#!/usr/bin/env python3
"""Offline check for the B2 dashboard (issue #28).

Four cases, all against the loopback fake pool:

  tty        under a real pseudo-terminal the panel must appear (scroll
             region set, cursor hidden, panel fields drawn) and a Ctrl-C
             must restore the terminal: region reset, cursor shown, exit 0.
  piped      stdout a pipe → not one escape byte, logs only (the tee case).
  no-flag    --no-dashboard under a pty → no escape bytes either.
  no-color   NO_COLOR under a pty → structure yes, SGR color codes no.

Also greps the new modules' imports: stdlib only (zero new packages).

    .venv/bin/python tools/check_dashboard.py
"""

import json
import os
import pty
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from check_shutdown import fake_pool  # noqa: E402


def miner_cmd(port: int) -> list[str]:
    with open(os.path.join(ROOT, "burner_wallet.json")) as f:
        address = json.load(f)["address"]
    return [sys.executable, "-m", "pearl_metal_miner.miner",
            "--pool", "luckypool", "--host", "127.0.0.1", "--port", str(port),
            "--address", address, "--worker", "dash",
            "--m", "1024", "--n", "1024", "--time-limit", "300",
            "--on-battery", "full"]  # checks must mine on an unplugged laptop


def run_under_pty(port: int, *extra: str, env_add: dict | None = None,
                  seconds: float = 6.0) -> tuple[int, bytes]:
    master, slave = pty.openpty()
    env = dict(os.environ, **(env_add or {}))
    proc = subprocess.Popen(miner_cmd(port) + list(extra), cwd=ROOT,
                            stdout=slave, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, env=env)
    os.close(slave)
    chunks: list[bytes] = []

    def pump():
        while True:
            try:
                data = os.read(master, 65536)
            except OSError:
                return
            if not data:
                return
            chunks.append(data)

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    time.sleep(seconds)  # let it mine and paint a few frames
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(20)
    finally:
        if proc.poll() is None:
            proc.kill()
    t.join(timeout=3)
    os.close(master)
    return proc.returncode, b"".join(chunks)


def check_tty(port: int) -> bool:
    rc, out = run_under_pty(port)
    must = [(b"\x1b[1;", "scroll region set"), (b"\x1b[?25l", "cursor hidden"),
            (b"pearl-metal-miner", "panel title"), (b"status", "status line"),
            (b"tiles/s (60s)", "speed line"), (b"est.", "est-labeled ETA or placeholder"),
            (b"\x1b[r", "scroll region reset on exit"),
            (b"\x1b[?25h", "cursor restored on exit"),
            (b"session:", "summary printed after restore")]
    missing = [why for needle, why in must if needle not in out]
    if rc != 0 or missing:
        print(f"FAIL tty: rc={rc}, missing {missing}")
        return False
    if out.rfind(b"\x1b[?25h") < out.rfind(b"\x1b[?25l"):
        print("FAIL tty: cursor left hidden at exit")
        return False
    print("PASS tty: panel drawn, Ctrl-C restores region+cursor, summary after")
    return True


def check_piped(port: int) -> bool:
    proc = subprocess.Popen(miner_cmd(port), cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    time.sleep(6)
    proc.send_signal(signal.SIGINT)
    out, _ = proc.communicate(timeout=20)
    if proc.returncode != 0 or b"\x1b" in out:
        print(f"FAIL piped: rc={proc.returncode}, escape bytes: {b'\x1b' in out}")
        return False
    print("PASS piped: zero control codes — tee-able plain logs")
    return True


def check_no_dashboard_flag(port: int) -> bool:
    rc, out = run_under_pty(port, "--no-dashboard")
    if rc != 0 or b"\x1b[?25l" in out or b"\x1b[1;" in out:
        print(f"FAIL no-flag: rc={rc}, escape sequences present under --no-dashboard")
        return False
    print("PASS no-flag: --no-dashboard keeps a TTY plain")
    return True


def check_no_color(port: int) -> bool:
    rc, out = run_under_pty(port, env_add={"NO_COLOR": "1"})
    colored = any(f"\x1b[{n}m".encode() in out for n in
                  list(range(30, 38)) + list(range(90, 98)) + [1, 2])
    if rc != 0 or b"\x1b[?25l" not in out or colored:
        print(f"FAIL no-color: rc={rc}, colored={colored}")
        return False
    print("PASS no-color: structure without SGR colors")
    return True


def check_stdlib_only() -> bool:
    bad = []
    for mod in ("dashboard.py", "config.py", "notify.py", "stats.py"):
        with open(os.path.join(ROOT, "pearl_metal_miner", mod)) as f:
            for line in f:
                line = line.strip()
                if line.startswith(("import ", "from ")) and not line.startswith("from ."):
                    root_mod = line.split()[1].split(".")[0]
                    if root_mod not in (
                            "argparse", "datetime", "os", "shutil", "socket",
                            "subprocess", "sys", "threading", "time",
                            "tomllib", "collections", "__future__"):
                        bad.append(f"{mod}: {line}")
    if bad:
        print(f"FAIL stdlib: non-stdlib imports: {bad}")
        return False
    print("PASS stdlib: no imports beyond the standard library")
    return True


def main() -> int:
    signal.alarm(900)
    port = fake_pool()
    ok = check_tty(port)
    ok = check_piped(port) and ok
    ok = check_no_dashboard_flag(port) and ok
    ok = check_no_color(port) and ok
    ok = check_stdlib_only() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
