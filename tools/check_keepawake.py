#!/usr/bin/env python3
"""Check for the A5 --keep-awake flag (issue #24).

With the flag, a `caffeinate` child of the miner must hold a real sleep
assertion (visible in `pmset -g assertions`) while mining, and both the
process and the assertion must be gone after a Ctrl-C exit. Without the
flag, the miner must have no caffeinate child at all.

    .venv/bin/python tools/check_keepawake.py
"""

import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from check_shutdown import Capture, fake_pool, start_miner  # noqa: E402


def caffeinate_children(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid), "caffeinate"],
                         capture_output=True, text=True).stdout
    return [int(x) for x in out.split()]


def assertion_lines(cpid: int) -> list[str]:
    out = subprocess.run(["pmset", "-g", "assertions"],
                         capture_output=True, text=True).stdout
    return [ln for ln in out.splitlines() if f"pid {cpid}(caffeinate)" in ln]


def check_with_flag(port: int) -> bool:
    name = "keep-awake"
    proc = start_miner(port, "--keep-awake")
    out, err = Capture(proc.stdout), Capture(proc.stderr)
    try:
        if not out.wait_for("grid #1 ready", 120):
            print(f"FAIL {name}: never mined\n{out.text()}\n{err.text()}")
            return False
        kids = caffeinate_children(proc.pid)
        if len(kids) != 1:
            print(f"FAIL {name}: expected one caffeinate child, got {kids}")
            return False
        held = assertion_lines(kids[0])
        if not any("PreventUserIdleSystemSleep" in ln for ln in held):
            print(f"FAIL {name}: no sleep assertion for pid {kids[0]}: {held}")
            return False
        proc.send_signal(signal.SIGINT)
        proc.wait(20)
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0 or "Traceback" in out.text() + err.text():
        print(f"FAIL {name}: dirty exit rc={proc.returncode}\n{err.text()}")
        return False
    deadline = time.time() + 10
    while time.time() < deadline:
        if not caffeinate_children(proc.pid) and not assertion_lines(kids[0]):
            print(f"PASS {name}: assertion held while mining "
                  f"(pid {kids[0]}), released after Ctrl-C")
            return True
        time.sleep(0.5)
    print(f"FAIL {name}: caffeinate or its assertion outlived the miner")
    return False


def check_without_flag(port: int) -> bool:
    name = "no-flag"
    proc = start_miner(port)
    out, err = Capture(proc.stdout), Capture(proc.stderr)
    try:
        if not out.wait_for("grid #1 ready", 120):
            print(f"FAIL {name}: never mined\n{out.text()}\n{err.text()}")
            return False
        kids = caffeinate_children(proc.pid)
        if kids:
            print(f"FAIL {name}: unexpected caffeinate child {kids}")
            return False
        proc.send_signal(signal.SIGINT)
        proc.wait(20)
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0:
        print(f"FAIL {name}: rc={proc.returncode}")
        return False
    print(f"PASS {name}: no caffeinate child, behavior as before")
    return True


def main() -> int:
    signal.alarm(600)
    port = fake_pool()
    ok = check_with_flag(port)
    ok = check_without_flag(port) and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
