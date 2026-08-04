# The Metal port covers the hot loop only; grid setup stays on the host

> **Amended 2026-08-04.** The decision and both its reasons stand — this is the
> ADR the pivot strengthened rather than damaged. But it was written citing a
> fork that is now barred ([[0005-public-apache-2-built-from-isc-upstream]]), so
> its evidence is re-anchored below to ISC upstream. The decision itself is
> unchanged.

GPU miners for this algorithm typically generate the committed matrices with a
device-side RNG and compute their Merkle commitment entirely on the GPU.
Mirroring that in Metal would mean porting a bit-exact BLAKE3 Merkle tree over
512 MiB — the second-riskiest component in the project after the PoW kernel
itself. We are not doing it. Metal implements noise generation, noise
application, transpose and the PoW kernel; the host generates the committed
matrices and computes the commitment.

This is safe for two reasons that are easy to miss:

1. **The committed matrices are miner-chosen.** Nothing verifies *which*
   matrices we picked, only that the commitment matches the ones we actually
   mined. So no RNG needs porting at all — any generator will do. (⚠️ Some pools
   dictate the dimensions, the rank and the pattern; nothing suggests any of
   them dictates the matrix *contents*. Confirmed in Phase 0.5.)
2. **A host commitment path already exists and is already bit-exact.**
   `py-pearl-mining` exports `MerkleTree` and the commitment machinery as ISC
   API. No wrapper from any fork is needed, and none is used.

Independent corroboration arrived on 2026-08-04 from an unrelated party.
`open-jarvis/OpenJarvis` reached the same conclusion in its own Phase 0 —
*"Phase 0 found the oracle already exists upstream"* — and recorded a full
mine-and-verify round trip on an Apple Silicon Mac in 0.119 s with
`verify_plain_proof` returning ok. The host path is not merely available;
someone has run it on this class of machine.

## Consequences

Grid setup costs a second or two of host time per grid, against an enormous
number of hash tiles of mining in the same grid — low single-digit percent, and
it overlaps with the previous grid's sweep. If that ever stops being true, the
GPU path is the thing to reach for, not a micro-optimisation of the host path.

The host commitment is a multi-core BLAKE3 burst, so it is **not** affected by
GPU throttling and must be capped separately for the intensity dial to mean
anything. `py-pearl-mining` reads `RAYON_NUM_THREADS`. See `Plan.md` Phase 4.

There is no CUDA API being mirrored, so there is no drop-in obligation to meet.
The miner loop is ours and is written around this split from the start, rather
than adapted from someone else's.
