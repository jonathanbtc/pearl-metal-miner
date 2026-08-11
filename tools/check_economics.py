#!/usr/bin/env python3
"""Offline check for the B4 money line (issue #30).

Unit part re-derives the arithmetic independently and pins the labels
(est./assumptions) and the missing-assumptions pointer. Integration part
runs the real miner under a pty twice with different config assumptions —
the dashboard verdict must change accordingly — and once with none — the
"run init" pointer must show. An easy-target run checks the session
PRL-earned estimate line. Finally, the offline/no-sudo audit: no network
or privilege-escalation imports anywhere in pearl_metal_miner/.

    .venv/bin/python tools/check_economics.py
"""

import json
import os
import re
import signal
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from check_dashboard import run_under_pty  # noqa: E402
from check_shutdown import fake_pool  # noqa: E402
from pearl_metal_miner import economics  # noqa: E402


def check_unit() -> bool:
    # Independent re-derivation: 2.3e6 tiles/s, factor 524288 (the default
    # shape), assumed 28.54 EH/s → hash-units share of the network per day.
    mine = 2.3e6 * 524288
    expect = mine / 28.54e18 * (86400 / 120) * 2460
    got = economics.prl_per_day(2.3e6, 524288, 28.54)
    if abs(got - expect) > 1e-12 * expect:
        print(f"FAIL unit: prl_per_day {got} != {expect}")
        return False
    # One share at difficulty D carries D×(2^256/diff1_target) hashes.
    share = economics.prl_per_share_est(888888, 28.54)
    expect_share = 2460 * 888888 * (2 ** 256 / float(0xFFFF << 208)) / (28.54e18 * 120)
    if abs(share - expect_share) > 1e-12 * expect_share:
        print(f"FAIL unit: prl_per_share {share} != {expect_share}")
        return False
    v = economics.verdict(2.3e6, 524288, "Apple M1 Max", 100, 0.20, 0.26, 28.54)
    if not v.startswith("est.") or "assumptions" not in v or "est. 40 W" not in v:
        print(f"FAIL unit: verdict labels off: {v!r}")
        return False
    if "run init" not in economics.verdict(1, 1, "x", 100, None, 0.26, 28.54):
        print("FAIL unit: missing assumptions must point at init")
        return False
    if economics.gpu_watts_est("Apple M1 Max", 50) != 20.0:
        print("FAIL unit: intensity scaling")
        return False
    print(f"PASS unit: arithmetic re-derived, labels pinned ({v!r})")
    return True


def panel_money(out: bytes) -> str:
    text = out.decode(errors="replace")
    lines = [re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", ln)
             for ln in re.split(r"\x1b\[\d+;1H|\x1b7|\x1b8", text)]
    money = [ln.strip() for ln in lines if ln.strip().startswith("money")]
    return money[-1] if money else ""


def check_dashboard_verdict(port: int) -> bool:
    with open(os.path.join(ROOT, "burner_wallet.json")) as f:
        address = json.load(f)["address"]
    runs = {}
    for name, extra_cfg in {
        "cheap": "electricity_usd_per_kwh = 0.05\nassumed_prl_price_usd = 0.26\n"
                 "assumed_network_hashrate = 28.54\n",
        "pricey": "electricity_usd_per_kwh = 0.95\nassumed_prl_price_usd = 0.26\n"
                  "assumed_network_hashrate = 28.54\n",
        "unset": "",
    }.items():
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.toml")
            with open(cfg, "w") as f:
                f.write(f'pool = "luckypool"\nhost = "127.0.0.1"\n'
                        f'port = {port}\naddress = "{address}"\n'
                        f'on_battery = "full"\n{extra_cfg}')
            rc, out = run_under_pty(port, env_add={"PRL_CONFIG": cfg},
                                    seconds=5.0)
            if rc != 0:
                print(f"FAIL verdict[{name}]: rc={rc}")
                return False
            runs[name] = panel_money(out)
    ok = ("est." in runs["cheap"] and "/day at your" in runs["cheap"]
          and "est." in runs["pricey"]
          and runs["cheap"] != runs["pricey"]
          and "run init" in runs["unset"])
    if not ok:
        print(f"FAIL verdict: {runs}")
        return False
    print(f"PASS verdict: assumptions drive the line "
          f"(cheap: {runs['cheap']!r} | pricey: {runs['pricey']!r} | "
          f"unset: {runs['unset']!r})")
    return True


def check_session_earned() -> bool:
    import subprocess
    from check_notify import accepting_pool, easy_target_hex
    port = accepting_pool(easy_target_hex())
    with open(os.path.join(ROOT, "burner_wallet.json")) as f:
        address = json.load(f)["address"]
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "config.toml")
        with open(cfg, "w") as f:
            f.write('electricity_usd_per_kwh = 0.20\n'
                    'assumed_prl_price_usd = 0.26\n'
                    'assumed_network_hashrate = 28.54\n')
        env = dict(os.environ, PRL_CONFIG=cfg)
        r = subprocess.run(
            [sys.executable, "-m", "pearl_metal_miner.miner",
             "--pool", "luckypool", "--host", "127.0.0.1", "--port", str(port),
             "--address", address, "--m", "64", "--n", "64",
             "--region-rows", "32", "--max-accepted", "1",
             "--on-battery", "full", "--no-notify", "--time-limit", "300"],
            capture_output=True, text=True, cwd=ROOT, env=env, timeout=240)
    m = re.search(r"session: est\. ([0-9.]+) PRL earned", r.stdout)
    if r.returncode != 0 or not m or "assumed network hashrate" not in r.stdout:
        print(f"FAIL earned: rc={r.returncode}\n{r.stdout[-2000:]}")
        return False
    # The fake pool's absurdly easy shares carry ~1e-19 PRL each, so the
    # printed figure legitimately rounds to zero — what matters is that the
    # line derives from accepted-share difficulty and says what it rests on.
    known = economics.prl_per_share_est(888888, 28.54)
    if not 0.002 < known < 0.004:
        print(f"FAIL earned: realistic per-share estimate off: {known}")
        return False
    print(f"PASS earned: session estimate labeled ({m.group(0)!r}; a real "
          f"888888-difficulty share ≈ {known:.8f} PRL)")
    return True


def check_offline_no_sudo() -> bool:
    """The miner package must import no HTTP/network-client machinery (its
    only socket is the pool's) and must never invoke sudo."""
    bad = []
    pkg = os.path.join(ROOT, "pearl_metal_miner")
    files = [os.path.join(pkg, n) for n in sorted(os.listdir(pkg))
             if n.endswith(".py")]
    files += [os.path.join(pkg, "stratum", n)
              for n in sorted(os.listdir(os.path.join(pkg, "stratum")))
              if n.endswith(".py")]
    for path in files:
        rel = os.path.relpath(path, pkg)
        with open(path) as f:
            for i, line in enumerate(f, 1):
                if re.match(r"\s*(import|from)\s+(urllib|http|requests"
                            r"|socketserver|ssl)\b", line):
                    bad.append(f"{rel}:{i}: {line.strip()}")
                if re.search(r"\bsudo\b", line) and "never asks" not in line \
                        and "password" not in line:
                    bad.append(f"{rel}:{i}: {line.strip()}")
    if bad:
        print(f"FAIL audit: {bad}")
        return False
    print("PASS audit: no HTTP/network-client imports, no sudo anywhere")
    return True


def main() -> int:
    signal.alarm(900)
    port = fake_pool()
    ok = check_unit()
    ok = check_dashboard_verdict(port) and ok
    ok = check_session_earned() and ok
    ok = check_offline_no_sudo() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
