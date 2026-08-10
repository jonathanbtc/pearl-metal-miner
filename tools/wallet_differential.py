"""Differentially test pearl_metal_miner.wallet against independent oracles.

This is the generator behind selftest.WALLET_VECTORS, kept so the baked
vectors are reproducible by anyone rather than an assertion to take on
faith. It checks fresh random keys three ways:

  A. key → address vs `bitcoinutils` (an independent BIP-341 implementation,
     and the very library upstream's gateway builds coinbases with) — the
     witness programs must be identical;
  B. our addresses through upstream's own gateway decoder
     (`get_script_pubkey_from_p2tr_address`) — must yield 5120‖program;
  C. the witness program from upstream's authored coinbase fixture
     (pearl-gateway/tests/test_blockchain_utils.py) round-tripped through
     our codec.

Needs the dev-only dependency `pip install bitcoin-utils` (MIT) and the
upstream clone in ./pearl (setup.sh puts it there). Not part of the runtime,
and not run by the self-test — the self-test uses the vectors this printed
on 2026-08-10 (bitcoinutils 0.8.2: 32 keys, all identical).

Exit 0 and "ALL MATCH" or exit 1 naming the mismatch.
"""

import importlib.util
import os
import secrets
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

from pearl_metal_miner import wallet  # noqa: E402

try:
    import bitcoinutils
    from bitcoinutils.bech32 import Encoding, bech32_decode, convertbits
    from bitcoinutils.keys import PrivateKey
    from bitcoinutils.setup import setup
except ImportError:
    sys.exit("bitcoinutils missing — dev-only dependency: pip install bitcoin-utils")

_GW = os.path.join(REPO, "pearl", "miner", "pearl-gateway", "src", "pearl_gateway",
                   "blockchain_utils", "blockchain_utils.py")
if not os.path.exists(_GW):
    sys.exit("upstream clone missing — run packaging/setup.sh first")
_spec = importlib.util.spec_from_file_location("gw_blockchain_utils", _GW)
gw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gw)

setup("mainnet")


def program_via_bitcoinutils(secret: int) -> bytes:
    addr = PrivateKey(secret_exponent=secret).get_public_key().get_taproot_address()
    _, data, enc = bech32_decode(addr.to_string())
    assert enc == Encoding.BECH32M and data[0] == 1
    return bytes(convertbits(data[1:], 5, 8, False))


def main(n_keys: int = 32) -> int:
    print(f"bitcoinutils {getattr(bitcoinutils, '__version__', '?')}, {n_keys} random keys")
    fails = 0
    vectors = []
    for _ in range(n_keys):
        secret = secrets.randbelow(wallet.N - 1) + 1
        norm, addr = wallet.derive_address(secret)

        ours = wallet.decode_payout_address(addr)
        theirs = program_via_bitcoinutils(secret)
        if ours != theirs:
            fails += 1
            print(f"MISMATCH (tweak) key {secret:064x}: ours {ours.hex()} vs "
                  f"bitcoinutils {theirs.hex()}")

        spk = bytes.fromhex(gw.get_script_pubkey_from_p2tr_address(addr).to_hex())
        if spk != b"\x51\x20" + ours:
            fails += 1
            print(f"MISMATCH (gateway) {addr}: scriptPubKey {spk.hex()}")

        if len(vectors) < 4:
            vectors.append((f"{norm:064x}", addr))

    from pearl_metal_miner.selftest import UPSTREAM_FIXTURE_PROGRAM
    fix = bytes.fromhex(UPSTREAM_FIXTURE_PROGRAM)
    if wallet.decode_payout_address(wallet.encode_address(fix)) != fix:
        fails += 1
        print("MISMATCH: upstream coinbase fixture failed to round-trip")

    if fails:
        print(f"{fails} FAILURES — do not trust wallet.py until this is understood")
        return 1
    print("ALL MATCH. Fresh vectors, should selftest.WALLET_VECTORS ever need renewing:")
    for k, a in vectors:
        print(f'    ("{k}",\n     "{a}"),')
    return 0


if __name__ == "__main__":
    sys.exit(main())
