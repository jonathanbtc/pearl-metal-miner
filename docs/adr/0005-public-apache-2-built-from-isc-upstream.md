# Public under Apache-2.0, built from ISC upstream; Muskwak is barred

Supersedes [[0003-private-repo-and-no-dev-fee]], which is kept in place and
marked superseded rather than deleted.

ADR-0003 rested on a premise that research on 2026-08-04 found to be false: that
this project needed `Muskwak/Open-Pearl-Miner`. It never did.
`pearl-research-labs/pearl` is **ISC** and supplies everything load-bearing —
the algorithm, the `miner_base` oracle, the Merkle commitment, `PlainProof` and
`verify_plain_proof`. Muskwak was only ever supplying a Stratum client and a
proof builder, and both have permissive replacements: `py-pearl-mining` (ISC)
builds and verifies the proof, and `arabel1a/ascend_prl` (MIT) is an
independently written Stratum implementation covering two pools.

So there is no fee to remove, no personal-use exemption to rely on, and no
requirement that this repo stay private. The full evidence, with verbatim
licence texts and URLs, is in
[`docs/research/2026-08-04-licensing-and-sources-for-a-public-metal-miner.md`](../research/2026-08-04-licensing-and-sources-for-a-public-metal-miner.md).

## What is decided

**Our code is Apache-2.0.** Chosen over ISC and MIT for its express patent
grant. Note what that grant does and does not do: it runs *from contributors to
users*, so it protects a user against a contributor who later asserts a patent.
It offers nothing at all against a patent held by a third party. It is still the
right licence; it is not a solution to the patent question below.

**Upstream is `pearl-research-labs/pearl`, ISC.** The root `LICENSE` is ISC and
its sub-project index names every exception — `node/`, `wallet/`, `spv/`,
`dnsseeder/`, `plonky2/`, `xmss/external/`, and NVIDIA's CUTLASS under
`miner/pearl-gemm/third_party/`. None of them covers a path we depend on. The
full tree of 4,870 entries holds 12 licence files and **none** sits under
`py-pearl-mining/`, `miner/miner-base/`, `pearl-blake3/` or `zk-pow/`.

GitHub's API reports the repo as `NOASSERTION`. That is its licence parser
giving up on the appended sub-project index, not a licensing problem. Do not
mistake a tool's label for a finding.

ISC's only obligation is reproducing the copyright notice and the permission
notice in all copies. We over-comply rather than reason about where the boundary
falls: the ISC text ships in the repo, in any release archive, and in
`--version` output, whether or not we vendor a single line of upstream code.

**`Muskwak/Open-Pearl-Miner` is barred absolutely.** Never cloned, never read,
never cited as evidence. Its licence mandates a 2% fee on "the Software or
derivative thereof" and does not define "derivative". Whether a Metal kernel
written after reading its CUDA is a derivative is an open question of law that
nobody needs to answer, because not opening the file makes it disappear.

ADR-0003 could afford to leave that question open: the personal-use exemption
covered a private repo. Publishing removes that cover entirely, so the bar is
now **stricter** than it was under ADR-0003, not looser.

The bar will come under pressure at one specific moment. Muskwak is the only
existing description of LuckyPool's Stratum dialect, and `ascend_prl` documents
Kryptex and K1Pool instead. If the pool survey concludes LuckyPool is the only
workable option, the answer is to reverse-engineer its dialect from logged wire
traffic. Observing a live protocol is not copying code, and it is how every
clean-room client has ever been written.

**No developer fee.** ADR-0003 removed Muskwak's 2% under an exemption; that
reason is gone, so fee-free is now a choice rather than an inheritance. The
ecosystem norm is a fee — Muskwak 2%, `minerjed` 2%, `ascend_prl` 1% — so this
is a real decision. It goes the other way on the arithmetic in
[[0002-backend-a-only]]: this machine earns about $0.06/day. One percent of that
is not income, it is a rounding error that costs a paragraph of explanation and
a quantity of goodwill.

`ascend_prl`'s README asks that its 1% fee not be zeroed without asking the
user. This is moot on the facts — that fee is a build flag in *their* binary and
we ship none of their code, so there is no fee of theirs to remove. What we take
from them is their documentation of the dialect problem, and the proportionate
response is loud attribution.

**Public at the release, not before.** The repo stays private through the build
and is published when the milestone lands. The operative rule in the meantime is
not "stay private" but **everything added must be publishable** — the constraint
that actually protects the release, and the one the old plan violated.

**Patents are documented, not searched.** ISC grants no patent licence, and
nobody has checked whether a patent covers Pearl's proof-of-useful-work
construction. We are not checking either. In US law, knowing about a patent you
are later found to infringe can raise the damages, so a search is not the
obviously-safe act it looks like. The exposure is identical for `OpenJarvis`,
`ascend_prl`, and Pearl Research Labs' own first-party miner. It is recorded
here so it is not rediscovered as a surprise.

## Consequences

**`Plan.md` §0.1 loses several of its citations.** Its evidence table sourced
the mandated dimensions, the `pow_key` identity, the digest bound and the
miner-chooses-A-and-B property to Muskwak's files. Those facts are not
un-known — but they are no longer *cited*, and under this ADR they cannot be
re-checked at their original source. Each one is re-verified against
`miner_base` in Phase 0.5 or deleted. The plan will briefly display fewer
verified facts than it did before this pivot. That is the pivot being honest.

**`HT = 16` is the worst casualty.** It came from Muskwak's `pool_common.py`
alone, and independent evidence now contradicts it. Phase 0.5 settles the tile
shape against `miner_base`, and the result gets its own ADR at that point —
recorded against evidence rather than in anticipation of it.

**Attribution is a shipped artifact, not a courtesy.** `NOTICE` credits Pearl
Research Labs (ISC — the algorithm, the oracle, the proof machinery),
`arabel1a/ascend_prl` (MIT — the dialect abstraction insight), and
`Yose144/Zion-v3.0.0` (MIT) if its kernel is read at all under
[[0006-built-for-other-people-to-run]].

**The name is `pearl-metal-miner`** — renamed 2026-08-04, while the repo had no
forks, no stars and no external links. Descriptive, findable, and unambiguously
third-party. The README carries "Not affiliated with Pearl Research Labs", which
costs one line and closes the trademark ambiguity that ISC is silent about. The
local working directory keeps its old path; only the remote was renamed.
