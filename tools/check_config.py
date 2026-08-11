#!/usr/bin/env python3
"""Offline check for the B1 config + init wizard (issue #27).

Covers: the scripted wizard writing TOML that round-trips through tomllib
with dated assumption comments; refusal to overwrite without --force;
precedence CLI flag > config > default (including the notifications →
--no-notify inversion); warn-don't-crash on unknown keys, wrong types, and
a bad pool; and the acceptance path — a bare run (no flags at all) mining
against the loopback fake pool purely from config.toml.

    .venv/bin/python tools/check_config.py
"""

import os
import signal
import subprocess
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from check_shutdown import TEST_ADDRESS, Capture, fake_pool  # noqa: E402


def run_wizard(cfg: str, answers: list[str], *extra: str):
    env = dict(os.environ, PRL_CONFIG=cfg)
    return subprocess.run(
        [sys.executable, "-m", "pearl_metal_miner.miner", "init", *extra],
        input="".join(a + "\n" for a in answers),
        capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)


def check_wizard(cfg: str) -> bool:
    r = run_wizard(cfg, ["", "", "studio", "0.30", "", ""])  # mostly prefills
    if r.returncode != 0 or not os.path.exists(cfg):
        print(f"FAIL wizard: rc={r.returncode}\n{r.stdout}\n{r.stderr}")
        return False
    with open(cfg, "rb") as f:
        parsed = tomllib.load(f)  # round-trip: hand-written TOML must parse
    want = {"pool": "luckypool", "worker": "studio",
            "electricity_usd_per_kwh": 0.30, "assumed_prl_price_usd": 0.26,
            "assumed_network_hashrate": 28.54}
    wrong = {k: parsed.get(k) for k, v in want.items() if parsed.get(k) != v}
    if wrong:
        print(f"FAIL wizard: values off: {wrong}")
        return False
    if not parsed.get("address", "").startswith("prl1p"):
        print(f"FAIL wizard: no prefilled wallet address: {parsed.get('address')}")
        return False
    text = open(cfg).read()
    if "2026-08-02" not in text or "assumption" not in text.lower():
        print("FAIL wizard: assumption comments not dated/labeled")
        return False
    r2 = run_wizard(cfg, [])
    if r2.returncode == 0 or "already exists" not in r2.stdout:
        print(f"FAIL wizard: overwrote without --force (rc={r2.returncode})")
        return False
    r3 = run_wizard(cfg, ["kryptex", "", "forced", "0.10", "0.5", "30"],
                    "--force")
    with open(cfg, "rb") as f:
        again = tomllib.load(f)
    if r3.returncode != 0 or again.get("pool") != "kryptex" \
            or again.get("worker") != "forced":
        print(f"FAIL wizard: --force rewrite failed\n{r3.stdout}")
        return False
    print("PASS wizard: round-trips, dated comments, refuses then --force rewrites")
    return True


def check_precedence(cfg: str) -> bool:
    os.environ["PRL_CONFIG"] = cfg
    with open(cfg, "w") as f:
        f.write('worker = "cfgworker"\nintensity = 55\nnotifications = false\n'
                'keep_awake = true\nmystery_key = 1\nport = "not a number"\n'
                'pool = "nosuchpool"\non_battery = "low"\n'
                'assumed_prl_price_usd = 1\n')
    from pearl_metal_miner.miner import _apply_config, _explicit_dests, build_parser
    import pearl_metal_miner.miner as miner_mod
    warnings: list[str] = []
    real_log = miner_mod.log
    miner_mod.log = lambda *a: warnings.append(" ".join(str(x) for x in a))
    try:
        argv = ["--worker", "flagworker"]
        args = build_parser().parse_args(argv)
        _apply_config(args, _explicit_dests(argv))
    finally:
        miner_mod.log = real_log
    checks = [
        (args.worker == "flagworker", f"flag should beat config: {args.worker}"),
        (args.intensity == 55, f"config should beat default: {args.intensity}"),
        (args.no_notify is True, "notifications=false must set no_notify"),
        (args.keep_awake is True, "keep_awake=true must apply"),
        (args.pool == "luckypool", f"bad pool must fall back: {args.pool}"),
        (args.port is None, f"wrong-typed port must be ignored: {args.port}"),
        (args.on_battery == "low", f"on_battery carried: {args.on_battery}"),
        (args.assumed_prl_price_usd == 1.0, "int→float coercion"),
        (args.electricity_usd_per_kwh is None, "absent economics stay None"),
        (any("mystery_key" in w for w in warnings), f"unknown key must warn: {warnings}"),
        (any("port" in w for w in warnings), "wrong type must warn"),
        (any("nosuchpool" in w for w in warnings), "bad pool must warn"),
    ]
    bad = [msg for ok, msg in checks if not ok]
    if bad:
        print("FAIL precedence: " + "; ".join(bad))
        return False
    print("PASS precedence: flag > config > default; warn-don't-crash on junk")
    return True


def check_bare_run(cfg: str) -> bool:
    port = fake_pool()
    address = TEST_ADDRESS
    with open(cfg, "w") as f:
        f.write(f'pool = "luckypool"\nhost = "127.0.0.1"\nport = {port}\n'
                f'address = "{address}"\nworker = "cfg"\n'
                f'on_battery = "full"\n')  # the check host may be unplugged
    env = dict(os.environ, PRL_CONFIG=cfg)
    proc = subprocess.Popen([sys.executable, "-m", "pearl_metal_miner.miner"],
                            cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    out, err = Capture(proc.stdout), Capture(proc.stderr)
    ok = out.wait_for("grid #1 ready", 120)
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(20)
    except Exception:
        proc.kill()
    if not ok or proc.returncode != 0:
        print(f"FAIL bare-run: rc={proc.returncode}\n{out.text()}\n{err.text()}")
        return False
    print("PASS bare-run: zero flags, config.toml alone drives a mining run")
    return True


def check_no_config_pointer() -> bool:
    """Nothing configured at all (empty project folder, no config, no wallet,
    no flags): the miner must exit with an `init` pointer, not a traceback.
    The project folder is module-relative, so point the module elsewhere."""
    import contextlib
    import io
    os.environ.pop("PRL_CONFIG", None)
    import pearl_metal_miner.miner as miner_mod
    import pearl_metal_miner.wallet as wallet_mod
    real_root = wallet_mod._repo_root
    stderr = io.StringIO()
    rc = None
    with tempfile.TemporaryDirectory() as d:
        wallet_mod._repo_root = lambda: d
        try:
            with contextlib.redirect_stderr(stderr):
                miner_mod.run([])
        except SystemExit as e:
            rc = e.code
        finally:
            wallet_mod._repo_root = real_root
    text = stderr.getvalue()
    if rc != 2 or "init" not in text or "Traceback" in text:
        print(f"FAIL pointer: rc={rc}\n{text}")
        return False
    print("PASS pointer: bare walletless run exits with the init pointer")
    return True


def main() -> int:
    signal.alarm(900)
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "config.toml")
        ok = check_wizard(cfg)
        os.remove(cfg)
        ok = check_precedence(cfg) and ok
        ok = check_bare_run(cfg) and ok
    ok = check_no_config_pointer() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
