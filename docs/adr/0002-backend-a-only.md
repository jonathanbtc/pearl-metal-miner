# Backend A only — no `simdgroup_matrix`, no optimisation phase

`Plan.md` specified two PoW kernels: Backend A (plain int32 arithmetic, exact by
construction) and Backend B (Apple's `simdgroup_matrix` fp32 hardware, exact
only if a numeric bound holds). We are building Backend A and nothing else, and
we are not running an optimisation phase.

The reason is economic, and it was measured rather than assumed. On 2026-08-02
PRL was $0.26 with a 28.54 EH/s network, paying $0.00829 per TH/s per day.
Upstream's own logs put an NVIDIA P40 at ~7.25 TH/s — about **$0.06/day**. An
M1 Max running flat out draws 60–90 W, i.e. **$0.25–0.75/day** of electricity.
Mining loses roughly 9× what it earns, at any speed. Backend B buys only speed.
Speed is worth nothing here, so its risk buys nothing either.

That risk was real. Because `simdgroup_matrix` has no integer type, Backend B
accumulates in fp32 and is exact only while every partial stays under 2²⁴. At
the true R of 256 (not the 128 `Plan.md` assumed) the margin is 4.06×, about two
spare bits — and the exactness argument further assumes IEEE semantics from
undocumented Apple matrix hardware. A violation would not crash; it would
silently produce rejected shares.

The goal is therefore **one accepted share from a real pool**, by the most
boring correct route available.

## Consequences

Backend A must still be fast enough that a share arrives in reasonable time. A
rough estimate puts it near 1 TH/s, which against a low-difficulty pool
endpoint should be ample — but it is an estimate, and it is the first thing to
check against a live job rather than to assume.

Backend B stays defined in [[../../CONTEXT.md]] so the term keeps its meaning.
If it is ever revisited, the fp32 exactness bound must be re-derived at the R
in force at that time, and validated against the hardware, not the
specification.
