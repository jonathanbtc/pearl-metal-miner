"""pearl-metal-miner — pool mining on Apple Silicon, Metal compute backend.

Loop per ADR-0001: the host generates and commits the grid (upstream's own
ISC machinery); the GPU generates noise, applies it, and sweeps tiles; a hit
is proved on the host, verified locally AT SHARE DIFFICULTY, and submitted.

Intensity is first-class and covers CPU and GPU both: the GPU throttles by
sleeping between region dispatches; the host commitment is capped via
RAYON_NUM_THREADS, which must be set before pearl_mining is imported — which
is why this module sets it at the very top.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import time


def _early_env():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--cpu-threads", type=int, default=4)
    args, _ = ap.parse_known_args()
    os.environ.setdefault("RAYON_NUM_THREADS", str(args.cpu_threads))


_early_env()

import numpy as np  # noqa: E402
import pearl_mining as pm  # noqa: E402

from . import reference as ref  # noqa: E402
from .host import Grid, verify_share  # noqa: E402
from .metal_capi import JobShape, Metal  # noqa: E402
from .stratum.dialect import Job, PoolConnection, ShareResult  # noqa: E402
from .stratum.kryptex import KryptexDialect  # noqa: E402
from .stratum.luckypool import LuckyPoolDialect  # noqa: E402

DIALECTS = {
    "kryptex": (KryptexDialect, "prl-eu.kryptex.network", 7048),
    "luckypool": (LuckyPoolDialect, "pearl-eu1.luckypool.io", 3360),
}


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


class Engine:
    """Owns the Metal context and the persistent buffers for one job shape."""

    def __init__(self, shape: JobShape, m_dim: int, n_dim: int):
        self.metal = Metal()
        info = self.metal.device_info()
        log(f"device {info['name']}, threadgroup mem {info['max_threadgroup_memory']}, "
            f"max threads {info['max_threads_per_threadgroup']}")
        self.shape, self.m_dim, self.n_dim = shape, m_dim, n_dim
        self.metal.compile(shape)
        k, r = shape.k, shape.r
        m = self.metal
        self.a_buf = m.alloc(m_dim * k)
        self.bt_buf = m.alloc(n_dim * k)
        self.an_buf = m.alloc(m_dim * k)
        self.bnt_buf = m.alloc(n_dim * k)
        self.ua = m.alloc(m_dim * r)
        self.ub = m.alloc(n_dim * r)
        self.pa = m.alloc(k * 8)
        self.pb = m.alloc(k * 8)
        self.row_bases = np.array(shape.rows_pattern.valid_offsets(m_dim), dtype=np.uint32)
        self.col_bases = np.array(shape.cols_pattern.valid_offsets(n_dim), dtype=np.uint32)
        self.cb_buf = m.from_numpy(self.col_bases)
        self.rb_slice = m.alloc(len(self.row_bases) * 4)
        self.hits = m.alloc(4 + 8 * 4096)
        self.n_tiles_grid = len(self.row_bases) * len(self.col_bases)
        # Blocked fast path: rows [0,32], cols [0..63], r ≤ 128, 64 | m and n.
        self.fast = (shape.rows_pattern.shape[0] == (32, 2)
                     and shape.rows_pattern.shape[1][1] == 1
                     and shape.cols_pattern.shape[0] == (1, 64)
                     and shape.cols_pattern.shape[1][1] == 1
                     and shape.r <= 128 and m_dim % 64 == 0 and n_dim % 64 == 0)
        self.n_bands = m_dim // 64
        self.n_cb = n_dim // 64
        log(f"pow kernel: {'blocked fast path (v2)' if self.fast else 'general (v1)'}")

    def load_grid(self, grid: Grid):
        self.a_buf.array(np.int8, (self.m_dim, self.shape.k))[...] = grid.A
        self.bt_buf.array(np.int8, (self.n_dim, self.shape.k))[...] = grid.Bt
        m = self.metal
        m.noise_uniform(ref.SEED_LABEL_A, grid.a_seed, self.ua, self.m_dim)
        m.noise_pairs(ref.SEED_LABEL_A, grid.a_seed, self.pa)
        m.noise_uniform(ref.SEED_LABEL_B, grid.b_seed, self.ub, self.n_dim)
        m.noise_pairs(ref.SEED_LABEL_B, grid.b_seed, self.pb)
        m.noise_apply(self.a_buf, self.ua, self.pa, self.an_buf, self.m_dim)
        m.noise_apply(self.bt_buf, self.ub, self.pb, self.bnt_buf, self.n_dim)

    def n_regions(self, region_rows: int) -> int:
        if self.fast:
            bands_per = max(1, region_rows // 32)
            return -(-self.n_bands // bands_per)
        return -(-len(self.row_bases) // region_rows)

    def sweep_region(self, idx: int, region_rows: int, a_seed: bytes,
                     bound: bytes) -> tuple[list[tuple[int, int]], int]:
        self.hits.array(np.uint32, (1,))[0] = 0
        if self.fast:
            bands_per = max(1, region_rows // 32)
            band_lo = idx * bands_per
            n_bands = min(bands_per, self.n_bands - band_lo)
            self.metal.pow_sweep2(self.an_buf, self.bnt_buf, band_lo, n_bands,
                                  self.n_cb, a_seed, bound, self.hits, 4096, None)
            n_tiles = n_bands * 32 * self.n_cb
        else:
            rb = self.row_bases[idx * region_rows:(idx + 1) * region_rows]
            self.rb_slice.array(np.uint32, (len(self.row_bases),))[:len(rb)] = rb
            self.metal.pow_sweep(self.an_buf, self.bnt_buf, self.rb_slice, len(rb),
                                 self.cb_buf, len(self.col_bases), a_seed, bound,
                                 self.hits, 4096, None)
            n_tiles = len(rb) * len(self.col_bases)
        count = min(int(self.hits.array(np.uint32, (1,))[0]), 4096)
        pairs = self.hits.array(np.uint32, (1 + 2 * 4096,))[1:1 + 2 * count]
        return [(int(pairs[2 * i]), int(pairs[2 * i + 1])) for i in range(count)], n_tiles


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pearl-metal-miner")
    ap.add_argument("--pool", choices=sorted(DIALECTS), default="kryptex")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--address", help="your PRL address (prl1p…)")
    ap.add_argument("--worker", default="m1")
    ap.add_argument("--m", type=int, default=8192)
    ap.add_argument("--n", type=int, default=8192)
    ap.add_argument("--k", type=int, default=4096)
    ap.add_argument("--rank", type=int, default=128)
    ap.add_argument("--rows", default="0,32", help="rows pattern (comma ints)")
    ap.add_argument("--cols", default=",".join(str(i) for i in range(64)),
                    help="cols pattern (comma ints)")
    ap.add_argument("--intensity", type=int, default=100,
                    help="1-100: GPU duty cycle floor; CPU is capped separately "
                         "via --cpu-threads")
    ap.add_argument("--cpu-threads", type=int, default=4,
                    help="host commitment thread cap (RAYON_NUM_THREADS)")
    ap.add_argument("--region-rows", type=int, default=256,
                    help="row-bases per GPU dispatch (burst size)")
    ap.add_argument("--max-accepted", type=int, default=0,
                    help="stop after this many accepted shares (0 = run forever)")
    ap.add_argument("--time-limit", type=float, default=0,
                    help="stop after N seconds (0 = none)")
    args = ap.parse_args(argv)

    if not args.address:
        burner = os.path.join(os.path.dirname(__file__), "..", "burner_wallet.json")
        if os.path.exists(burner):
            with open(burner) as f:
                args.address = json.load(f)["address"]
            log(f"no --address given; using TESTING burner address {args.address}")
        else:
            ap.error("--address required (or run tools/make_burner_wallet.py)")

    shape = JobShape(
        k=args.k, r=args.rank,
        rows_pattern=ref.Pattern.from_list([int(x) for x in args.rows.split(",")]),
        cols_pattern=ref.Pattern.from_list([int(x) for x in args.cols.split(",")]))
    factor = ref.difficulty_factor(shape.h, shape.w, args.k, args.rank)
    pfactor = ref.penalized_factor(shape.h, shape.w, args.k, args.rank)
    if factor != pfactor:
        log(f"note: rank {args.rank} carries a rank penalty ({pfactor}/{factor} of "
            f"the bound); rank 128 avoids it")

    dialect_cls, def_host, def_port = DIALECTS[args.pool]
    host, port = args.host or def_host, args.port or def_port
    engine = Engine(shape, args.m, args.n)
    conn = PoolConnection(dialect_cls(), host, port, args.address, args.worker, log=log)
    log(f"connecting to {args.pool} at {host}:{port} as {args.address}.{args.worker}")
    conn.connect()

    job: Job | None = None
    grid: Grid | None = None
    bound_bytes = b""
    row_cursor = 0
    rng = np.random.default_rng()
    pending: dict[int, str] = {}
    stats = {"tiles": 0, "grids": 0, "sub": 0, "acc": 0, "rej": 0, "t0": time.time(),
             "last_report": time.time()}
    t_start = time.time()

    def handle_events(block_s: float = 0.0):
        nonlocal job
        newest: Job | None = None
        try:
            while True:
                ev = conn.events.get(timeout=block_s) if block_s else conn.events.get_nowait()
                block_s = 0
                if isinstance(ev, Job):
                    newest = ev
                elif isinstance(ev, ShareResult):
                    tag = pending.pop(ev.msg_id, None)
                    if tag is not None:
                        stats["acc" if ev.accepted else "rej"] += 1
                        log(f"share {'ACCEPTED' if ev.accepted else 'REJECTED'} "
                            f"(job {tag}) — {ev.raw[:160]}")
        except queue.Empty:
            pass
        if newest is not None and (job is None or newest.job_id != job.job_id):
            job = newest
            return True
        return False

    log("waiting for first job…")
    while job is None:
        if conn.dead.is_set():
            log("connection died before first job")
            return 1
        handle_events(block_s=1.0)

    while True:
        if conn.dead.is_set():
            log("connection lost; reconnecting in 5s")
            time.sleep(5)
            try:
                conn.connect()
            except OSError as e:
                log(f"reconnect failed: {e}")
            continue
        if args.time_limit and time.time() - t_start > args.time_limit:
            log("time limit reached")
            break
        if args.max_accepted and stats["acc"] >= args.max_accepted:
            log("accepted-share target reached")
            break

        new_job = handle_events()
        if new_job or grid is None:
            bound_int = job.target * factor
            if bound_int >= 1 << 256:
                log("bound overflows 2^256 — refusing job (target unusably easy)")
                job = None
                continue
            bound_bytes = bound_int.to_bytes(32, "little")
            t0 = time.time()
            grid = Grid(shape, args.m, args.n, job.header_bytes, rng)
            engine.load_grid(grid)
            stats["grids"] += 1
            row_cursor = 0
            n_regions = engine.n_regions(args.region_rows)
            log(f"job {job.job_id} height={job.height}: grid #{stats['grids']} "
                f"committed+noised in {time.time() - t0:.2f}s "
                f"(~2^{bound_int.bit_length() - 1} bound, "
                f"{engine.n_tiles_grid} tiles/grid)")

        t_burst = time.time()
        hits, n_tiles = engine.sweep_region(row_cursor, args.region_rows,
                                            grid.a_seed, bound_bytes)
        stats["tiles"] += n_tiles
        row_cursor += 1
        t_burst = time.time() - t_burst

        for base_r, base_c in hits:
            proof = grid.craft_proof(base_r, base_c)
            header = pm.IncompleteBlockHeader.from_bytes(job.header_bytes)
            ok, msg = verify_share(header, proof, job.target)
            if not ok:
                log(f"LOCAL VERIFY FAILED at share difficulty — NOT submitting. "
                    f"tile ({base_r},{base_c}): {msg}")
                continue
            msg_id = conn.submit(job.job_id, proof.to_base64())
            pending[msg_id] = job.job_id
            stats["sub"] += 1
            log(f"share found at tile ({base_r},{base_c}) → verified locally → "
                f"submitted (msg {msg_id})")

        if row_cursor >= n_regions:
            grid = None  # grid exhausted; next iteration builds a fresh one

        if args.intensity < 100:
            time.sleep(t_burst * (100 - args.intensity) / max(args.intensity, 1))

        if time.time() - stats["last_report"] > 30:
            dt = time.time() - stats["t0"]
            log(f"{stats['tiles'] / dt / 1e6:.3f}M tiles/s | grids {stats['grids']} | "
                f"shares {stats['acc']}/{stats['sub']} accepted "
                f"({stats['rej']} rejected)")
            stats["last_report"] = time.time()

    dt = time.time() - stats["t0"]
    log(f"done: {stats['tiles']} tiles in {dt:.0f}s "
        f"({stats['tiles'] / dt / 1e6:.3f}M tiles/s), "
        f"shares {stats['acc']}/{stats['sub']} accepted, {stats['rej']} rejected")
    return 0


if __name__ == "__main__":
    sys.exit(run())
