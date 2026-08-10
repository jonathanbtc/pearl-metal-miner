"""Pool survey: connect, handshake, log both directions verbatim.

Throwaway by design. Submits nothing. The address used for
authorize is the example address printed in ascend_prl's README (format-valid);
no shares are ever sent, so nothing is credited or debited anywhere.

Usage: python tools/pool_survey.py [seconds_per_pool]
"""

import json
import socket
import sys
import time

ADDR = "prl1p2skcz8kxn03p3j2hzaz4j687ewan8deju7lgvpswux9hkgavcz5s6v5p83"
WORKER = "survey"
AGENT = "pearl-metal-miner/0.0-survey"

POOLS = [
    # (label, host, port, handshake lines)
    ("luckypool:3360", "pearl-eu1.luckypool.io", 3360, [
        {"id": 1, "method": "mining.subscribe", "params": [AGENT]},
        {"id": 2, "method": "mining.authorize", "params": [f"{ADDR}.{WORKER}", "x"]},
    ]),
    ("kryptex:7048", "prl-eu.kryptex.network", 7048, [
        {"id": 1, "method": "mining.subscribe", "params": [AGENT]},
        {"id": 3, "method": "mining.authorize", "params": [f"{ADDR}.{WORKER}", "x"]},
    ]),
    ("k1pool:5566", "eu.pearl.k1pool.com", 5566, [
        {"id": 1, "method": "mining.subscribe", "params": [AGENT]},
        {"id": 3, "method": "mining.authorize",
         "params": {"wallet": ADDR, "worker": WORKER, "agent": AGENT}},
    ]),
]

PROBES = [
    ("luckypool cpu-eu1:3370 (undocumented)", "pearl-cpu-eu1.luckypool.io", 3370),
]


def survey(label, host, port, lines, listen_s):
    print(f"\n════════ {label} — {host}:{port} ════════")
    try:
        s = socket.create_connection((host, port), timeout=10)
    except OSError as e:
        print(f"[connect] FAILED: {e}")
        return
    print(f"[connect] ok ({s.getpeername()})")
    s.settimeout(listen_s)
    try:
        for msg in lines:
            raw = json.dumps(msg, separators=(",", ":"))
            s.sendall(raw.encode() + b"\n")
            print(f">>> {raw}")
        buf = b""
        t_end = time.time() + listen_s
        while time.time() < t_end:
            s.settimeout(max(0.5, t_end - time.time()))
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                print("[conn] closed by pool")
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode(errors="replace")
                print(f"<<< {text[:1200]}")
    finally:
        s.close()


def probe(label, host, port):
    print(f"\n──── probe {label} — {host}:{port} ────")
    try:
        s = socket.create_connection((host, port), timeout=8)
        print(f"[connect] ok ({s.getpeername()}) — endpoint exists")
        s.close()
    except OSError as e:
        print(f"[connect] failed: {e}")


if __name__ == "__main__":
    listen_s = float(sys.argv[1]) if len(sys.argv) > 1 else 15
    for label, host, port, lines in POOLS:
        survey(label, host, port, lines, listen_s)
    for label, host, port in PROBES:
        probe(label, host, port)
