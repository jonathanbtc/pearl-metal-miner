"""Session rate numbers, shared by the heartbeat, the exit summary, and the
dashboard — one place, so every surface shows the same figures.

Display math only: nothing here feeds consensus values, so the kernel rule
of exact-integer comparisons does not bind; the unit stays tiles/s because
any conversion to a hashrate would be an invented number.
"""

from __future__ import annotations

import threading
import time
from collections import deque


def fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


class RateMeter:
    """Tiles/s two ways: a rolling window that tracks what the machine is
    doing now (intensity and thermal changes show within `window_s`), and
    the session average the summary reports. Monotonic clock, injectable
    for deterministic tests."""

    def __init__(self, window_s: float = 60.0, now=time.monotonic):
        self._now = now
        self.window_s = window_s
        self.total = 0
        self._t0 = now()
        self._samples: deque[tuple[float, int]] = deque()
        self._win_total = 0
        # the dashboard's ticker thread reads rolling() (which prunes) while
        # the mining loop add()s; the window sum must not lose an update
        self._lock = threading.Lock()

    def add(self, n: int):
        with self._lock:
            self.total += n
            self._win_total += n
            self._samples.append((self._now(), n))

    def uptime(self) -> float:
        return self._now() - self._t0

    def average(self) -> float:
        up = self.uptime()
        return self.total / up if up > 0 else 0.0

    def rolling(self) -> float:
        with self._lock:
            t = self._now()
            cutoff = t - self.window_s
            # A sample's tiles belong to the burst ENDING at its timestamp, so a
            # sample at exactly `cutoff` is work done outside (cutoff, t] — drop it.
            while self._samples and self._samples[0][0] <= cutoff:
                self._win_total -= self._samples.popleft()[1]
            span = min(t - self._t0, self.window_s)
            return self._win_total / span if span > 0 else 0.0
