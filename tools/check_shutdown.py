#!/usr/bin/env python3
"""Offline acceptance check for the designed exit (issue #20).

Runs the real miner against a throwaway fake pool on 127.0.0.1 speaking the
LuckyPool line format — a fresh impossible-target job every 2 s, so the miner
sweeps and logs but never submits — then stops it three ways and asserts the
contract:

  SIGINT (Ctrl-C)      exit code 0, session summary printed, no traceback
  SIGTERM              exit code 0, session summary printed, no traceback
  stdout pipe closes   exit code 0, no traceback (summary has nowhere to go)

Stdlib only; no traffic beyond loopback. Run from a working checkout:

    .venv/bin/python tools/check_shutdown.py
"""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIFY_EVERY_S = 2.0  # keeps the miner printing, so a closed pipe is felt fast
START_TIMEOUT_S = 120  # first job adopted (includes Metal pipeline compile)
EXIT_TIMEOUT_S = 20

AUTH_ACK = {"error": None, "id": 2, "result": True, "type": "plain"}


def notify(n: int) -> dict:
    # target 1 → bound ≈ 2^-256 of tile space: the sweep never finds a hit,
    # so nothing is ever submitted, not even to this fake pool.
    return {"method": "mining.notify",
            "params": {"diff": 1, "header": "00" * 76, "height": n,
                       "job_id": f"cafe{n:04x}_1", "target": "01"}}


def send_line(sock: socket.socket, msg: dict):
    sock.sendall(json.dumps(msg, separators=(",", ":")).encode() + b"\n")


def serve_client(client: socket.socket):
    try:
        buf = b""
        while b"\n" not in buf:  # the authorize line
            chunk = client.recv(4096)
            if not chunk:
                return
            buf += chunk
        send_line(client, AUTH_ACK)
        n = 1
        while True:
            send_line(client, notify(n))
            n += 1
            time.sleep(NOTIFY_EVERY_S)
    except OSError:
        pass
    finally:
        client.close()


def fake_pool() -> int:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)

    def accept_loop():
        while True:
            try:
                client, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=serve_client, args=(client,),
                             daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    return srv.getsockname()[1]


def start_miner(port: int, *extra: str) -> subprocess.Popen:
    with open(os.path.join(ROOT, "burner_wallet.json")) as f:
        address = json.load(f)["address"]
    cmd = [sys.executable, "-m", "pearl_metal_miner.miner",
           "--pool", "luckypool", "--host", "127.0.0.1", "--port", str(port),
           "--address", address, "--worker", "check",
           "--m", "1024", "--n", "1024",
           "--time-limit", "300",  # orphan failsafe; every case stops it sooner
           *extra]
    return subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


class Capture:
    def __init__(self, stream):
        self.lines: list[str] = []
        self.stream = stream
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self):
        for line in self.stream:
            self.lines.append(line)

    def wait_for(self, needle: str, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if any(needle in line for line in self.lines):
                return True
            time.sleep(0.05)
        return False

    def text(self) -> str:
        self.thread.join(timeout=2)
        return "".join(self.lines)


def fail(name: str, why: str, out: str, err: str) -> bool:
    print(f"FAIL {name}: {why}\n----- stdout -----\n{out}\n"
          f"----- stderr -----\n{err}\n------------------")
    return False


def check_signal_exit(port: int, name: str, sig: signal.Signals) -> bool:
    proc = start_miner(port)
    out, err = Capture(proc.stdout), Capture(proc.stderr)
    try:
        if not out.wait_for("grid #1 ready", START_TIMEOUT_S):
            return fail(name, "never adopted a job", out.text(), err.text())
        time.sleep(1.0)  # let it sweep a little first
        proc.send_signal(sig)
        proc.wait(EXIT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return fail(name, "did not exit after signal", out.text(), err.text())
    finally:
        if proc.poll() is None:
            proc.kill()
    o, e = out.text(), err.text()
    if proc.returncode != 0:
        return fail(name, f"exit code {proc.returncode}, wanted 0", o, e)
    if "session:" not in o:
        return fail(name, "no session summary printed", o, e)
    if "Traceback" in o or "Traceback" in e:
        return fail(name, "traceback in output", o, e)
    print(f"PASS {name}: exit 0, summary printed, no traceback")
    return True


def check_broken_pipe(port: int) -> bool:
    name = "broken-pipe"
    proc = start_miner(port)
    err = Capture(proc.stderr)
    try:
        deadline = time.time() + START_TIMEOUT_S
        for line in proc.stdout:  # notifies arrive every 2 s, so this moves
            if "grid #1 ready" in line or time.time() > deadline:
                break
        proc.stdout.close()  # the reading side walks away, as `| head` would
        proc.wait(EXIT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return fail(name, "did not exit after stdout closed", "<closed>",
                    err.text())
    finally:
        if proc.poll() is None:
            proc.kill()
    e = err.text()
    if proc.returncode != 0:
        return fail(name, f"exit code {proc.returncode}, wanted 0", "<closed>", e)
    if "Traceback" in e:
        return fail(name, "traceback on stderr", "<closed>", e)
    print(f"PASS {name}: exit 0, no traceback after stdout vanished")
    return True


def main() -> int:
    signal.alarm(600)  # whole-script watchdog: a hang is a failure, not a wait
    port = fake_pool()
    ok = check_signal_exit(port, "SIGINT", signal.SIGINT)
    ok = check_signal_exit(port, "SIGTERM", signal.SIGTERM) and ok
    ok = check_broken_pipe(port) and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
