#!/usr/bin/env python3
"""Offline check for the A2 rate numbers (issue #21).

Part one is deterministic: drive RateMeter through an intensity step on a
fake clock and assert the rolling window tracks the change within a minute
while the session average keeps its lifetime meaning. Part two is a live
smoke: the real miner against the loopback fake pool from
check_shutdown.py, long enough to catch one 30 s heartbeat, asserting the
new fields and that the A1 exit contract still holds.

    .venv/bin/python tools/check_stats.py
"""

import os
import signal
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from check_shutdown import Capture, fake_pool, start_miner  # noqa: E402
from pearl_metal_miner.stats import RateMeter, fmt_uptime  # noqa: E402


def check_meter() -> bool:
    clock = [0.0]
    m = RateMeter(window_s=60.0, now=lambda: clock[0])

    def run(seconds, tiles_per_s):
        for _ in range(seconds):
            clock[0] += 1.0
            m.add(tiles_per_s)

    run(100, 1000)  # steady full intensity
    assert abs(m.rolling() - 1000.0) < 1e-9, m.rolling()
    assert abs(m.average() - 1000.0) < 1e-9, m.average()

    run(30, 100)  # intensity drops 10×; half a window later the blend shows
    assert abs(m.rolling() - (30 * 1000 + 30 * 100) / 60) < 1e-9, m.rolling()

    run(30, 100)  # a full window after the change, the old rate is gone
    assert abs(m.rolling() - 100.0) < 1e-9, m.rolling()
    expected_avg = (100 * 1000 + 60 * 100) / 160
    assert abs(m.average() - expected_avg) < 1e-9, m.average()
    assert m.total == 100 * 1000 + 60 * 100

    assert fmt_uptime(3) == "0:00:03"
    assert fmt_uptime(3723) == "1:02:03"
    print("PASS meter: rolling tracks a rate step within one window, "
          "average keeps its lifetime meaning")
    return True


def check_heartbeat() -> bool:
    port = fake_pool()
    proc = start_miner(port)
    out, err = Capture(proc.stdout), Capture(proc.stderr)
    seen = out.wait_for("tiles/s (60s)", 150)  # first heartbeat ~30 s in
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(20)
    except Exception:
        proc.kill()
    o, e = out.text(), err.text()
    if not seen:
        print(f"FAIL heartbeat: none within 150 s\n{o}\n{e}")
        return False
    beat = next(line for line in o.splitlines() if "tiles/s (60s)" in line)
    for needle in ("M/s session", "acc", "rej", "| up 0:"):
        if needle not in beat:
            print(f"FAIL heartbeat: {needle!r} missing from {beat!r}")
            return False
    if proc.returncode != 0 or "session:" not in o or "Traceback" in o + e:
        print(f"FAIL heartbeat: A1 exit contract broken (rc={proc.returncode})"
              f"\n{o}\n{e}")
        return False
    print(f"PASS heartbeat: {beat.strip()}")
    return True


def main() -> int:
    signal.alarm(600)
    ok = check_meter()
    ok = check_heartbeat() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
