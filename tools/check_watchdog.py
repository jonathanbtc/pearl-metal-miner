#!/usr/bin/env python3
"""Offline check for the A3 watchdog and reconnect backoff (issue #22).

Two loopback scenarios against the real miner:

  silent pool   accepts TCP and says nothing. The watchdog must fire at
                --max-job-age, force a fresh session, and the second
                connection (which behaves) must resume mining.

  dead network  a behaving pool drops the miner and its port stays closed.
                The log must show numbered attempts with growing gaps
                (5 s, 10 s, 20 s…); once the port comes back the miner must
                resume and the exit summary must count the outage.

    .venv/bin/python tools/check_watchdog.py
"""

import os
import signal
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from check_shutdown import (  # noqa: E402
    AUTH_ACK, Capture, NOTIFY_EVERY_S, notify, send_line, serve_client,
    start_miner)


def listener() -> socket.socket:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    return srv


def check_silent_pool() -> bool:
    name = "silent-pool"
    srv = listener()
    port = srv.getsockname()[1]
    clients: list[socket.socket] = []

    def accept_loop():
        while True:
            try:
                client, _ = srv.accept()
            except OSError:
                return
            clients.append(client)
            if len(clients) == 1:
                continue  # first session: accept TCP, say nothing at all
            threading.Thread(target=serve_client, args=(client,),
                             daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    proc = start_miner(port, "--max-job-age", "6")
    out, err = Capture(proc.stdout), Capture(proc.stderr)
    ok = (out.wait_for("WATCHDOG", 60)
          and out.wait_for("reconnect attempt 1 in 5s", 30)
          and out.wait_for("grid #1 ready", 60))
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(20)
    except Exception:
        proc.kill()
    srv.close()
    o, e = out.text(), err.text()
    if not ok:
        print(f"FAIL {name}: watchdog/reconnect/resume sequence not seen\n{o}\n{e}")
        return False
    if proc.returncode != 0 or "Traceback" in o + e:
        print(f"FAIL {name}: dirty exit (rc={proc.returncode})\n{o}\n{e}")
        return False
    print(f"PASS {name}: watchdog fired, second session mined "
          f"({len(clients)} connections served)")
    return True


def check_dead_network() -> bool:
    name = "dead-network"
    srv = listener()
    port = srv.getsockname()[1]

    def serve_then_die():
        client, _ = srv.accept()
        try:
            buf = b""
            while b"\n" not in buf:
                buf += client.recv(4096) or b"\r\n"
            send_line(client, AUTH_ACK)
            for n in range(1, 3):
                send_line(client, notify(n))
                time.sleep(NOTIFY_EVERY_S)
        except OSError:
            pass
        client.close()
        srv.close()  # the whole port goes away: connects now refuse

    threading.Thread(target=serve_then_die, daemon=True).start()
    proc = start_miner(port)
    out, err = Capture(proc.stdout), Capture(proc.stderr)

    def after_marker(marker: str, needle: str, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            txt = "".join(out.lines)
            if marker in txt and needle in txt.split(marker, 1)[1]:
                return True
            time.sleep(0.1)
        return False

    # Attempts 1 (5 s) and 2 (10 s) hit a closed port. The port comes back
    # only after attempt 2 has FAILED, so attempt 3 (20 s gap) must succeed.
    ok = (out.wait_for("grid #1 ready", 60)
          and out.wait_for("reconnect attempt 1 in 5s", 60)
          and out.wait_for("reconnect attempt 2 in 10s", 30)
          and out.wait_for("attempt 2: ", 30))
    revived = None
    while revived is None:
        try:
            revived = socket.socket()
            revived.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            revived.bind(("127.0.0.1", port))
            revived.listen(4)
        except OSError:
            revived = None
            time.sleep(0.5)

    def accept_loop():
        while True:
            try:
                client, _ = revived.accept()
            except OSError:
                return
            threading.Thread(target=serve_client, args=(client,),
                             daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    ok = (ok and out.wait_for("reconnect attempt 3 in 20s", 30)
          and out.wait_for("reconnected on attempt 3", 60)
          and out.wait_for("waiting for a job", 10)
          and after_marker("reconnected on attempt 3", "ready in", 30))
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(20)
    except Exception:
        proc.kill()
    revived.close()
    o, e = out.text(), err.text()
    if not ok:
        print(f"FAIL {name}: backoff/resume sequence not seen\n{o}\n{e}")
        return False
    if "connection lost 1×, reconnected 1×" not in o:
        print(f"FAIL {name}: outage missing from summary\n{o}")
        return False
    if proc.returncode != 0 or "Traceback" in o + e:
        print(f"FAIL {name}: dirty exit (rc={proc.returncode})\n{o}\n{e}")
        return False
    print(f"PASS {name}: numbered attempts with growing gaps, resumed, "
          f"outage counted in summary")
    return True


def main() -> int:
    signal.alarm(600)
    ok = check_silent_pool()
    ok = check_dead_network() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
