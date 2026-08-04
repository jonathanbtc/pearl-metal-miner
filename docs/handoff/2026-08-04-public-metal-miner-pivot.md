# Handoff — pivot to a public, fee-free Metal miner

**Date:** 2026-08-04
**For:** a fresh `/grill-with-docs` session
**Status:** decision taken in principle, docs and tracker not yet reconciled

Open a new session, point it at this file, and run `/grill-with-docs`. Everything
below is settled unless marked as an open question.

---

## The pivot, in one paragraph

The project was planned as a **private fork** of `Muskwak/Open-Pearl-Miner`,
removing that licence's mandated 2% developer fee under its personal-use
exemption — which is lawful only while the repo stays private
(ADR-0003). Research on 2026-08-04 established that **the fork was never
necessary**: `pearl-research-labs/pearl` is **ISC**, and it supplies the
algorithm, the oracle, the Merkle commitment, `PlainProof` and the verifier.
Muskwak was only ever supplying a Stratum client and a proof builder, both of
which have permissive replacements. So the project becomes a **public,
fee-free, Apache-2.0 repo built from ISC upstream**, with Muskwak dropped
entirely.

Full evidence, with verbatim quotes and URLs:
[`docs/research/2026-08-04-licensing-and-sources-for-a-public-metal-miner.md`](../research/2026-08-04-licensing-and-sources-for-a-public-metal-miner.md).

---

## Decisions already taken

| Decision | Value |
| -------- | ----- |
| Repo visibility | **Public** |
| Our licence | **Apache-2.0** — chosen for its express patent grant, which ISC and MIT lack |
| Upstream | `pearl-research-labs/pearl` (ISC) |
| `Muskwak/Open-Pearl-Miner` | **Dropped entirely.** Never merged, never read for porting. |
| Next flow step | `/grill-with-docs`, then `/to-tickets` to reconcile the tracker |

### Licence facts, verified twice

Root `LICENSE` of the monorepo is ISC. Its sub-project index names every
exception: `node/`, `wallet/`, `spv/`, `dnsseeder/`, `plonky2/`,
`xmss/external/`, and NVIDIA's CUTLASS under `miner/pearl-gemm/third_party/`.
The full tree — 4,870 entries, untruncated — holds 12 licence files, and **none
sits under `py-pearl-mining/`, `miner/miner-base/`, `pearl-blake3/` or
`zk-pow/`**. Every path we depend on is root ISC.

GitHub's API reports the repo as `NOASSERTION`. That is its parser giving up on
the appended sub-project index, **not** a licensing problem. Do not let a tool's
label be mistaken for a finding.

ISC's only obligation is reproducing the copyright notice and permission notice
in all copies. Relevant if we ever vendor upstream code; not triggered by merely
depending on it.

---

## Sources, and what each is for

| Source | Licence | Role |
| ------ | ------- | ---- |
| `pearl-research-labs/pearl` | ISC | Upstream. `miner_base` oracle, `py-pearl-mining` (Merkle commitment, `PlainProof`, `verify_plain_proof`), `pearl-blake3`. |
| `arabel1a/ascend_prl` | MIT | Reference for the **Stratum dialect abstraction**. From-scratch NPU miner with an independently written Stratum layer. |
| `Yose144/Zion-v3.0.0` | MIT | **Second opinion to diff the kernel against.** 23.8 KB Metal kernel for this PoW. Zero stars, no evidence of an accepted share — not a base to build on. |
| `open-jarvis/OpenJarvis` | Apache-2.0 | Reference for the Apple Silicon path. |

`ascend_prl`'s README carries a note asking that its dev fee not be zeroed
without asking the user. MIT permits zeroing it outright, so this is a courtesy
rather than a term — and it is close to moot for us, since we would read that
repo for its dialect abstraction and ship none of its code. Worth deciding
explicitly rather than by omission.

---

## Three premises that broke

The plan asserted a gap that is narrower than stated. Say this plainly in the
rewritten docs rather than letting it quietly disappear.

1. **"No public Apple Silicon Pearl miner exists" — false.**
   `open-jarvis/OpenJarvis` (Apache-2.0, 8,288 stars) ships one. It runs the
   matmuls through PyTorch MPS with hashing and proof construction on CPU, and
   its own docs place a native Metal kernel in the future ("v3"). It mines
   **solo against your own node, not to a pool** — so the pool path stays
   distinct from what it does.
2. **"No public Metal implementation of this PoW exists" — false.**
   `Yose144/Zion-v3.0.0` has one, structurally right in the ways that matter
   (rotation constant 13, cumulative int32, keyed BLAKE3 on the pow key).
3. **"Muskwak is the only Stratum description" — false.** `ascend_prl` has an
   independent one, and it documents that **Pearl pools use different
   dialects** — some dictate the dimensions and rank to the miner. A client
   hardcoded to one pool's shape will not port.

**What survives:** nobody has publicly demonstrated a **pool-accepted share
from a hand-written Metal kernel**. That is the honest remaining first. It is
narrower than the plan assumed. Per ADR-0002 the honest justification was
always "its owner wants it built" — no weaker now, and no longer requiring the
repo to be private.

---

## Two plan bugs, independent of the licensing decision

**1. Phase 1 points at an endpoint that may not exist.** LuckyPool's own API
advertises only ports 3360/3361/3362 at a **minimum difficulty of 2,000,000**,
and lists no CPU server. Port `3370` and `pearl-cpu-eu1` appear nowhere in the
pool's configuration or front-end bundle, though the hostname still resolves to
the same IP as the advertised EU server. Phase 1 is the designated "prove the
pipeline before writing any Metal" gate and cannot rest on an undocumented
endpoint. Verify it lives, or pick another pool, before anything depends on it.

The 2,000,000 minimum difficulty is now a **documented number** rather than an
unknown — but its units, and therefore the expected time to a share on this
hardware, are still unestablished. Do not compute a rate from it without
settling the units first.

**2. `Plan.md` §2.1's hash tile shape and target endianness are both in doubt.**
The independent Metal kernel compares the digest **big-endian** against our
stated little-endian; and both it and `py-pearl-mining`'s observed
`PeriodicPattern` output suggest a **4 × 8 periodic pattern** rather than a
contiguous 16 × 16 hash tile. These are exactly the silent-rejection failures
the plan is built to avoid. **Settle both against `miner_base` before writing
any kernel** — a morning's work now, a week of mystery later.

---

## Documents to rewrite

- **ADR-0003** — *supersede, do not amend.* Its entire premise (private repo,
  fee removed under a personal-use exemption) is gone. Replace with an ADR
  recording: public, Apache-2.0, built from ISC upstream, Muskwak dropped.
- **ADR-0002** — restate the justification against the narrowed premise above.
  Its reasoning about Backend A stands; only the "what makes this worth doing"
  paragraph needs revisiting.
- **ADR-0001** — **survives intact and is strengthened.** Its safety argument
  rests on `py-pearl-mining` providing an already-bit-exact host Merkle
  commitment, which is confirmed ISC-exported API, and OpenJarvis independently
  reached the same conclusion and demonstrated a verified proof on an Apple
  Silicon Mac in 0.119 s.
- **`Plan.md`** — §0.2 rows about the Apple Silicon gap, §4.4 ("port from the
  sm61 path" — we no longer read Muskwak's CUDA at all), §5 Phase 0 (no fork
  merge) and Phase 1 (endpoint), §2.1 (tile shape, endianness).
- **`CONTEXT.md`** — no known changes, but re-check "Backend A" and "Oracle"
  once the tile-shape question is settled.
- **`CLAUDE.md`** — the "must stay private" warning becomes wrong the moment
  ADR-0003 is superseded. Do not miss this one.

---

## Tracker state

14 issues on `jonathanbtc/perle-minig`, created 2026-08-02 from the old plan,
with native GitHub blocking edges wired.

- **#2 "Import the upstream miner and pin its commit" is ON HOLD** —
  `ready-for-agent` removed, comment explaining why. It merges Muskwak's code
  into this repo's history with `--allow-unrelated-histories`, and history is
  the one irreversible step in the plan. **Proposed fate: close as `wontfix`.**
- **#1 and #3 are the live frontier and are correct under either plan** — Rust
  toolchain plus `py-pearl-mining`, and the wallet. Safe to work now.
- **#4 needs rewriting** (verify the endpoint; use our own Stratum client).
- **#12 loses** its "upstream modules unmodified" acceptance criterion.
- **#7–#11, #13, #14 survive** essentially as written, though the kernel
  tickets change which source they read.

**Three new tickets proposed, not yet created:**

1. Stratum client, written against a **dialect abstraction** rather than
   hardcoded to one pool. This is the real work the fork was saving us, and the
   old plan was going to pay for it late instead of early.
2. **Settle hash tile shape and target endianness against the oracle.** Must
   block all four kernel tickets.
3. Public-readiness: our Apache-2.0 `LICENSE`, third-party notices, `README`,
   build instructions.

---

## Open questions for the grill session

1. **Does the milestone stay "one pool-accepted share"?** Apple Silicon Pearl
   mining is already public; a Metal kernel for this PoW is already public.
   Neither has produced a pool-accepted share from a hand-written Metal kernel.
   Is that narrower first still the goal?
2. **Standalone, or eventually contribute upstream?** OpenJarvis has explicitly
   declared a native Metal kernel as future work and a "Pearl upstream
   contribution". Building standalone first and contributing the kernel later
   is a plausible sequence, not necessarily a fork in the road today.
3. **Which pool, and at what difficulty?** Follows from plan bug 1.
4. **Do we adopt `ascend_prl`'s dialect abstraction shape, or design our own?**
5. **Patents.** ISC grants no patent licence, and nobody has checked whether a
   patent covers this proof-of-work construction. The exposure is identical for
   every existing Pearl miner including the first-party one, but it is not zero
   and it is not documented. Apache-2.0 was chosen partly for this reason —
   note that it grants patent rights *from our contributors* and protects
   against nothing held by third parties.

Questions 1 and 2 are the ones that shape everything else. Start there.
