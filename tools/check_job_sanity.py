#!/usr/bin/env python3
"""Offline check: a bad job is refused, never a traceback.

Two sources of a bad job, both previously ending in an uncaught Python
exception on a user's screen:

  the flags   an out-of-range --m/--n/--k/--rank/--rows/--cols. Consensus
              refuses any proof outside upstream's sanity bounds, and noise
              generation needs a power-of-two rank, so a mistyped --rank ran
              the GPU flat out and could never win — nothing on screen said
              so. Now every shape is checked at startup against
              reference.validate_shape (a restatement of
              zk-pow/src/api/sanity_checks.rs), exiting 2 with the rule.

  the pool    a mining.notify carrying a wrong-length header or a
              non-positive target. Target 0 divided by zero the moment the
              job was adopted; a short header only blew up hours later, when
              a tile finally won. Job.__post_init__ rejects both at parse
              time, so the reader logs the line and the miner waits for a
              usable job.

Stdlib only; no traffic beyond loopback.

    .venv/bin/python tools/check_job_sanity.py
"""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from check_shutdown import TEST_ADDRESS, Capture, send_line  # noqa: E402

# (flags, a fragment the error message must contain)
BAD_SHAPES = [
    (["--rank", "100"], "power of two"),
    (["--rank", "16"], "power of two"),
    (["--k", "0"], "multiple of 64"),
    (["--k", "1024"], "at least 16"),
    (["--k", "131072"], "multiple of 64"),
    (["--m", "100"], "pattern period"),
    (["--n", "8193"], "pattern period"),
    (["--rows", "5,0"], "sorted"),
    (["--rows", "abc"], "whole numbers"),
    (["--cols", "0,1,2"], "multiple of 2"),
    (["--rows", "0,32", "--cols", "0,1"], "32 to 256"),
]


def check_bad_shapes() -> bool:
    """Every bad shape must exit 2 with a named rule and no traceback. These
    run without a GPU or a pool: the refusal happens before either is touched,
    which is the point — nothing is spun up for a shape that cannot win."""
    env = dict(os.environ, PRL_CONFIG=os.path.join(HERE, "_no_such_config.toml"))
    bad = []
    for flags, want in BAD_SHAPES:
        r = subprocess.run(
            [sys.executable, "-m", "pearl_metal_miner.miner", *flags,
             "--address", TEST_ADDRESS, "--time-limit", "1"],
            capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)
        text = r.stdout + r.stderr
        if r.returncode != 2:
            bad.append(f"{flags}: rc={r.returncode}, want 2")
        elif "Traceback" in text:
            bad.append(f"{flags}: traceback on screen")
        elif want not in text:
            bad.append(f"{flags}: message missing {want!r}: {text.strip()[-160:]}")
    if bad:
        print("FAIL bad-shapes: " + "; ".join(bad))
        return False
    print(f"PASS bad-shapes: {len(BAD_SHAPES)} bad shapes refused at startup, "
          f"exit 2, rule named, no traceback")
    return True


def check_default_shape_still_valid() -> bool:
    """The guard must not refuse the shape the miner actually ships with —
    nor the shapes --self-test compiles."""
    from pearl_metal_miner import reference as ref
    try:
        rows = ref.Pattern.from_list([0, 32])
        cols = ref.Pattern.from_list(list(range(64)))
        ref.validate_shape(8192, 8192, 4096, 128, rows, cols)
    except ValueError as e:
        print(f"FAIL default-shape: the shipped default was refused: {e}")
        return False
    print("PASS default-shape: the shipped 8192×8192, k=4096, rank=128 passes")
    return True


def malformed_pool(jobs: list[dict]) -> int:
    """A pool that sends the given notify params, then a usable job forever."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]

    def serve():
        while True:
            try:
                client, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=one, args=(client,), daemon=True).start()

    def one(client: socket.socket):
        try:
            buf = b""
            while b"\n" not in buf:
                chunk = client.recv(4096)
                if not chunk:
                    return
                buf += chunk
            send_line(client, {"error": None, "id": 2, "result": True})
            for params in jobs:
                send_line(client, {"method": "mining.notify", "params": params})
                time.sleep(0.5)
            n = 0
            while True:  # then a job the miner can actually mine
                n += 1
                send_line(client, {"method": "mining.notify", "params": {
                    "diff": 1, "header": "00" * 76, "height": n,
                    "job_id": f"good{n:04x}_1", "target": "01"}})
                time.sleep(2.0)
        except OSError:
            pass
        finally:
            client.close()

    threading.Thread(target=serve, daemon=True).start()
    return port


def check_malformed_jobs() -> bool:
    """A pool sending garbage must not take the miner down: each bad notify is
    logged and dropped, and the miner goes on to mine the next good job."""
    port = malformed_pool([
        {"job_id": "zerotarget_1", "header": "00" * 76, "height": 1, "target": "0"},
        {"job_id": "shorthdr_1", "header": "00" * 40, "height": 2, "target": "01"},
        {"job_id": "longhdr_1", "header": "00" * 96, "height": 3, "target": "01"},
    ])
    env = dict(os.environ, PRL_CONFIG=os.path.join(HERE, "_no_such_config.toml"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "pearl_metal_miner.miner",
         "--host", "127.0.0.1", "--port", str(port),
         "--address", TEST_ADDRESS, "--worker", "sanity",
         "--on-battery", "full", "--no-dashboard"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env)
    out, err = Capture(proc.stdout), Capture(proc.stderr)
    # The proof it survived all three: it adopted a later, good job.
    ok = out.wait_for("grid #1 ready", 180)
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(20)
    except Exception:
        proc.kill()
    text = out.text() + err.text()
    problems = []
    if not ok:
        problems.append("never reached a good job")
    if proc.returncode != 0:
        problems.append(f"rc={proc.returncode}")
    if "Traceback" in text:
        problems.append("traceback on screen")
    for want in ("target 0 is not positive", "header is 40 bytes",
                 "header is 96 bytes"):
        if want not in text:
            problems.append(f"never logged {want!r}")
    if problems:
        print(f"FAIL malformed-jobs: {'; '.join(problems)}\n{text[-2000:]}")
        return False
    print("PASS malformed-jobs: zero target and both wrong-length headers "
          "logged and dropped; the miner mined the next good job")
    return True


def main() -> int:
    signal.alarm(900)
    ok = check_default_shape_still_valid()
    ok = check_bad_shapes() and ok
    ok = check_malformed_jobs() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
