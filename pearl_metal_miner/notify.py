"""macOS notifications for the rare moments that matter — an accepted share
can be an hour apart, and nobody is watching the terminal when it lands.

Zero new packages: `osascript` ships with macOS. A toast must never crash or
stall mining, so each one runs in a fire-and-forget thread (waited on there,
which also reaps the process), every failure is swallowed, and only the
first is logged. The thread is deliberately NOT a daemon: a stop right
after an accepted share (--max-accepted 1 is the "first share!" moment)
must not kill the toast mid-flight; the subprocess timeout bounds how long
exit can be held up.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time


class Notifier:
    """One shared gate for every notification the miner sends (A4 accepted
    shares; B3 battery pause/resume reuses it). `enabled=False` makes every
    call a no-op; so does running anywhere but macOS."""

    MIN_GAP_S = 3.0  # a burst of toasts coalesces: the body carries the
    #                  running total, so a suppressed one is still counted

    def __init__(self, enabled: bool, log=print, now=time.monotonic):
        self.enabled = enabled and sys.platform == "darwin"
        self.log = log
        self._now = now
        self._last: float | None = None
        self._warned = False

    def send(self, title: str, body: str):
        if not self.enabled:
            return
        t = self._now()
        if self._last is not None and t - self._last < self.MIN_GAP_S:
            return
        self._last = t
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
        script = f'display notification "{esc(body)}" with title "{esc(title)}"'
        threading.Thread(target=self._run, args=(script,)).start()

    def _run(self, script: str):
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True,
                           timeout=10)
        except Exception as e:  # noqa: BLE001 — a toast must never hurt mining
            if not self._warned:
                self._warned = True
                self.log(f"notifications unavailable ({e}) — mining continues; "
                         f"silence this with --no-notify")
