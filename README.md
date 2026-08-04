# pearl-metal-miner

A bit-exact Apple Metal compute backend for the Pearl (PRL) proof-of-useful-work
miner, for **pool** mining on Apple Silicon.

> **Not usable yet.** Nothing is built. This repository currently contains a
> plan, a glossary, a set of decision records and one Metal probe. It is private
> and goes public under Apache-2.0 when the release phase completes.
>
> Not affiliated with Pearl Research Labs.

## Where things are

| File | What it is |
| ---- | ---------- |
| [`Plan.md`](Plan.md) | The build plan, with a verification marker on every external claim |
| [`CONTEXT.md`](CONTEXT.md) | The glossary. Terms only — every concrete number lives in `Plan.md` |
| [`docs/adr/`](docs/adr/) | The decisions and why they were taken |
| [`docs/research/`](docs/research/) | Source research, with verbatim quotes and URLs |
| `tools/metal_probe.mm` | Proves runtime MSL compilation and int32 exactness on this hardware |

## What it will be

An accepted share on a pool dashboard, produced by a hand-written Metal kernel
on an Apple Silicon Mac, plus everything needed for someone else to do the same:
a clean-machine build, two tested pool dialects, and a `--self-test` that proves
bit-exactness against the reference implementation on *your* machine before you
mine anything.

**No developer fee**, ever. The reasoning is in
[ADR-0005](docs/adr/0005-public-apache-2-built-from-isc-upstream.md), and the
short version is that this hardware earns roughly $0.06/day while burning
$0.25–0.75 of electricity. A percentage of that is not income.

## Credit

- **[`pearl-research-labs/pearl`](https://github.com/pearl-research-labs/pearl)** (ISC) — the algorithm, the `miner_base` oracle, the Merkle commitment, `PlainProof` and the verifier.
- **[`arabel1a/ascend_prl`](https://github.com/arabel1a/ascend_prl)** (MIT) — for documenting that Pearl pools do not share one Stratum dialect, which is the single most useful structural insight this project got from anyone.
