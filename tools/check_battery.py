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
  paused-cost   a paused miner dispatches nothing, so the dashboard's money
                line must charge nothing for power. It used to keep the
                pre-pause intensity and bill the full chip wattage at it.

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


def check_paused_costs_nothing(port: int) -> bool:
    """Pausing exists so an unplugged laptop stops spending. The money line
    prices power from the live intensity, so a pause that left the pre-pause
    intensity standing billed the full chip wattage for a GPU doing nothing —
    a made-up figure in the one place this project promises none."""
    name = "paused-cost"
    from check_dashboard import run_under_pty
    from check_economics import panel_money
    with tempfile.TemporaryDirectory() as d:
        shims = make_shims(d)
        set_power(shims, BATT)  # on battery from the first poll
        cfg = os.path.join(d, "config.toml")
        with open(cfg, "w") as f:
            f.write("electricity_usd_per_kwh = 0.95\n"      # loud if charged
                    "assumed_prl_price_usd = 0.26\n"
                    "assumed_network_hashrate = 28.54\n")
        # COLUMNS so the panel does not truncate the tail of the money line
        # (a pty reports no size, and the 80-column fallback cuts it).
        env = dict(shims["env"], PRL_CONFIG=cfg, COLUMNS="200", LINES="40")
        # run_under_pty's command ends in `--on-battery full`; a later
        # occurrence wins in argparse, so this run is a real pause.
        rc, out = run_under_pty(port, "--on-battery", "pause",
                                env_add=env, seconds=8.0)
    money = panel_money(out)
    text = out.decode(errors="replace")
    if rc != 0 or "pausing" not in text:
        print(f"FAIL {name}: rc={rc}, never paused\n{text[-2000:]}")
        return False
    if "$0.00 power" not in money or "est. 0 W" not in money:
        print(f"FAIL {name}: paused run still billed for power: {money!r}")
        return False
    print(f"PASS {name}: paused run charges nothing ({money!r})")
    return True


def main() -> int:
    signal.alarm(900)
    port = fake_pool()
    ok = check_pause_resume(port)
    ok = check_full(port) and ok
    ok = check_desktop(port) and ok
    ok = check_paused_costs_nothing(port) and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
