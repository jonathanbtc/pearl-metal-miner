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


HEADER_BYTES = 76  # IncompleteBlockHeader wire form; every dialect sends this


@dataclass
class Job:
    job_id: str
    header_bytes: bytes          # the 76-byte IncompleteBlockHeader wire form
    target: int                  # pool base target as an integer (pre-factor)
    height: int = 0
    cert_version: int = 2
    received_at: float = field(default_factory=time.time)

    def __post_init__(self):
        """Reject a malformed job here, where the reader logs it and drops the
        line, rather than downstream where it is a traceback: a wrong-length
        header only fails once a tile wins (after mining a doomed job for
        hours), and target 0 divides by zero the moment the job is adopted.
        Every dialect gets this by constructing a Job — including future ones."""
        if len(self.header_bytes) != HEADER_BYTES:
            raise ValueError(f"job {self.job_id}: header is "
                             f"{len(self.header_bytes)} bytes, expected "
                             f"{HEADER_BYTES}")
        if self.target <= 0:
            raise ValueError(f"job {self.job_id}: target {self.target} is not "
                             f"positive — no tile could ever satisfy it")


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
        self.last_rx = time.monotonic()  # any pool traffic; the watchdog's clock
        self.log = log
        self._msg_id = 10  # submit ids start above any handshake id
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    def connect(self):
        """Open a fresh session. Safe to call again after `dead` is set: the
        old socket is closed (which unblocks a reader still stuck in recv on
        it), and each reader is bound to its own socket so a lingering old
        reader can never consume from — or kill — the new session."""
        old, self._sock = self._sock, None
        if old is not None:
            try:
                old.close()
            except OSError:
                pass
        # Events belong to a session; anything still queued from the old one
        # (a stale job would be mined and rejected) is garbage on the new one.
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                break
        sock = socket.create_connection((self.host, self.port), timeout=20)
        sock.settimeout(None)
        # A miner runs for days; without keepalive a silently dropped route
        # leaves recv blocked forever and the miner sweeping into the void.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self._sock = sock
        self.dead.clear()
        self.last_rx = time.monotonic()  # the watchdog clock restarts with the session
        for msg in self.dialect.handshake_lines(self.address, self.worker):
            self.send(msg)
        t = threading.Thread(target=self._reader, args=(sock,), daemon=True)
        t.start()

    def send(self, msg: dict):
        raw = json.dumps(msg, separators=(",", ":")).encode() + b"\n"
        if _RAW:
            self.log(f"[raw>] {raw[:300]!r}{' …' if len(raw) > 300 else ''} ({len(raw)} B)")
        with self._lock:
            sock = self._sock
            if sock is None:  # closed under us; nothing to send on
                self.dead.set()
                return
            try:
                sock.sendall(raw)
            except OSError as e:
                if _RAW:
                    self.log(f"[raw>] send failed: {e}")
                self.dead.set()

    def submit(self, job_id: str, proof_b64: str) -> int:
        self._msg_id += 1
        self.send(self.dialect.submit_line(self._msg_id, self.address, self.worker,
                                           job_id, proof_b64))
        return self._msg_id

    def close(self):
        """Deliberate local stop. The protocol has no goodbye — closing the
        socket IS the disconnect. Detach the socket before closing so the
        reader it unblocks sees a superseded socket and exits silently,
        instead of reporting our own shutdown as a lost connection."""
        self.dead.set()
        old, self._sock = self._sock, None
        if old is not None:
            try:
                old.close()
            except OSError:
                pass

    def _reader(self, sock: socket.socket):
        buf = b""
        try:
            while not self.dead.is_set():
                chunk = sock.recv(65536)
                if not chunk:
                    break
                self.last_rx = time.monotonic()
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
            if sock is self._sock:  # a superseded reader must not kill the new session
                self.dead.set()
                self.log("[stratum] connection closed")
