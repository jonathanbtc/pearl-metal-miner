"""Deprecated shim — wallet creation moved into the package on 2026-08-10.

Equivalent to `python -m pearl_metal_miner.wallet new`, which creates
`wallet.json` (or prints the address of an existing wallet file, including a
legacy `burner_wallet.json`). Kept because pre-08-10 instructions name this
path; new documentation should point at the module.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pearl_metal_miner import wallet  # noqa: E402

if __name__ == "__main__":
    print("note: wallet creation moved — this now runs "
          "`python -m pearl_metal_miner.wallet new`", file=sys.stderr)
    sys.exit(wallet.main(["new"]))
