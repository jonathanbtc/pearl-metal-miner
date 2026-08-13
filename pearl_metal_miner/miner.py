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
import subprocess
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
from . import economics  # noqa: E402
from .dashboard import Dashboard  # noqa: E402
from .metal_capi import HITS_BUF_BYTES, HITS_CAPACITY, JobShape, Metal  # noqa: E402
from .notify import Notifier  # noqa: E402
from .stats import RateMeter, fmt_uptime  # noqa: E402
from .stratum.dialect import Job, PoolConnection, ShareResult  # noqa: E402
from .stratum.kryptex import KryptexDialect  # noqa: E402
from .stratum.luckypool import LuckyPoolDialect  # noqa: E402

DIALECTS = {
    "kryptex": (KryptexDialect, "prl-eu.kryptex.network", 7048),
    "luckypool": (LuckyPoolDialect, "pearl-eu1.luckypool.io", 3360),
}


_sink = None  # the dashboard's serialized writer while the panel is up


def log(*a):
    line = f"[{time.strftime('%H:%M:%S')}] " + " ".join(str(x) for x in a)
    if _sink is None:
        print(line, flush=True)
    else:
        _sink(line)


def _set_sink(fn):
    global _sink
    _sink = fn


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt


_BATTERY_LOW_INTENSITY = 25  # the "low" mode's cap while on battery
_BATTERY_POLL_S = 20         # unplug → reaction within ~30 s


def power_source() -> str:
    """'battery' or 'ac' via pmset. Fails toward 'ac' — a parse failure must
    never pause a desktop by mistake."""
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True,
                             text=True, timeout=5).stdout
        if "Battery Power" in out:
            return "battery"
    except Exception:  # noqa: BLE001
        pass
    return "ac"


def hid_idle_seconds() -> float:
    """System idle time via IOKit (no dependencies). Returns 0 on failure so
    auto-intensity fails toward the polite floor, never toward full burn."""
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
        self.device_name = info["name"]
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


_EPILOG = """\
getting started (each line is copy-paste):
  python -m pearl_metal_miner.miner --self-test
                                            prove the GPU math is bit-exact on this
                                            machine first: ~50 exact checks, ~3 s
  python -m pearl_metal_miner.miner init    one-time setup: pool, wallet (created
                                            here if missing), your cost assumptions
                                            → config.toml in the project folder
  python -m pearl_metal_miner.miner         mine with those settings

more examples:
  --benchmark                               how fast is THIS Mac? offline speed
                                            test + your economics verdict, ~1 min
  --pool kryptex --worker studio            pick a pool (default: luckypool, the
                                            one with verified accepted shares)
                                            and your dashboard name
  --intensity 60 --auto-intensity           polite laptop: ~60% GPU while you work,
                                            full speed after 5 idle minutes
  --keep-awake --no-notify                  unattended Mac: no sleep, no toasts

related commands:
  python -m pearl_metal_miner.wallet {new,show,verify}
                                            manage the local payout wallet

debugging:
  PRL_RAW=1 python -m pearl_metal_miner.miner ...
                                            log every raw stratum line, both
                                            directions — the starting point for
                                            adding a new pool dialect

Stopping is Ctrl-C (or SIGTERM): the pool just sees a disconnect; you get a
session summary and exit code 0. The README tells the full story, including
the economics of why this is a hobby and not an income.
"""


def _bounded(cast, lo, hi, unit=""):
    """An argparse `type=` that refuses out-of-range numbers by name. Every
    numeric flag here has a range it means, and several of them misbehave
    badly outside it — `--region-rows 0` divides by zero on the general
    kernel, a negative `--max-job-age` makes the watchdog fire every pass and
    reconnect forever. Cheaper to refuse the number than to explain the
    symptom."""
    def parse(raw: str):
        try:
            v = cast(raw)
        except ValueError:
            want = "a whole number" if cast is int else "a number"
            raise argparse.ArgumentTypeError(f"must be {want} (got {raw!r})") from None
        if not lo <= v <= hi:
            raise argparse.ArgumentTypeError(
                f"must be between {lo:g} and {hi:g}{unit} (got {v:g})")
        return v
    return parse


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pearl_metal_miner.miner",
        description="Pool mining for Pearl (PRL) on Apple Silicon. The proof-of-work\n"
                    "sweep runs on the GPU as a bit-exact Metal port of the reference\n"
                    "implementation, and --self-test proves that on your machine before\n"
                    "any money is at stake. Fair warning: at current network difficulty\n"
                    "a lone Mac is a hobby, not an income.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="store_true",
                    help="print version and third-party notices")
    ap.add_argument("--self-test", action="store_true",
                    help="run the live differential against the reference and exit")
    ap.add_argument("--benchmark", action="store_true",
                    help="offline speed test (~1 min, no pool/wallet/network): "
                         "measures this Mac's real tiles/s at the default "
                         "shape, prints your economics verdict if configured, "
                         "and a paste-ready result block")
    ap.add_argument("--benchmark-seconds", type=_bounded(float, 1, 86400, " s"),
                    default=45,
                    help="measured duration of --benchmark after warmup "
                         "(default %(default)s)")
    ap.add_argument("--pool", choices=sorted(DIALECTS), default="luckypool",
                    help="which pool to mine on; picks the wire dialect and "
                         "the default endpoint (default: %(default)s)")
    ap.add_argument("--host",
                    help="pool hostname, if not the chosen pool's default")
    ap.add_argument("--port", type=_bounded(int, 1, 65535),
                    help="pool port, if not the chosen pool's default")
    ap.add_argument("--address", help="payout address (prl1p…); default: the "
                                      "local wallet.json, if you created one")
    ap.add_argument("--worker", default="m1",
                    help="any label for this machine; the pool dashboard "
                         "shows stats per address.worker (default: %(default)s)")
    ap.add_argument("--m", type=int, default=8192,
                    help="job shape: grid rows (default %(default)s — the "
                         "defaults are the fast-kernel shape; see README)")
    ap.add_argument("--n", type=int, default=8192,
                    help="job shape: grid columns (default %(default)s)")
    ap.add_argument("--k", type=int, default=4096,
                    help="job shape: inner dimension (default %(default)s)")
    ap.add_argument("--rank", type=int, default=128,
                    help="job shape: tile rank; anything but 128 carries a "
                         "consensus difficulty penalty, and the miner warns "
                         "(default %(default)s)")
    ap.add_argument("--rows", default="0,32",
                    help="hash-tile rows pattern, comma-separated offsets "
                         "(advanced; default %(default)s)")
    ap.add_argument("--cols", default=",".join(str(i) for i in range(64)),
                    help="hash-tile cols pattern, comma-separated offsets "
                         "(advanced; default 0,1,…,63)")
    ap.add_argument("--intensity", type=_bounded(int, 1, 100), default=100,
                    help="1-100: GPU duty cycle floor; CPU is capped separately "
                         "via --cpu-threads")
    ap.add_argument("--auto-intensity", action="store_true",
                    help="treat --intensity as the floor while you use the "
                         "machine; ramp to 100 after 5 idle minutes and drop "
                         "back the moment input resumes")
    ap.add_argument("--cpu-threads", type=_bounded(int, 1, 1024), default=4,
                    help="host commitment thread cap (RAYON_NUM_THREADS)")
    ap.add_argument("--region-rows", type=_bounded(int, 1, 1 << 20), default=256,
                    help="row-bases per GPU dispatch (burst size)")
    ap.add_argument("--max-accepted", type=_bounded(int, 0, 1 << 31), default=0,
                    help="stop after this many accepted shares (0 = run forever)")
    ap.add_argument("--on-battery", choices=("pause", "low", "full"),
                    default="pause",
                    help="when the Mac runs on battery: pause (default — stop "
                         "sweeping, keep the pool connection, resume on AC by "
                         "itself), low (cap intensity at "
                         f"{_BATTERY_LOW_INTENSITY}), or full (mine on, one "
                         "warning). Desktops are unaffected")
    ap.add_argument("--keep-awake", action="store_true",
                    help="hold off system sleep while mining (spawns "
                         "caffeinate -is, released on exit); the display may "
                         "still sleep, and a closed lid still wins")
    ap.add_argument("--no-notify", action="store_true",
                    help="disable macOS notifications (on by default: accepted "
                         "shares — the payoff moment usually happens while "
                         "nobody watches the terminal)")
    ap.add_argument("--no-dashboard", action="store_true",
                    help="plain scrolling logs even in a terminal; the live "
                         "dashboard already disables itself when stdout is "
                         "piped or redirected")
    ap.add_argument("--max-job-age", type=_bounded(float, 0, 86400, " s"),
                    default=300,
                    help="watchdog: if the pool sends nothing for this many "
                         "seconds, drop the connection and reconnect — a pool "
                         "that keeps TCP open but stops sending jobs would "
                         "otherwise leave you grinding a stale job forever "
                         "(0 = off)")
    ap.add_argument("--time-limit", type=_bounded(float, 0, 3.15e9, " s"),
                    default=0,
                    help="stop after N seconds (0 = none)")
    return ap


def _explicit_dests(argv) -> set[str]:
    """Which dests the user actually typed. Same parser, every default
    suppressed: what remains in the namespace was given on the command
    line — the fact that decides flag-vs-config precedence."""
    probe = build_parser()
    for action in probe._actions:
        action.default = argparse.SUPPRESS
    return set(vars(probe.parse_args(argv)).keys())


def _apply_config(args, explicit: set[str]):
    """Overlay config.toml under the CLI: flag > file > built-in default.
    Also carries the config-only keys (on_battery, economics) onto args for
    the battery, money-line and benchmark paths to consume."""
    from . import config
    cfg = config.load(log=log)

    def take(key: str, dest: str | None = None):
        dest = dest or key
        if key in cfg and dest not in explicit:
            setattr(args, dest, cfg[key])

    for key in ("host", "port", "address", "worker", "intensity",
                "auto_intensity", "keep_awake", "max_job_age", "on_battery"):
        take(key)
    if cfg.get("pool") is not None and "pool" not in explicit:
        if cfg["pool"] in DIALECTS:
            args.pool = cfg["pool"]
        else:
            log(f"config.toml: pool = {cfg['pool']!r} is not one of "
                f"{'/'.join(sorted(DIALECTS))}; using {args.pool}")
    if "notifications" in cfg and "no_notify" not in explicit:
        args.no_notify = not cfg["notifications"]
    if "dashboard" in cfg and "no_dashboard" not in explicit:
        args.no_dashboard = not cfg["dashboard"]
    for key in ("electricity_usd_per_kwh", "assumed_prl_price_usd",
                "assumed_network_hashrate"):
        setattr(args, key, cfg.get(key))


def _shape_from_args(args, ap) -> JobShape:
    """The job shape the flags ask for, refused at startup if consensus would
    never accept it. Every failure here is a typo in an advanced flag, so it
    exits like any other bad flag — one line naming the rule, never a
    traceback, and never a run that sweeps forever and can't win."""
    def offsets(flag: str, text: str) -> list[int]:
        try:
            return [int(x) for x in text.split(",")]
        except ValueError:
            raise ValueError(f"--{flag} must be comma-separated whole numbers "
                             f"(got {text!r})") from None

    try:
        shape = JobShape(
            k=args.k, r=args.rank,
            rows_pattern=ref.Pattern.from_list(offsets("rows", args.rows)),
            cols_pattern=ref.Pattern.from_list(offsets("cols", args.cols)))
        ref.validate_shape(args.m, args.n, args.k, args.rank,
                           shape.rows_pattern, shape.cols_pattern)
    except ValueError as e:
        ap.error(f"job shape: {e}")
    return shape


def _interrupted(note: str) -> int:
    """Ctrl-C is a designed exit for every command, not only the mining loop:
    one line, never a traceback. Always non-zero — an interrupted command
    produced no result, and a half-run --self-test must never read as a pass."""
    print(f"\n{note}")
    return 1


def run(argv=None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if argv[:1] == ["init"]:
        from . import config
        try:
            return config.init_wizard(argv[1:])
        except KeyboardInterrupt:
            return _interrupted("aborted; nothing written")
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.version:
        print(_version_text())
        return 0
    if args.self_test:
        from . import selftest
        try:
            return selftest.run()
        except KeyboardInterrupt:
            return _interrupted("self-test interrupted — it did NOT pass; "
                                "rerun it before mining")
    _apply_config(args, _explicit_dests(argv))
    shape = _shape_from_args(args, ap)
    if args.benchmark:
        from . import benchmark
        try:
            return benchmark.run(args, shape)
        except KeyboardInterrupt:
            return _interrupted("benchmark interrupted — no result "
                                "(it needs the full run to measure)")

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
            ap.error("no payout address: run `python -m pearl_metal_miner.miner "
                     "init` once (writes config.toml, creates a wallet if you "
                     "want one) — or pass --address, or run: "
                     "python -m pearl_metal_miner.wallet new")
        args.address, wallet_path = found
        log(f"no --address given; paying the local wallet {args.address} "
            f"(from {os.path.basename(wallet_path)} — that file is the only "
            f"claim on anything mined; back it up)")

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
    pending: dict[int, tuple[str, float]] = {}  # submit id -> (job_id, share difficulty)
    stats = {"grids": 0, "sub": 0, "acc": 0, "rej": 0, "disc": 0, "reco": 0,
             "attempt": 0, "down_since": None, "last_report": time.time(),
             "intensity_now": args.intensity, "last_share_t": None,
             "exp_tiles": None, "on_batt": False, "batt_poll_t": 0.0,
             "batt_warned": False, "acc_diff_sum": 0.0}
    meter = RateMeter()
    notifier = Notifier(enabled=not args.no_notify, log=log)
    conn: PoolConnection | None = None
    awake: subprocess.Popen | None = None
    dash: Dashboard | None = None
    stop_note = ""
    # A session summary describes a session. Startup failures (DNS, timeout,
    # refused) already print their own diagnosis; following it with
    # "0 tiles, 0 shares" reads like a run that finished, not one that never
    # began, so the summary waits until there is a session to summarise.
    session_began = False

    # Ctrl-C is the README's documented stop; SIGTERM is how process managers
    # say the same thing. Both must take the designed exit below — summary
    # printed, socket closed, exit code 0 — never a traceback.
    signal.signal(signal.SIGTERM, _raise_interrupt)

    try:
        if args.keep_awake:
            try:
                # -w ties the assertion to our pid even if we die ungracefully;
                # the finally below releases it on every designed exit. App Nap
                # is handled separately by the NSActivity token inside the
                # Metal context — this only adds the system-sleep assertion.
                awake = subprocess.Popen(
                    ["caffeinate", "-is", "-w", str(os.getpid())],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log("keep-awake: holding off system sleep while mining "
                    "(the display may still sleep)")
            except OSError as e:
                log(f"keep-awake unavailable ({e}); mining anyway")
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
        session_began = True
        factory = GridFactory(shape, args.m, args.n)

        def dash_state() -> dict:
            now = time.monotonic()
            if conn.dead.is_set():
                status = "reconnecting"
                if stats["attempt"]:
                    status += f" — attempt {stats['attempt']}"
                if stats["down_since"] is not None:
                    status += f", down {fmt_uptime(now - stats['down_since'])}"
            elif stats["on_batt"] and args.on_battery == "pause":
                status = "paused — on battery (resumes on AC)"
            else:
                status = "mining"
            rolling = meter.rolling()
            return {
                "device": engine.device_name,
                "pool": f"{args.pool} @ {host}:{port}", "worker": args.worker,
                "status": status, "uptime": meter.uptime(),
                "rolling": rolling, "avg": meter.average(),
                "intensity": (f"{stats['intensity_now']} (auto)"
                              if args.auto_intensity
                              else str(stats["intensity_now"])),
                "acc": stats["acc"], "rej": stats["rej"],
                "pending": len(pending),
                "last_share_ago": (now - stats["last_share_t"]
                                   if stats["last_share_t"] is not None else None),
                "est_next_s": (stats["exp_tiles"] / rolling
                               if stats["exp_tiles"] and rolling > 0 else None),
                "money": economics.verdict(
                    rolling, factor, engine.device_name,
                    stats["intensity_now"], args.electricity_usd_per_kwh,
                    args.assumed_prl_price_usd, args.assumed_network_hashrate),
            }

        dash = Dashboard(dash_state)
        if not args.no_dashboard:
            dash.start()
        if dash.active:
            _set_sink(dash.log)

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
                        entry = pending.pop(ev.msg_id, None)
                        if entry is not None:
                            tag, share_diff = entry
                            stats["acc" if ev.accepted else "rej"] += 1
                            log(f"share {'ACCEPTED' if ev.accepted else 'REJECTED'} "
                                f"(job {tag}) — {ev.raw[:160]}")
                            if ev.accepted:
                                stats["last_share_t"] = time.monotonic()
                                stats["acc_diff_sum"] += share_diff
                                notifier.send("Pearl miner",
                                              f"Share accepted — total {stats['acc']}")
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
                # 5, 10, 20, 40, then 60 forever. The exponent is capped too:
                # attempts run without limit, and 2**(attempt-1) alone would
                # grow a multi-thousand-bit integer over a long outage to
                # compute a number that has been 60 since attempt 5.
                delay = min(5 * 2 ** min(stats["attempt"] - 1, 4), 60)
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

            # Battery awareness (slow poll, like the idle poll below). On a
            # desktop power_source() is always "ac", so nothing here ever
            # fires — no logs, no behavior change.
            if time.monotonic() - stats["batt_poll_t"] > _BATTERY_POLL_S:
                stats["batt_poll_t"] = time.monotonic()
                on_batt = power_source() == "battery"
                if on_batt and not stats["on_batt"]:
                    if args.on_battery == "pause":
                        log("on battery — pausing (on_battery = pause); "
                            "resumes on AC by itself")
                        notifier.send("Pearl miner", "Paused — on battery")
                    elif args.on_battery == "low":
                        log(f"on battery — capping intensity at "
                            f"{_BATTERY_LOW_INTENSITY} (on_battery = low)")
                    elif not stats["batt_warned"]:
                        stats["batt_warned"] = True
                        log("on battery — mining at full intensity anyway "
                            "(on_battery = full); this drains a battery fast")
                elif not on_batt and stats["on_batt"]:
                    if args.on_battery == "pause":
                        log("back on AC — resuming")
                        notifier.send("Pearl miner", "Resuming — on AC power")
                    elif args.on_battery == "low":
                        log("back on AC — intensity restored")
                stats["on_batt"] = on_batt

            # A refused job leaves `job` as None; block briefly on the event queue
            # until the pool sends a usable one rather than spinning (or crashing
            # on job.target below).
            new_job = handle_events(block_s=1.0 if job is None else 0.0)
            if job is None:
                continue
            if stats["on_batt"] and args.on_battery == "pause":
                # Sweeping stops; the connection, event drain, and dashboard
                # stay alive, so resume is instant and the watchdog stays fed.
                # A job adopted while paused rebuilds its grid on resume.
                # Intensity is 0 while paused, not the pre-pause value: the
                # dashboard's money line prices power from it, and a pause
                # that still charged for electricity would be a wrong number.
                grid = None
                stats["intensity_now"] = 0
                time.sleep(1)
                continue
            if new_job or grid is None:
                bound_int = job.target * factor
                if bound_int >= 1 << 256:
                    log("bound overflows 2^256 — refusing job (target unusably easy)")
                    job = None
                    continue
                bound_bytes = bound_int.to_bytes(32, "little")
                stats["exp_tiles"] = float(1 << 256) / float(bound_int)
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
                pending[msg_id] = (job.job_id,
                                   economics.DIFF1_TARGET / job.target)
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
            if stats["on_batt"] and args.on_battery == "low":
                intensity = min(intensity, _BATTERY_LOW_INTENSITY)
            stats["intensity_now"] = intensity
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
        _set_sink(None)
        if dash is not None:
            try:
                dash.stop()  # scroll region reset, cursor back — before the summary
            except OSError:
                pass
        if awake is not None:
            try:
                awake.terminate()
                awake.wait(timeout=5)
            except Exception:  # noqa: BLE001 — releasing a comfort must not eat the summary
                pass
        if conn is not None:
            conn.close()
        try:
            if stop_note:
                log(stop_note)
            # No `return` in this finally: it would swallow an in-flight
            # exception (a Metal failure must still reach the user).
            if session_began:
                log(f"session: {meter.total} tiles in {fmt_uptime(meter.uptime())} "
                    f"({meter.average() / 1e6:.3f}M tiles/s average), "
                    f"{stats['grids']} grids")
                log(f"session: shares {stats['acc']} accepted, {stats['rej']} rejected, "
                    f"{stats['sub']} submitted"
                    + (f" ({len(pending)} awaiting verdict)" if pending else ""))
            if session_began and stats["disc"]:
                log(f"session: connection lost {stats['disc']}×, "
                    f"reconnected {stats['reco']}×")
            if stats["acc_diff_sum"] and args.assumed_network_hashrate:
                earned = economics.prl_per_share_est(
                    stats["acc_diff_sum"], args.assumed_network_hashrate)
                log(f"session: est. {earned:.8f} PRL earned from accepted "
                    f"shares — an estimate at your assumed network hashrate "
                    f"({args.assumed_network_hashrate:g} EH/s), before pool "
                    f"fees and luck")
        except BrokenPipeError:
            # Silence the interpreter's own stdout-flush complaint at exit.
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


if __name__ == "__main__":
    sys.exit(run())
