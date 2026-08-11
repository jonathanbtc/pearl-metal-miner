#!/usr/bin/env python3
"""Offline check for the B3 battery behavior (issue #29).

`pmset` is shimmed via PATH to read a state file, so the "battery" can be
unplugged and replugged mid-run against the real miner and the loopback
fake pool; `osascript` is shimmed as in check_notify.py to record toasts.

  pause-resume  unplug → "pausing" within 30 s, sweeping stops, toast;
                replug → resumes by itself, sweeping restarts, toast.
  full          unplug under --on-battery full → exactly one warning,
                mining continues.
  desktop       power stays AC → zero battery-related output.

    .venv/bin/python tools/check_battery.py
"""

import os
import signal
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
import sys  # noqa: E402
sys.path.insert(0, HERE)

from check_shutdown import Capture, fake_pool, start_miner  # noqa: E402

AC = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=123)\t100%; charged\n"
BATT = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=123)\t95%; discharging\n"


def make_shims(d: str) -> dict:
    power_file = os.path.join(d, "power_state")
    with open(power_file, "w") as f:
        f.write(AC)
    with open(os.path.join(d, "pmset"), "w") as f:
        f.write(f'#!/bin/sh\ncat "{power_file}"\n')
    toast_file = os.path.join(d, "toasts.log")
    with open(os.path.join(d, "osascript"), "w") as f:
        f.write(f'#!/bin/sh\nprintf \'%s\\n\' "$2" >> "{toast_file}"\n')
    os.chmod(os.path.join(d, "pmset"), 0o755)
    os.chmod(os.path.join(d, "osascript"), 0o755)
    env = dict(os.environ, PATH=d + os.pathsep + os.environ["PATH"])
    return {"env": env, "power_file": power_file, "toast_file": toast_file}


def set_power(shims: dict, text: str):
    with open(shims["power_file"], "w") as f:
        f.write(text)


def toasts(shims: dict) -> list[str]:
    if not os.path.exists(shims["toast_file"]):
        return []
    with open(shims["toast_file"]) as f:
        return f.read().splitlines()


def tiles_line_count(cap: Capture) -> int:
    return sum(1 for ln in cap.lines if "ready in" in ln)


def check_pause_resume(port: int) -> bool:
    name = "pause-resume"
    with tempfile.TemporaryDirectory() as d:
        shims = make_shims(d)
        proc = start_miner(port, "--on-battery", "pause", env=shims["env"])
        out, err = Capture(proc.stdout), Capture(proc.stderr)
        try:
            if not out.wait_for("grid #1 ready", 120):
                print(f"FAIL {name}: never mined\n{out.text()}\n{err.text()}")
                return False
            set_power(shims, BATT)
            if not out.wait_for("pausing", 35):
                print(f"FAIL {name}: no pause within ~30 s of unplug\n{out.text()}")
                return False
            n_paused = tiles_line_count(out)
            time.sleep(25)  # a full poll cycle: sweeping must NOT advance
            if tiles_line_count(out) != n_paused:
                print(f"FAIL {name}: grids kept building while paused")
                return False
            set_power(shims, AC)
            if not out.wait_for("back on AC — resuming", 35):
                print(f"FAIL {name}: no auto-resume on replug\n{out.text()}")
                return False
            deadline = time.time() + 30
            while tiles_line_count(out) <= n_paused and time.time() < deadline:
                time.sleep(0.5)
            if tiles_line_count(out) <= n_paused:
                print(f"FAIL {name}: no fresh grids after resume\n{out.text()}")
                return False
            proc.send_signal(signal.SIGINT)
            proc.wait(20)
        finally:
            if proc.poll() is None:
                proc.kill()
        t = toasts(shims)
        want_pause = 'display notification "Paused — on battery" with title "Pearl miner"'
        want_resume = 'display notification "Resuming — on AC power" with title "Pearl miner"'
        if want_pause not in t or want_resume not in t:
            print(f"FAIL {name}: toasts missing: {t!r}")
            return False
    print(f"PASS {name}: paused within poll, no sweeping while paused, "
          f"auto-resumed, both toasts sent")
    return True


def check_full(port: int) -> bool:
    name = "full"
    with tempfile.TemporaryDirectory() as d:
        shims = make_shims(d)
        set_power(shims, BATT)  # on battery from the start
        proc = start_miner(port, "--on-battery", "full", env=shims["env"])
        out = Capture(proc.stdout)
        Capture(proc.stderr)  # drained: a full stderr pipe would stall the child
        try:
            ok = (out.wait_for("grid #1 ready", 120)
                  and out.wait_for("mining at full intensity anyway", 35))
            n = tiles_line_count(out)
            time.sleep(8)
            still_mining = tiles_line_count(out) > n
            proc.send_signal(signal.SIGINT)
            proc.wait(20)
        finally:
            if proc.poll() is None:
                proc.kill()
        o = out.text()
        warnings = o.count("mining at full intensity anyway")
        if not ok or not still_mining or warnings != 1:
            print(f"FAIL {name}: ok={ok} mining={still_mining} "
                  f"warnings={warnings}\n{o}")
            return False
    print(f"PASS {name}: mines on battery with exactly one warning")
    return True


def check_desktop(port: int) -> bool:
    name = "desktop"
    with tempfile.TemporaryDirectory() as d:
        shims = make_shims(d)  # stays AC for the whole run
        proc = start_miner(port, "--on-battery", "pause", env=shims["env"])
        out = Capture(proc.stdout)
        Capture(proc.stderr)  # drained: a full stderr pipe would stall the child
        try:
            out.wait_for("grid #1 ready", 120)
            time.sleep(25)  # cross a poll boundary
            proc.send_signal(signal.SIGINT)
            proc.wait(20)
        finally:
            if proc.poll() is None:
                proc.kill()
        o = out.text()
        if "battery" in o.lower() or toasts(shims):
            print(f"FAIL {name}: battery chatter on AC-only power\n{o}")
            return False
    print(f"PASS {name}: on AC, zero battery-related output")
    return True


def main() -> int:
    signal.alarm(900)
    port = fake_pool()
    ok = check_pause_resume(port)
    ok = check_full(port) and ok
    ok = check_desktop(port) and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
