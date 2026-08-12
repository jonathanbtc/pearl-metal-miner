#!/usr/bin/env python3
"""Offline check for the C1 benchmark (issue #31).

Asserts: the benchmark completes with no pool contact and prints the
paste-ready markdown block (the C3 format contract); the number in that
block is the one the run measured, over the window it was asked for, and
carries the power source it was measured on (AC vs battery is worth ~15%,
so a row without it can be wrong by more than the differences the table
exists to show); with config assumptions present the economics verdict
appears, without them the init pointer does.

Deliberately NOT asserted: that two runs agree closely. That is a property
of the host — thermals, other load, AC vs battery — not of this code, and
gating on it made the check fail on busy machines and CI runners. The two
rates are still measured and printed, because a wildly divergent pair is
worth a human's eye; only the code's own arithmetic is a hard gate.

    .venv/bin/python tools/check_benchmark.py
"""

import os
import re
import signal
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from pearl_metal_miner.miner import power_source  # noqa: E402

ROW = re.compile(r"^\| (?P<chip>[^|]+) \| (?P<macos>[^|]+) \| "
                 r"(?P<rate>[0-9.]+)M \| 100 \| (?P<power>AC|battery) \| "
                 r"(?P<ver>[^|]+) \| (?P<date>\d{4}-\d{2}-\d{2}) \|$", re.M)


def run_bench(seconds: float, cfg: str | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    if cfg is not None:
        env["PRL_CONFIG"] = cfg
    r = subprocess.run(
        [sys.executable, "-m", "pearl_metal_miner.miner", "--benchmark",
         "--benchmark-seconds", str(seconds)],
        capture_output=True, text=True, cwd=ROOT, env=env, timeout=300)
    return r.returncode, r.stdout + r.stderr


def check_block_and_offline() -> bool:
    with tempfile.TemporaryDirectory() as d:  # no config: pointer expected
        rc, out = run_bench(4, cfg=os.path.join(d, "none.toml"))
    m = ROW.search(out)
    if rc != 0 or not m:
        print(f"FAIL block: rc={rc}, no parseable table row\n{out}")
        return False
    if "connecting to" in out or "wallet" in out.lower().replace(
            "no pool, no wallet", ""):
        print(f"FAIL block: touched pool or wallet\n{out}")
        return False
    if "run init" not in out:
        print(f"FAIL block: missing init pointer without assumptions\n{out}")
        return False
    want_power = "AC" if power_source() == "ac" else "battery"
    if m.group("power") != want_power:
        print(f"FAIL block: row says power {m.group('power')}, this host is "
              f"on {want_power}")
        return False
    print(f"PASS block: offline, parseable row ({m.group('chip').strip()} "
          f"{m.group('rate')}M tiles/s on {want_power}), init pointer "
          f"without assumptions")
    return True


MEASURED = re.compile(r"measured (?P<rate>[0-9.]+)M tiles/s over (?P<secs>\d+)s")


def check_reported_rate() -> bool:
    """The hard gate: whatever the run measured is what it publishes, and it
    measured the window it was asked for (not the warmup, not the whole run)."""
    rates = []
    for seconds in (8, 8):
        rc, out = run_bench(seconds)
        row, meas = ROW.search(out), MEASURED.search(out)
        if rc != 0 or not row or not meas:
            print(f"FAIL rate: rc={rc}, row={bool(row)}, measured={bool(meas)}\n{out}")
            return False
        if row.group("rate") != meas.group("rate"):
            print(f"FAIL rate: paste block says {row.group('rate')}M but the run "
                  f"measured {meas.group('rate')}M")
            return False
        # warmup is min(10, max(2, s/5)); the measured window is `seconds`
        if abs(int(meas.group("secs")) - seconds) > 1:
            print(f"FAIL rate: asked for {seconds}s, measured over "
                  f"{meas.group('secs')}s")
            return False
        rate = float(row.group("rate"))
        if rate <= 0:
            print(f"FAIL rate: non-positive rate {rate}M")
            return False
        rates.append(rate)
    delta = abs(rates[0] - rates[1]) / max(rates)
    print(f"PASS rate: published == measured, over the requested window "
          f"({rates[0]}M then {rates[1]}M, {delta:.1%} apart — host noise, "
          f"not a gate)")
    return True


def check_verdict() -> bool:
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "config.toml")
        with open(cfg, "w") as f:
            f.write("electricity_usd_per_kwh = 0.20\n"
                    "assumed_prl_price_usd = 0.26\n"
                    "assumed_network_hashrate = 28.54\n")
        rc, out = run_bench(4, cfg=cfg)
    if rc != 0 or "at your assumptions" not in out or "est." not in out:
        print(f"FAIL verdict: rc={rc}\n{out}")
        return False
    print("PASS verdict: economics verdict appears with configured assumptions")
    return True


def main() -> int:
    signal.alarm(900)
    ok = check_block_and_offline()
    ok = check_reported_rate() and ok
    ok = check_verdict() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
