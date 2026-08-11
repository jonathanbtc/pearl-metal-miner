#!/usr/bin/env python3
"""Offline check for the A4 notifications (issue #23).

Unit part drives Notifier directly: coalescing on a fake clock, AppleScript
escaping, a missing osascript logs once and never raises, disabled = no-op.

Integration part is the first check to exercise the whole submit path: the
fake pool hands out an EASY target (every tile wins), the real miner finds
real shares, verifies them locally, submits, the pool accepts them all, and
`osascript` — shimmed via PATH into a file recorder — must have been asked
for exactly ONE toast (the burst coalesces; the body carries the total).
A --no-notify run must record none.

    .venv/bin/python tools/check_notify.py
"""

import json
import os
import signal
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from check_shutdown import AUTH_ACK, Capture, notify, send_line, start_miner  # noqa: E402
from pearl_metal_miner.notify import Notifier  # noqa: E402


def check_unit() -> bool:
    import pearl_metal_miner.notify as mod
    real_run = mod.subprocess.run
    calls: list[str] = []
    logs: list[str] = []
    try:
        mod.subprocess.run = lambda argv, **kw: calls.append(argv[-1])
        clock = [0.0]
        n = Notifier(enabled=True, log=logs.append, now=lambda: clock[0])
        n.send("Pearl miner", 'total "1"')   # sent
        clock[0] = 1.0
        n.send("Pearl miner", "total 2")     # coalesced away
        clock[0] = 5.0
        n.send("Pearl miner", "total 3")     # sent
        off = Notifier(enabled=False, log=logs.append, now=lambda: clock[0])
        off.send("x", "y")                   # no-op
        time.sleep(0.3)
        assert len(calls) == 2, calls
        assert calls[0] == 'display notification "total \\"1\\"" with title "Pearl miner"', calls
        assert not logs

        def boom(argv, **kw):
            raise FileNotFoundError("no osascript")
        mod.subprocess.run = boom
        clock[0] = 10.0
        n.send("t", "b")
        clock[0] = 20.0
        n.send("t", "b")
        time.sleep(0.3)
        assert len(logs) == 1 and "notifications unavailable" in logs[0], logs
    finally:
        mod.subprocess.run = real_run
    print("PASS unit: coalescing, escaping, log-once failure, no-op when off")
    return True


def easy_target_hex() -> str:
    from pearl_metal_miner import reference as ref
    rows = ref.Pattern.from_list([0, 32])
    cols = ref.Pattern.from_list(list(range(64)))
    factor = ref.difficulty_factor(rows.size(), cols.size(), 4096, 128)
    return f"{(1 << 256) // factor - 1:x}"  # bound just under 2^256: all tiles win


def accepting_pool(target_hex: str) -> int:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)

    def serve(client: socket.socket):
        try:
            buf = b""
            while b"\n" not in buf:
                chunk = client.recv(4096)
                if not chunk:
                    return
                buf += chunk
            send_line(client, AUTH_ACK)
            job = notify(1)
            job["params"]["target"] = target_hex
            send_line(client, job)
            buf = b""
            while True:  # accept every submitted share
                chunk = client.recv(65536)
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = json.loads(line)
                    if msg.get("method") == "mining.submit":
                        send_line(client, {"error": None, "id": msg["id"],
                                           "result": True, "type": "plain"})
        except OSError:
            pass
        finally:
            client.close()

    def accept_loop():
        while True:
            try:
                client, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=serve, args=(client,), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    return srv.getsockname()[1]


def run_easy_miner(record_dir: str, *extra: str):
    shim = os.path.join(record_dir, "osascript")
    record = os.path.join(record_dir, "toasts.log")
    with open(shim, "w") as f:
        f.write(f'#!/bin/sh\nprintf \'%s\\n\' "$2" >> "{record}"\n')
    os.chmod(shim, 0o755)
    env = dict(os.environ, PATH=record_dir + os.pathsep + os.environ["PATH"])
    port = accepting_pool(easy_target_hex())
    proc = start_miner(port, "--m", "64", "--n", "64", "--region-rows", "32",
                       "--max-accepted", "1", *extra, env=env)
    out, err = Capture(proc.stdout), Capture(proc.stderr)
    try:
        proc.wait(180)
    except Exception:
        proc.send_signal(signal.SIGINT)
        proc.kill()
    toasts = []
    if os.path.exists(record):
        with open(record) as f:
            toasts = f.read().splitlines()
    return proc.returncode, out.text(), err.text(), toasts


def check_accepted_share() -> bool:
    with tempfile.TemporaryDirectory() as d:
        rc, o, e, toasts = run_easy_miner(d)
    if rc != 0 or "Traceback" in o + e:
        print(f"FAIL accepted-share: dirty exit rc={rc}\n{o}\n{e}")
        return False
    if "share ACCEPTED" not in o or "accepted-share target reached" not in o:
        print(f"FAIL accepted-share: no accepted share end-to-end\n{o}\n{e}")
        return False
    if toasts != ['display notification "Share accepted — total 1" '
                  'with title "Pearl miner"']:
        print(f"FAIL accepted-share: expected exactly one coalesced toast, "
              f"got {toasts!r}\n{o}")
        return False
    print(f"PASS accepted-share: real share accepted end-to-end, "
          f"one coalesced toast: {toasts[0]!r}")
    return True


def check_no_notify() -> bool:
    with tempfile.TemporaryDirectory() as d:
        rc, o, e, toasts = run_easy_miner(d, "--no-notify")
    if rc != 0 or "share ACCEPTED" not in o:
        print(f"FAIL no-notify: run did not complete cleanly rc={rc}\n{o}\n{e}")
        return False
    if toasts:
        print(f"FAIL no-notify: toasts recorded despite flag: {toasts!r}")
        return False
    print("PASS no-notify: shares accepted, zero toasts")
    return True


def main() -> int:
    signal.alarm(600)
    ok = check_unit()
    ok = check_accepted_share() and ok
    ok = check_no_notify() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
