# Backend A only — no `simdgroup_matrix`, and optimisation only against a bar

> **Amended 2026-08-04** by [ADR-0006](0006-built-for-other-people-to-run.md). This ADR
> originally bundled two decisions — *no Backend B* and *no optimisation phase*
> — under one economic argument. That argument survives for the first and not
> the second. See **The amendment** below. Everything else stands.

> **Amended 2026-08-10**, when the optimisation the earlier amendment authorised
> was actually done and needed a sharper line than "never fp32". The shipped
> fast kernel (`pow_sweep_v2`, 0.12M → 2.31M tiles/s) accumulates each **k-chunk
> partial** in scalar **fp32 FMA with fast-math disabled**. This is exact, not
> approximate: every partial is an integer of magnitude ≤ R·127² = 2,064,512,
> comfortably below 2²⁴ where fp32 is integer-exact, and IEEE semantics are
> guaranteed by `fastMathEnabled = NO`. The **cumulative** tile sum, which
> exceeds 2²⁴ (up to 66,064,384), is held in **int32** exactly as before. The
> self-test proves the whole kernel byte-identical to the reference, including
> the ±127 adversarial cases that maximise the cumulative magnitude.
>
> So the rule is refined, not broken: **no `simdgroup_matrix` / undocumented
> matrix hardware** (that was the real risk — Backend B), and **no fp32 for any
> value that can exceed 2²⁴**. Scalar fp32 for a provably-bounded partial is
> exact and permitted. "Never fp32 anywhere" was a proxy for "never risk a
> silent rounding error"; the precise version of that is stated here.

The build plan specified two PoW kernels: Backend A (plain int32 arithmetic, exact by
construction) and Backend B (Apple's `simdgroup_matrix` fp32 hardware, exact
only if a numeric bound holds). We are building Backend A and nothing else.

The reason is economic, and it was measured rather than assumed. On 2026-08-02
PRL was $0.26 with a 28.54 EH/s network, paying $0.00829 per TH/s per day.
Upstream's own logs put an NVIDIA P40 at ~7.25 TH/s — about **$0.06/day**. An
M1 Max running flat out draws 60–90 W, i.e. **$0.25–0.75/day** of electricity.
Mining loses roughly 9× what it earns, at any speed. Backend B buys only speed.
Speed is worth nothing here, so its risk buys nothing either.

That risk was real. Because `simdgroup_matrix` has no integer type, Backend B
accumulates in fp32 and is exact only while every partial stays under 2²⁴. At
the true R of 256 (not the 128 originally assumed) the margin is 4.06×, about two
spare bits — and the exactness argument further assumes IEEE semantics from
undocumented Apple matrix hardware. A violation would not crash; it would
silently produce rejected shares.

The goal is therefore **one accepted share from a real pool**, by the most
boring correct route available.

## The amendment

**"No Backend B" survives untouched.** Its argument is about exactness, not
money, and does not care whether the coin is worth $0.26 or $2,600.

**"No optimisation phase" does not survive.** Its whole argument was *"speed is
worth nothing here"*, which was true when the audience was one person. Two
things changed it under [ADR-0006](0006-built-for-other-people-to-run.md):

1. **Speed gates the milestone.** The lowest difficulty LuckyPool advertises is
   2,000,000, and Backend A's ~1 TH/s is an estimate, not a measurement. If the
   kernel is too slow no share ever arrives, and the plan cannot reach its own
   definition of done. That is not a profit question.
2. **Speed is the product.** A stranger's M2 Air is considerably slower than
   this M1 Max. "We chose not to optimise because it wasn't worth money to the
   author" is not a sentence that belongs in a public README.

So optimisation is neither forbidden nor open-ended. It is **conditional on a
measured bar**: the Phase 1 pool survey yields the real share difficulty, which
yields a required tiles/s for a share in reasonable time. Miss the bar and
Backend A gets optimised — tiling, memory layout, occupancy, all within int32
exactness. Clear the bar and the work stops there. The bar is written down
before the measurement, not after, so it cannot be quietly moved.

## Consequences

Backend A must be fast enough that a share arrives in reasonable time, and
"fast enough" is now a number derived in Phase 1 rather than a hope. Phase 5
measures against it.

Backend B stays defined in [the glossary](../../CONTEXT.md) so the term keeps its meaning.
If it is ever revisited, the fp32 exactness bound must be re-derived at the R
in force at that time, and validated against the hardware, not the
specification.
