#!/bin/sh
# One-time setup on a clean machine: venv, Python deps, ISC upstream clone
# (pinned), and the py-pearl-mining Rust extension. Requires python3.12+ and
# cargo (https://rustup.rs) on PATH.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=
for c in python3.12 python3.13 python3.14 python3; do
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PY="$c"
    break
  fi
done
[ -n "$PY" ] || {
  echo "python >= 3.12 required (py-pearl-mining is abi3-py312)."
  echo "Looked for python3.12, python3.13, python3.14, python3 on PATH;"
  echo "e.g.  brew install python@3.12  then rerun this script."
  exit 1
}
command -v cargo >/dev/null 2>&1 || {
  echo "Rust not found. Install it first:"
  echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
  echo "Already installed? This shell can't see it — run:"
  echo '  . "$HOME/.cargo/env"'
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
    # A fresh clone is upstream's tip of the day; the verified commit is the
    # pinned one. Fetch it (shallow — GitHub serves reachable SHAs) and check
    # it out, warning only if that fails.
    if git -C pearl fetch --depth 1 origin "$WANT" &&
       git -C pearl checkout -q "$WANT"; then
      echo "pearl: checked out pinned commit $WANT"
    else
      echo "WARNING: could not check out pinned commit $WANT; building against $HAVE."
      echo "The self-test re-verifies against whatever is checked out, but the"
      echo "documented verification applies to the pinned commit."
    fi
  fi
else
  git -C pearl rev-parse HEAD > PINNED_PEARL_COMMIT.txt
fi

( cd pearl/py-pearl-mining && "$ROOT"/.venv/bin/maturin develop --release )
.venv/bin/python -c "import pearl_mining; print('pearl_mining OK', pearl_mining.__version__)"
echo "setup complete — next: ./packaging/build_macos.sh"
