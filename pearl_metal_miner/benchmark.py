"""--benchmark: the offline speed test. No pool, no wallet, no network —
a synthetic job at the exact default mining shape, swept by the same
Engine/GridFactory machinery as live mining (grid rebuild stalls included),
so the number it prints is the number the miner really achieves. This is
what makes the README's headline speed reproducible by a shipped command,
and its paste-ready block is the format contract for the community
hardware table (C3).
"""

from __future__ import annotations

import datetime
import platform
import time

from . import __version__, economics
from . import reference as ref


class _SyntheticJob:
    job_id = "benchmark"
    header_bytes = bytes(range(76))  # any fixed 76 bytes; timing is value-blind


def run(args) -> int:
    from .metal_capi import JobShape
    from .miner import Engine, GridFactory, log  # lazy — miner imports us lazily

    shape = JobShape(
        k=args.k, r=args.rank,
        rows_pattern=ref.Pattern.from_list([int(x) for x in args.rows.split(",")]),
        cols_pattern=ref.Pattern.from_list([int(x) for x in args.cols.split(",")]))
    factor = ref.difficulty_factor(shape.h, shape.w, args.k, args.rank)
    seconds = args.benchmark_seconds
    warmup = min(10.0, max(2.0, seconds / 5))

    log("benchmark: offline synthetic job — no pool, no wallet, no network")
    engine = Engine(shape, args.m, args.n)
    log(f"warmup {warmup:.0f}s, then {seconds:.0f}s measured at intensity 100")

    factory = GridFactory(shape, args.m, args.n)
    job = _SyntheticJob()
    bound = (1).to_bytes(32, "little")  # nothing can hit: pure sweep timing
    grid = factory.take(job)
    factory.request(job)
    engine.load_grid(grid)
    n_regions = engine.n_regions(args.region_rows)
    row_cursor = 0
    tiles = 0
    t_warm_end = time.monotonic() + warmup
    t_measure_0 = tiles_0 = t_end = None

    while True:
        now = time.monotonic()
        if t_measure_0 is None and now >= t_warm_end:
            t_measure_0, tiles_0 = now, tiles
            t_end = now + seconds
        if t_end is not None and now >= t_end:
            break
        _, n = engine.sweep_region(row_cursor, args.region_rows,
                                   grid.a_seed, bound)
        tiles += n
        row_cursor += 1
        if row_cursor >= n_regions:  # same rebuild cadence as live mining
            grid = factory.take(job)
            factory.request(job)
            engine.load_grid(grid)
            row_cursor = 0

    dt = time.monotonic() - t_measure_0
    rate = (tiles - tiles_0) / dt
    macos = platform.mac_ver()[0] or "unknown"
    today = datetime.date.today().isoformat()
    log(f"measured {rate / 1e6:.3f}M tiles/s over {dt:.0f}s on "
        f"{engine.device_name}")
    log(economics.verdict(rate, factor, engine.device_name, 100,
                          args.electricity_usd_per_kwh,
                          args.assumed_prl_price_usd,
                          args.assumed_network_hashrate)
        .replace("run init", "no economics verdict — run init"))

    # The community-hardware-table contract (C3 must match these columns):
    print(f"""
paste-ready for the community hardware table
(https://github.com/jonathanbtc/pearl-metal-miner — benchmark reports issue):

| chip | macOS | tiles/s | intensity | version | date |
| ---- | ----- | ------- | --------- | ------- | ---- |
| {engine.device_name} | {macos} | {rate / 1e6:.3f}M | 100 | {__version__} | {today} |
""")
    return 0
