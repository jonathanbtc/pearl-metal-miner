#!/bin/sh
# One-time setup on a clean machine: venv, Python deps, ISC upstream clone
# (pinned), and the py-pearl-mining Rust extension. Requires python3.12+ and
# cargo (https://rustup.rs) on PATH.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || {
  echo "python >= 3.12 required (py-pearl-mining is abi3-py312)"; exit 1;
}
command -v cargo >/dev/null 2>&1 || {
  echo "Rust not found. Install it first:"
  echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
  exit 1
}

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet numpy blake3 maturin

if [ ! -d pearl ]; then
  git clone --depth 1 https://github.com/pearl-research-labs/pearl.git
fi
if [ -f PINNED_PEARL_COMMIT.txt ]; then
  WANT="$(cat PINNED_PEARL_COMMIT.txt)"
  HAVE="$(git -C pearl rev-parse HEAD)"
  if [ "$WANT" != "$HAVE" ]; then
    echo "WARNING: pearl checkout is $HAVE, pinned commit is $WANT."
    echo "The self-test re-verifies against whatever is checked out, but the"
    echo "documented verification applies to the pinned commit."
  fi
else
  git -C pearl rev-parse HEAD > PINNED_PEARL_COMMIT.txt
fi

( cd pearl/py-pearl-mining && "$ROOT"/.venv/bin/maturin develop --release )
.venv/bin/python -c "import pearl_mining; print('pearl_mining OK', pearl_mining.__version__)"
echo "setup complete — next: ./packaging/build_macos.sh"
