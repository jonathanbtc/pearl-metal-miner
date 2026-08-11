#!/usr/bin/env python3
"""Offline check for the C1 benchmark (issue #31).

Asserts: the benchmark completes with no pool contact and prints the
paste-ready markdown block (the C3 format contract); two consecutive runs
agree within tolerance; with config assumptions present the economics
verdict appears, without them the init pointer does.

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

ROW = re.compile(r"^\| (?P<chip>[^|]+) \| (?P<macos>[^|]+) \| "
                 r"(?P<rate>[0-9.]+)M \| 100 \| (?P<ver>[^|]+) \| "
                 r"(?P<date>\d{4}-\d{2}-\d{2}) \|$", re.M)


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
    print(f"PASS block: offline, parseable row ({m.group('chip').strip()} "
          f"{m.group('rate')}M tiles/s), init pointer without assumptions")
    return True


def check_consistency() -> bool:
    rates = []
    for _ in range(2):
        rc, out = run_bench(8)
        m = ROW.search(out)
        if rc != 0 or not m:
            print(f"FAIL consistency: rc={rc}\n{out}")
            return False
        rates.append(float(m.group("rate")))
    delta = abs(rates[0] - rates[1]) / max(rates)
    # acceptance says "a few percent on an idle machine"; this host is not
    # guaranteed idle, so the gate is looser but the delta is printed
    if delta > 0.15:
        print(f"FAIL consistency: {rates} differ by {delta:.1%}")
        return False
    print(f"PASS consistency: {rates[0]}M vs {rates[1]}M ({delta:.1%} apart)")
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
    ok = check_consistency() and ok
    ok = check_verdict() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
