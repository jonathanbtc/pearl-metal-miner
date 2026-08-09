# pearl-metal-miner

Pool mining for Pearl (PRL) on Apple Silicon, with a hand-written Metal
compute backend. Apache-2.0, **no developer fee**.
**Not affiliated with Pearl Research Labs.**

Built from the ISC-licensed
[`pearl-research-labs/pearl`](https://github.com/pearl-research-labs/pearl)
upstream: the host commitment, proof construction and local verification are
upstream's own `py-pearl-mining` machinery; the mining hot loop — noise
generation, noise application, and the fused GEMM → transcript → keyed-BLAKE3
proof-of-work sweep — is implemented from scratch in Metal Shading Language
and compiled at process start (no Xcode required, Command Line Tools only).

## Why trust it: run the self-test

This domain fails silently: a subtly wrong kernel doesn't crash, it burns
electricity producing shares every pool rejects. So the first supported
command is a live differential of **every GPU stage** against the reference
implementation, on **your** machine, ending with a proof crafted from GPU
output that upstream's own Rust consensus verifier must accept:

```sh
.venv/bin/python -m pearl_metal_miner.miner --self-test
```

It prints `SELF-TEST PASS` and exits 0, or names the exact stage that
diverged and exits non-zero. Do not mine on a build that fails it.

Verified by the authors on: Apple M1 Max, macOS 14.4.1. Every other machine:
that's what the self-test is for.

## Build

Requires: macOS on Apple Silicon, Python ≥ 3.12, Rust (for the upstream
`py-pearl-mining` extension), Command Line Tools. No Xcode.

```sh
./packaging/setup.sh        # venv, deps, upstream clone + pin, maturin build
./packaging/build_macos.sh  # libpearlmetal.dylib (clang++ only)
.venv/bin/python -m pearl_metal_miner.miner --self-test
```

## Mine

```sh
.venv/bin/python -m pearl_metal_miner.miner \
  --pool luckypool --address prl1p...your_address --worker mac1
```

Tested pools (both exercised live; wire evidence in
`docs/research/2026-08-10-pool-survey.md`):

| pool | endpoint | notes |
| ---- | -------- | ----- |
| `luckypool` | `pearl-eu1.luckypool.io:3360` | varDiff; dialect reverse-engineered from live traffic |
| `kryptex` | `prl-eu.kryptex.network:7048` | fixed difficulty 2,097,152 |

`--intensity 1-100` throttles the GPU duty cycle and `--cpu-threads N` caps
the host commitment's cores — both matter if you want the machine usable
while it mines. `--rows/--cols/--rank/--k/--m/--n` change the job shape; the
default (rank 128, k 4096, 2×64 tiles, 8192² grids) is the fast path.

## The honest economics

At the network conditions measured 2026-08-02 (PRL $0.26, 28.54 EH/s), a
top-end GPU earns ~$0.06/day and an M1 Max draws $0.25–0.75/day of
electricity. **Mining PRL on a Mac loses roughly 9× what it earns.** This
project exists to demonstrate a bit-exact Metal implementation of the PoW and
pool pipeline — a pool-accepted share from a hand-written Metal kernel — not
to make anyone money. Pool payout thresholds mean small balances may never
move.

## Design notes

- `Plan.md` — the build plan, with a verification marker on every external claim.
- `CONTEXT.md` — the domain glossary.
- `docs/adr/` — the decisions and their reasoning, including why the barred
  fee-licensed repositories were never read (ADR-0005) and what a hash tile
  actually is (ADR-0007).
- `pearl_metal_miner/reference.py` — the NumPy restatement of the consensus
  PoW every kernel is differentially tested against; itself pinned to
  upstream by `tools/phase05_experiments.py`.

Contributing the kernel upstream or to other projects is a welcome
conversation now that it works; it is a port to offer, not a promise made.

## License

Apache-2.0 (`LICENSE`); third-party notices in `NOTICE`, also printed by
`--version`. No developer fee — at these economics a fee would be a rounding
error that costs more goodwill than it earns.
