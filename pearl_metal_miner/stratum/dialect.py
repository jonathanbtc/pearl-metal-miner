"""The dialect seam (ADR-0006): Pearl pools do not share one Stratum wire
format, so everything pool-specific — handshake, notify parsing, submit
framing, target normalisation, who chooses the mining parameters — lives
behind this interface, one module per pool.

Shared plumbing here: line-framed JSON over TCP with a reader thread and an
event queue the mining loop drains.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
from dataclasses import dataclass, field

_RAW = bool(os.environ.get("PRL_RAW"))


@dataclass
class Job:
    job_id: str
    header_bytes: bytes          # the 76-byte IncompleteBlockHeader wire form
    target: int                  # pool base target as an integer (pre-factor)
    height: int = 0
    cert_version: int = 2
    received_at: float = field(default_factory=time.time)


@dataclass
class ShareResult:
    msg_id: int
    accepted: bool
    raw: str


class Dialect:
    """One pool's wire format. Subclasses override the four framing points."""

    name = "abstract"
    miner_chooses_params = True

    def handshake_lines(self, address: str, worker: str) -> list[dict]:
        raise NotImplementedError

    def parse(self, line: str) -> Job | ShareResult | None:
        """Map one received line to an event, or None for chatter."""
        raise NotImplementedError

    def submit_line(self, msg_id: int, address: str, worker: str, job_id: str,
                    proof_b64: str) -> dict:
        raise NotImplementedError


class PoolConnection:
    """TCP + reader thread. Events (Job / ShareResult) land in .events."""

    def __init__(self, dialect: Dialect, host: str, port: int,
                 address: str, worker: str, log=print):
        self.dialect = dialect
        self.host, self.port = host, port
        self.address, self.worker = address, worker
        self.events: queue.Queue = queue.Queue()
        self.dead = threading.Event()
        self.log = log
        self._msg_id = 10
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    def connect(self):
        self._sock = socket.create_connection((self.host, self.port), timeout=20)
        self._sock.settimeout(None)
        self.dead.clear()
        for msg in self.dialect.handshake_lines(self.address, self.worker):
            self.send(msg)
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def send(self, msg: dict):
        raw = json.dumps(msg, separators=(",", ":")).encode() + b"\n"
        if _RAW:
            self.log(f"[raw>] {raw[:300]!r}{' …' if len(raw) > 300 else ''} ({len(raw)} B)")
        with self._lock:
            try:
                self._sock.sendall(raw)
            except OSError as e:
                if _RAW:
                    self.log(f"[raw>] send failed: {e}")
                self.dead.set()

    def submit(self, job_id: str, proof_b64: str) -> int:
        self._msg_id += 1
        self.send(self.dialect.submit_line(self._msg_id, self.address, self.worker,
                                           job_id, proof_b64))
        return self._msg_id

    def _reader(self):
        buf = b""
        try:
            while not self.dead.is_set():
                chunk = self._sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if _RAW:
                        self.log(f"[raw<] {line.decode(errors='replace')[:400]}")
                    try:
                        event = self.dialect.parse(line.decode(errors="replace"))
                    except Exception as e:  # noqa: BLE001 — log, never kill the reader
                        self.log(f"[stratum] parse error: {e} on {line[:200]!r}")
                        continue
                    if event is not None:
                        self.events.put(event)
        except OSError:
            pass
        finally:
            self.dead.set()
            self.log("[stratum] connection closed")
