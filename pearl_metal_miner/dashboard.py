"""The live terminal dashboard: hand-rolled ANSI, zero new packages (the
three-package install is a trust property of a tool that generates private
keys).

Model: an ANSI scroll region owns the top of the screen, so ordinary log
lines keep scrolling there and remain the plain-text source of truth; the
panel owns the bottom rows and is redrawn in place ~1 Hz by a ticker thread
(a thread so the panel stays live through reconnect backoff sleeps). One
lock serializes the log sink and the panel painter. Active only when stdout
is a real TTY; piped/redirected runs keep pre-dashboard behavior exactly.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading

from .stats import fmt_uptime

_ESC = "\x1b"
_MIN_ROWS = 12  # below this, a panel would crowd out the logs — stay plain


def _fmt_eta(seconds: float) -> str:
    if seconds < 90:
        return f"~{seconds:.0f} s"
    if seconds < 5400:
        return f"~{seconds / 60:.0f} min"
    if seconds < 48 * 3600:
        return f"~{seconds / 3600:.1f} h"
    if seconds < 366 * 86400:
        return f"~{seconds / 86400:.1f} days"
    return "over a year"  # an honest cap: targets can be arbitrarily hard


class Dashboard:
    """state_fn() returns the panel's fields each tick (see miner.run);
    everything it reads is written by the mining loop under the GIL."""

    def __init__(self, state_fn, out=None):
        self.state_fn = state_fn
        self.out = out if out is not None else sys.stdout
        self.active = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._size = (0, 0)
        self._panel_h = 7  # incl. the money line, which always renders
        color = not os.environ.get("NO_COLOR")
        self._c = (lambda code, s: f"{_ESC}[{code}m{s}{_ESC}[0m") if color \
            else (lambda code, s: s)

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        if not self.out.isatty():
            return
        cols, rows = shutil.get_terminal_size()
        if rows < _MIN_ROWS:
            return
        with self._lock:
            self._size = (cols, rows)
            top = rows - self._panel_h
            self._write("\n" * self._panel_h        # push history clear of the panel zone
                        + f"{_ESC}[?25l"            # hide cursor
                        + f"{_ESC}[1;{top}r"        # logs live in the scroll region
                        + f"{_ESC}[{top};1H")       # cursor at the region's bottom
            self.active = True
        self._ticker = threading.Thread(target=self._run, daemon=True)
        self._ticker.start()

    def stop(self):
        """Restore the terminal; idempotent, safe on every exit path."""
        self._stop.set()
        with self._lock:
            if not self.active:
                return
            self.active = False
            rows = self._size[1]
            self._write(f"{_ESC}[r{_ESC}[{rows};1H\n{_ESC}[?25h")
        self._ticker.join(timeout=2)

    def log(self, line: str):
        """The miner's log sink while the dashboard runs: same scrolling
        text as ever, just serialized against the panel painter."""
        with self._lock:
            self._write(line + "\n")

    # -- painting -----------------------------------------------------------

    def _run(self):
        while not self._stop.wait(1.0):
            try:
                self._draw()
            except OSError:       # stdout vanished; the miner's own handling decides
                self.active = False
                return

    def _write(self, s: str):
        self.out.write(s)
        self.out.flush()

    def _draw(self):
        with self._lock:
            if not self.active:
                return
            cols, rows = shutil.get_terminal_size()
            if rows < _MIN_ROWS:
                return
            top = rows - self._panel_h
            if (cols, rows) != self._size:  # re-anchor after a resize
                self._size = (cols, rows)
                self._write(f"{_ESC}[r{_ESC}[1;{top}r{_ESC}[{top};1H")
            out = [f"{_ESC}7"]
            for i, line in enumerate(self._lines(self.state_fn(), cols)):
                out.append(f"{_ESC}[{top + 1 + i};1H{_ESC}[2K{line}")
            out.append(f"{_ESC}8")
            self._write("".join(out))

    def _lines(self, st: dict, cols: int) -> list[str]:
        c, dim = self._c, "2"
        title = " pearl-metal-miner "
        rule = "─" * max(0, (cols - len(title)) // 2)
        status = st.get("status", "mining")
        status_col = {"mining": "32", "reconnecting": "33", "paused": "36"}.get(
            status.split()[0], "0")
        judged = st.get("acc", 0) + st.get("rej", 0)
        pct = f" ({100 * st.get('acc', 0) / judged:.0f}% accept)" if judged else ""
        awaiting = f" · {st['pending']} awaiting" if st.get("pending") else ""
        last = st.get("last_share_ago")
        last_s = f" · last share {_fmt_eta(last)} ago".replace("~", "") \
            if last is not None else ""
        eta = st.get("est_next_s")
        eta_s = (f"est. {_fmt_eta(eta)} to a share at the current speed "
                 f"(from the live job's target)") if eta else "…"
        lines = [
            c(dim, rule + title + rule),
            f" {st.get('device', '?')} · {st.get('pool', '?')} · "
            f"worker {st.get('worker', '?')}",
            f" status  {c(status_col, status)} · up "
            f"{fmt_uptime(st.get('uptime', 0))}",
            f" speed   {st.get('rolling', 0) / 1e6:.3f}M tiles/s (60s) · "
            f"{st.get('avg', 0) / 1e6:.3f}M/s session · "
            f"intensity {st.get('intensity', '?')}",
            f" shares  {c('32', str(st.get('acc', 0)) + ' acc')} / "
            f"{st.get('rej', 0)} rej{pct}{awaiting}{last_s}",
            f" next    {c(dim, eta_s)}",
        ]
        if st.get("money"):
            lines.append(f" money   {st['money']}")
        return [_fit(ln, cols) for ln in lines]


def _strip_ansi(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == _ESC:
            i += 1
            while i < len(s) and not s[i].isalpha():
                i += 1
            i += 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _fit(line: str, cols: int) -> str:
    """Truncate to the terminal width counting glyphs, not ANSI bytes. A cut
    must never leave a dangling escape sequence, so an overlong styled line
    is shown plain."""
    if len(line) <= cols or len(_strip_ansi(line)) <= cols:
        return line
    return _strip_ansi(line)[:cols]
