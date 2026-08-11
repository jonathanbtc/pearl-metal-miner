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
import os
import queue
import signal
import socket
import sys
import threading
import time


def _early_env():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--cpu-threads", type=int, default=4)
    args, _ = ap.parse_known_args()
    os.environ.setdefault("RAYON_NUM_THREADS", str(args.cpu_threads))


_early_env()

import numpy as np  # noqa: E402
import pearl_mining as pm  # noqa: E402

from . import __version__  # noqa: E402
from . import reference as ref  # noqa: E402
from . import wallet  # noqa: E402
from .host import Grid, verify_share  # noqa: E402
from .metal_capi import HITS_BUF_BYTES, HITS_CAPACITY, JobShape, Metal  # noqa: E402
from .stats import RateMeter, fmt_uptime  # noqa: E402
from .stratum.dialect import Job, PoolConnection, ShareResult  # noqa: E402
from .stratum.kryptex import KryptexDialect  # noqa: E402
from .stratum.luckypool import LuckyPoolDialect  # noqa: E402

DIALECTS = {
    "kryptex": (KryptexDialect, "prl-eu.kryptex.network", 7048),
    "luckypool": (LuckyPoolDialect, "pearl-eu1.luckypool.io", 3360),
}


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt


def hid_idle_seconds() -> float:
    """System idle time via IOKit (no dependencies). Returns 0 on failure so
    auto-intensity fails toward the polite floor, never toward full burn."""
    import subprocess  # deferred: only --auto-intensity ever needs it
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"],
                             capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if "HIDIdleTime" in line:
                return int(line.split("=")[-1].strip()) / 1e9
    except Exception:  # noqa: BLE001
        pass
    return 0.0


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
        self.hits = m.alloc(HITS_BUF_BYTES)
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
                                  self.n_cb, a_seed, bound, self.hits,
                                  HITS_CAPACITY, None)
            n_tiles = n_bands * 32 * self.n_cb
        else:
            rb = self.row_bases[idx * region_rows:(idx + 1) * region_rows]
            self.rb_slice.array(np.uint32, (len(self.row_bases),))[:len(rb)] = rb
            self.metal.pow_sweep(self.an_buf, self.bnt_buf, self.rb_slice, len(rb),
                                 self.cb_buf, len(self.col_bases), a_seed, bound,
                                 self.hits, HITS_CAPACITY, None)
            n_tiles = len(rb) * len(self.col_bases)
        count = min(int(self.hits.array(np.uint32, (1,))[0]), HITS_CAPACITY)
        pairs = self.hits.array(np.uint32, (1 + 2 * HITS_CAPACITY,))[1:1 + 2 * count]
        return [(int(pairs[2 * i]), int(pairs[2 * i + 1])) for i in range(count)], n_tiles


def _version_text() -> str:
    notice = os.path.join(os.path.dirname(__file__), "..", "NOTICE")
    isc = ""
    if os.path.exists(notice):
        with open(notice) as f:
            isc = f.read()
    return (f"pearl-metal-miner {__version__} — Apache-2.0, no dev fee.\n"
            f"Not affiliated with Pearl Research Labs.\n\n{isc}")


class GridFactory(threading.Thread):
    """Prepares the next grid's host side (generation + Merkle commitment)
    while the GPU sweeps the current one. The GPU wait releases the GIL, so
    the overlap is real. A prepared grid is bound to a job_id; a stale one is
    discarded on job change."""

    def __init__(self, shape, m_dim, n_dim):
        super().__init__(daemon=True)
        self.shape, self.m_dim, self.n_dim = shape, m_dim, n_dim
        self.requests: queue.Queue = queue.Queue()
        self.ready: queue.Queue = queue.Queue()
        self.rng = np.random.default_rng()
        self.start()

    def request(self, job):
        self.requests.put(job)

    def take(self, job):
        """A ready grid for `job` if the pipeline has one, else build inline.
        Never blocks: a stale or missing grid is cheaper to rebuild than to
        wait for, and the GPU must not stall on the host."""
        while True:
            try:
                job_id, grid = self.ready.get_nowait()
            except queue.Empty:
                return Grid(self.shape, self.m_dim, self.n_dim, job.header_bytes, self.rng)
            if job_id == job.job_id:
                return grid  # discard grids for superseded jobs

    def run(self):
        while True:
            job = self.requests.get()
            grid = Grid(self.shape, self.m_dim, self.n_dim, job.header_bytes, self.rng)
            self.ready.put((job.job_id, grid))


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pearl-metal-miner")
    ap.add_argument("--version", action="store_true",
                    help="print version and third-party notices")
    ap.add_argument("--self-test", action="store_true",
                    help="run the live differential against the reference and exit")
    ap.add_argument("--pool", choices=sorted(DIALECTS), default="kryptex")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--address", help="payout address (prl1p…); default: the "
                                      "local wallet.json, if you created one")
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
    ap.add_argument("--auto-intensity", action="store_true",
                    help="treat --intensity as the floor while you use the "
                         "machine; ramp to 100 after 5 idle minutes and drop "
                         "back the moment input resumes")
    ap.add_argument("--cpu-threads", type=int, default=4,
                    help="host commitment thread cap (RAYON_NUM_THREADS)")
    ap.add_argument("--region-rows", type=int, default=256,
                    help="row-bases per GPU dispatch (burst size)")
    ap.add_argument("--max-accepted", type=int, default=0,
                    help="stop after this many accepted shares (0 = run forever)")
    ap.add_argument("--max-job-age", type=float, default=300,
                    help="watchdog: if the pool sends nothing for this many "
                         "seconds, drop the connection and reconnect — a pool "
                         "that keeps TCP open but stops sending jobs would "
                         "otherwise leave you grinding a stale job forever "
                         "(0 = off)")
    ap.add_argument("--time-limit", type=float, default=0,
                    help="stop after N seconds (0 = none)")
    args = ap.parse_args(argv)

    if args.version:
        print(_version_text())
        return 0
    if args.self_test:
        from . import selftest
        return selftest.run()

    # A bad payout address is this domain's silent failure at its worst —
    # value mined to an address nobody can claim — so refuse it before the
    # first byte reaches the pool.
    if args.address:
        try:
            args.address = wallet.validate_payout_address(args.address)
        except ValueError as e:
            ap.error(f"--address: {e}")
    else:
        try:
            found = wallet.payout_address_from_disk()
        except ValueError as e:
            ap.error(str(e))
        if found is None:
            ap.error("--address required — or create a local payout wallet once "
                     "with: python -m pearl_metal_miner.wallet new")
        args.address, wallet_path = found
        log(f"no --address given; paying the local wallet {args.address} "
            f"(from {os.path.basename(wallet_path)} — that file is the only "
            f"claim on anything mined; back it up)")

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

    job: Job | None = None
    grid: Grid | None = None
    bound_bytes = b""
    row_cursor = 0
    pending: dict[int, str] = {}
    stats = {"grids": 0, "sub": 0, "acc": 0, "rej": 0, "disc": 0, "reco": 0,
             "attempt": 0, "down_since": None, "last_report": time.time()}
    meter = RateMeter()
    conn: PoolConnection | None = None
    stop_note = ""

    # Ctrl-C is the README's documented stop; SIGTERM is how process managers
    # say the same thing. Both must take the designed exit below — summary
    # printed, socket closed, exit code 0 — never a traceback.
    signal.signal(signal.SIGTERM, _raise_interrupt)

    try:
        engine = Engine(shape, args.m, args.n)
        conn = PoolConnection(dialect_cls(), host, port, args.address, args.worker,
                              log=log)
        log(f"connecting to {args.pool} at {host}:{port} as "
            f"{args.address}.{args.worker}")
        try:
            conn.connect()
        except socket.gaierror as e:
            log(f"cannot resolve {host}: {e} — check --host and your network")
            return 1
        except TimeoutError:
            log(f"connect to {host}:{port} timed out — pool down, or the port "
                f"is blocked?")
            return 1
        except OSError as e:
            log(f"cannot connect to {host}:{port}: {e}")
            return 1
        factory = GridFactory(shape, args.m, args.n)

        def handle_events(block_s: float = 0.0):
            """Drain the pool event queue: record share verdicts, adopt the newest
            job. Returns True if `job` changed (waits up to block_s for the first
            event)."""
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
        while True:
            if args.time_limit and meter.uptime() > args.time_limit:
                log("time limit reached")
                break
            if args.max_accepted and stats["acc"] >= args.max_accepted:
                log("accepted-share target reached")
                break

            if conn.dead.is_set():
                if stats["down_since"] is None:
                    stats["down_since"] = time.monotonic()
                    stats["disc"] += 1
                stats["attempt"] += 1
                delay = min(5 * 2 ** (stats["attempt"] - 1), 60)
                log(f"connection lost (down "
                    f"{fmt_uptime(time.monotonic() - stats['down_since'])}); "
                    f"reconnect attempt {stats['attempt']} in {delay}s")
                time.sleep(delay)
                try:
                    conn.connect()
                    pending.clear()  # old submissions will never be answered
                    job, grid = None, None  # wait for a fresh job on the new session
                    stats["reco"] += 1
                    log(f"reconnected on attempt {stats['attempt']} (down "
                        f"{fmt_uptime(time.monotonic() - stats['down_since'])}); "
                        f"waiting for a job")
                    stats["attempt"], stats["down_since"] = 0, None
                except socket.gaierror as e:
                    log(f"attempt {stats['attempt']}: DNS lookup for {host} "
                        f"failed: {e}")
                except TimeoutError:
                    log(f"attempt {stats['attempt']}: connect timed out")
                except OSError as e:
                    log(f"attempt {stats['attempt']}: {e}")
                continue

            # The stratum protocol has no ping. A pool that keeps TCP open but
            # goes mute would leave us sweeping a stale job forever — the
            # silent-failure mode this project treats as the enemy — so any
            # pool silence beyond the watchdog age forces a fresh session.
            if args.max_job_age and time.monotonic() - conn.last_rx > args.max_job_age:
                log(f"WATCHDOG: nothing from the pool for "
                    f"{fmt_uptime(time.monotonic() - conn.last_rx)} "
                    f"(--max-job-age {args.max_job_age:g}) — dropping the "
                    f"connection to force a fresh session")
                conn.close()
                continue

            # A refused job leaves `job` as None; block briefly on the event queue
            # until the pool sends a usable one rather than spinning (or crashing
            # on job.target below).
            new_job = handle_events(block_s=1.0 if job is None else 0.0)
            if job is None:
                continue
            if new_job or grid is None:
                bound_int = job.target * factor
                if bound_int >= 1 << 256:
                    log("bound overflows 2^256 — refusing job (target unusably easy)")
                    job = None
                    continue
                bound_bytes = bound_int.to_bytes(32, "little")
                t0 = time.time()
                grid = factory.take(job)
                factory.request(job)  # keep one grid building ahead of the sweep
                engine.load_grid(grid)
                stats["grids"] += 1
                row_cursor = 0
                n_regions = engine.n_regions(args.region_rows)
                if stats["grids"] == 1 or new_job:
                    log(f"job {job.job_id} height={job.height}: grid #{stats['grids']} "
                        f"ready in {time.time() - t0:.2f}s "
                        f"(~2^{bound_int.bit_length() - 1} bound, "
                        f"{engine.n_tiles_grid} tiles/grid)")

            t_burst = time.time()
            hits, n_tiles = engine.sweep_region(row_cursor, args.region_rows,
                                                grid.a_seed, bound_bytes)
            meter.add(n_tiles)
            row_cursor += 1
            t_burst = time.time() - t_burst

            for base_r, base_c in hits:
                if conn.dead.is_set():
                    log(f"share at tile ({base_r},{base_c}) dropped: connection down "
                        f"before submit")
                    break
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
                    f"submitted (msg {msg_id}) on job {job.job_id}")

            if row_cursor >= n_regions:
                grid = None  # grid exhausted; next iteration builds a fresh one

            intensity = args.intensity
            if args.auto_intensity and time.time() - stats.get("last_idle_poll", 0) > 10:
                stats["last_idle_poll"] = time.time()
                stats["idle_full"] = hid_idle_seconds() > 300
            if args.auto_intensity and stats.get("idle_full"):
                intensity = 100
            if intensity < 100:
                time.sleep(t_burst * (100 - intensity) / max(intensity, 1))

            if time.time() - stats["last_report"] > 30:
                judged = stats["acc"] + stats["rej"]
                pct = f" ({100 * stats['acc'] / judged:.0f}% accept)" if judged else ""
                log(f"{meter.rolling() / 1e6:.3f}M tiles/s (60s) | "
                    f"{meter.average() / 1e6:.3f}M/s session | "
                    f"shares {stats['acc']} acc / {stats['rej']} rej{pct} | "
                    f"up {fmt_uptime(meter.uptime())}")
                stats["last_report"] = time.time()
    except KeyboardInterrupt:
        stop_note = "stopped by user — disconnecting"
    except BrokenPipeError:
        pass  # stdout's reader vanished (e.g. `| head`); nothing can be printed
    finally:
        # A second Ctrl-C (or a racing TERM) during teardown must not turn a
        # clean stop into a traceback.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if conn is not None:
            conn.close()
        try:
            if stop_note:
                log(stop_note)
            log(f"session: {meter.total} tiles in {fmt_uptime(meter.uptime())} "
                f"({meter.average() / 1e6:.3f}M tiles/s average), "
                f"{stats['grids']} grids")
            log(f"session: shares {stats['acc']} accepted, {stats['rej']} rejected, "
                f"{stats['sub']} submitted"
                + (f" ({len(pending)} awaiting verdict)" if pending else ""))
            if stats["disc"]:
                log(f"session: connection lost {stats['disc']}×, "
                    f"reconnected {stats['reco']}×")
        except BrokenPipeError:
            # Silence the interpreter's own stdout-flush complaint at exit.
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


if __name__ == "__main__":
    sys.exit(run())
