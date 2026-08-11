"""config.toml in the project folder, and the `init` wizard that writes it.

The file lives next to wallet.json on purpose — "uninstall = delete the
folder" stays true — and is read with stdlib tomllib (zero new packages).
Precedence is uniform: CLI flag > config value > built-in default. The
wizard is the only place that asks questions; the miner itself never
prompts. Unknown keys and wrong types warn and are ignored — a typo in a
config file must never stop the miner.

The three economics keys (electricity, assumed PRL price, assumed network
hashrate) are the user's OWN assumptions, prefilled with dated figures at
`init`: the miner contacts nothing but the pool, so every money figure
downstream (B4 money line, C1 benchmark) derives from these and is labeled
an estimate, never a measurement.
"""

from __future__ import annotations

import argparse
import datetime
import os
import socket
import tomllib

from . import wallet

CONFIG_BASENAME = "config.toml"

# key -> expected type, or a tuple of allowed literal values
KNOWN: dict[str, type | tuple] = {
    "pool": str,
    "host": str,
    "port": int,
    "address": str,
    "worker": str,
    "intensity": int,
    "auto_intensity": bool,
    "on_battery": ("pause", "low", "full"),
    "notifications": bool,
    "dashboard": bool,
    "keep_awake": bool,
    "max_job_age": float,
    "electricity_usd_per_kwh": float,
    "assumed_prl_price_usd": float,
    "assumed_network_hashrate": float,
}


def config_path() -> str:
    """The project-folder config; PRL_CONFIG overrides (tests, power users)."""
    return os.environ.get("PRL_CONFIG") or os.path.join(
        wallet._repo_root(), CONFIG_BASENAME)


def load(path: str | None = None, log=print) -> dict:
    """Validated config values, or {} if there is no (readable) file."""
    path = path or config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        log(f"config.toml ignored (not valid TOML): {e}")
        return {}
    vals: dict = {}
    for key, val in raw.items():
        spec = KNOWN.get(key)
        if spec is None:
            log(f"config.toml: unknown key {key!r} ignored")
        elif isinstance(spec, tuple):
            if val in spec:
                vals[key] = val
            else:
                log(f"config.toml: {key} = {val!r} is not one of "
                    f"{'/'.join(spec)}; ignored")
        elif spec is float and isinstance(val, int) and not isinstance(val, bool):
            vals[key] = float(val)
        elif not isinstance(val, spec) or (spec is not bool and isinstance(val, bool)):
            log(f"config.toml: {key} = {val!r} has the wrong type "
                f"(want {spec.__name__}); ignored")
        else:
            vals[key] = val
    return vals


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render(values: dict) -> str:
    """Hand-written commented TOML (stdlib has no writer; the file is small).
    Must round-trip through tomllib — check_config.py asserts it."""
    today = datetime.date.today().isoformat()
    num = lambda v: f"{v:g}"  # noqa: E731
    lines = [
        f"# pearl-metal-miner configuration — written by `init` on {today}.",
        "# Lives in the project folder on purpose: uninstall = delete the folder.",
        "# CLI flags always override these values. Rerun `init --force` to redo,",
        "# or just edit this file.",
        "",
        f"pool = {_toml_str(values['pool'])}",
    ]
    if values.get("address"):
        lines.append(f"address = {_toml_str(values['address'])}")
    else:
        lines.append('# address = "prl1p…"   # none yet: pass --address, or run'
                     " `python -m pearl_metal_miner.wallet new`")
    lines += [
        f"worker = {_toml_str(values['worker'])}",
        "",
        "# ---- your assumptions ------------------------------------------------",
        "# The miner contacts nothing but the pool. Every money figure it shows",
        "# is derived from the three values below — YOUR assumptions, labeled as",
        "# such in the UI — never from a live feed.",
        "",
        "# what you pay for power, USD per kWh — check your bill",
        f"electricity_usd_per_kwh = {num(values['electricity_usd_per_kwh'])}",
        "",
        "# the PRL/USD price you assume. Prefill $0.26 is hashrate.no's figure",
        "# dated 2026-08-02 (Plan.md \"Economics\") — check today's price before",
        "# trusting any earnings estimate",
        f"assumed_prl_price_usd = {num(values['assumed_prl_price_usd'])}",
        "",
        "# the network hashrate you assume, in EH/s as aggregators report it.",
        "# Prefill 28.54 EH/s is hashrate.no's figure dated 2026-08-02",
        "# (Plan.md \"Economics\")",
        f"assumed_network_hashrate = {num(values['assumed_network_hashrate'])}",
        "",
        "# ---- optional toggles (defaults shown; uncomment to change) ----------",
        '# intensity = 100        # GPU duty cycle 1-100',
        '# auto_intensity = false # treat intensity as the floor, 100 when idle',
        '# on_battery = "pause"   # pause|low|full when a laptop is unplugged',
        '# notifications = true   # macOS toast on accepted shares',
        '# dashboard = true       # live bottom panel in a terminal; plain logs when piped',
        '# keep_awake = false     # hold off system sleep while mining',
        '# max_job_age = 300      # pool-silence watchdog, seconds (0 = off)',
        '# host = "…"             # override the pool endpoint',
        '# port = 3360',
        "",
    ]
    return "\n".join(lines)


def _ask(prompt: str, default: str, validate=None) -> str:
    """One wizard question. Enter accepts the prefill; invalid answers
    re-ask; EOF (piped stdin ran dry) raises to abort with nothing written."""
    while True:
        raw = input(f"{prompt} [{default}]: ").strip() or default
        if validate is None:
            return raw
        try:
            return str(validate(raw))
        except ValueError as e:
            print(f"  {e}")


def _float(name: str):
    def parse(raw: str) -> float:
        try:
            v = float(raw)
        except ValueError:
            raise ValueError(f"{name} must be a number") from None
        if v < 0:
            raise ValueError(f"{name} cannot be negative")
        return v
    return parse


def init_wizard(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m pearl_metal_miner.miner init",
        description="One-time setup: writes config.toml in the project "
                    "folder so a bare run mines with your settings.")
    ap.add_argument("--force", action="store_true",
                    help="rewrite an existing config.toml")
    opts = ap.parse_args(argv if argv is not None else [])
    path = config_path()

    if os.path.exists(path) and not opts.force:
        print(f"{path} already exists — current values:\n")
        with open(path) as f:
            print(f.read())
        print("Nothing changed. Rerun with --force to rewrite it, "
              "or just edit the file.")
        return 1

    print("pearl-metal-miner init — a few questions, Enter accepts the "
          "[prefill].\nAnswers land in config.toml; CLI flags always "
          "override it; nothing leaves your machine.\n")
    def valid_pool(v: str) -> str:
        if v not in ("luckypool", "kryptex"):
            raise ValueError("pick luckypool or kryptex")
        return v

    try:
        pool = _ask("pool (luckypool has verified accepted shares; kryptex "
                    "is live-tested, no accept yet)", "luckypool", valid_pool)

        found = wallet.payout_address_from_disk()
        if found is not None:
            address = _ask("payout address", found[0],
                           wallet.validate_payout_address)
        else:
            make = _ask("no wallet.json here — create one now? (y/n)", "y")
            if make.lower().startswith("y"):
                data = wallet.create_wallet(wallet.default_wallet_path())
                address = data["address"]
                print(f"  created wallet.json — address {address}")
                print("  that file is the only claim on anything mined: "
                      "back it up.")
            else:
                address = _ask("payout address (prl1p…, empty to skip)", "",
                               lambda v: v if not v
                               else wallet.validate_payout_address(v))
                if not address:
                    print("  no address: the miner will refuse to start "
                          "until you pass --address or create a wallet.")

        worker = _ask("worker label (how this machine shows on the pool "
                      "dashboard)", socket.gethostname().split(".")[0])
        print("\nThree assumptions drive every money estimate. They are "
              "yours to change\nany time in config.toml; the miner never "
              "fetches prices or anything else.")
        kwh = _ask("electricity price, USD per kWh (check your bill)",
                   "0.20", _float("electricity price"))
        price = _ask("assumed PRL price in USD ($0.26 dated 2026-08-02, "
                     "hashrate.no — check today's)", "0.26",
                     _float("PRL price"))
        net = _ask("advanced — assumed network hashrate in EH/s "
                   "(28.54 dated 2026-08-02, hashrate.no)", "28.54",
                   _float("network hashrate"))
    except EOFError:
        print("\naborted (end of input); nothing written")
        return 1

    values = {"pool": pool, "address": address, "worker": worker,
              "electricity_usd_per_kwh": float(kwh),
              "assumed_prl_price_usd": float(price),
              "assumed_network_hashrate": float(net)}
    with open(path, "w") as f:
        f.write(_render(values))
    print(f"\nwrote {path}")
    print("a bare `python -m pearl_metal_miner.miner` now mines with these "
          "settings")
    return 0
