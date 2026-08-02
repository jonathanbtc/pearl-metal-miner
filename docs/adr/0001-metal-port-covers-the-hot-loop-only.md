# The Metal port covers the hot loop only; grid setup stays on the host

The CUDA backend's `p40_setup_job` generates the committed matrices with a
Philox RNG and computes their Merkle commitment entirely on the GPU. Mirroring
that in Metal would mean porting a bit-exact BLAKE3 Merkle tree over 512 MiB —
the second-riskiest component in the project after the PoW kernel itself. We
are not doing it. Metal implements noise generation, noise application,
transpose and the PoW kernel; the host generates the committed matrices and
computes the commitment.

This is safe for two reasons that are easy to miss:

1. **The committed matrices are miner-chosen.** The job fixes only the job key
   and the target. Nothing verifies *which* matrices we picked, only that the
   commitment matches the ones we actually mined. So the Philox RNG needs no
   port at all — any generator will do.
2. **A host commitment path already exists and is already bit-exact.**
   `pearl_host.commitment_hashes` computes it with the Rust `MerkleTree` from
   `py-pearl-mining`, and upstream documents it as validated against the GPU
   `tensor_hash` result.

## Consequences

Grid setup costs a second or two of host time per grid, against roughly 8192² =
67M hash tiles of mining in the same grid — low single-digit percent, and it
overlaps with the previous grid's sweep. If that ever stops being true, the GPU
path is the thing to reach for, not a micro-optimisation of the host path.

`metal_capi` is therefore **not** a drop-in replacement for `cuda_capi`:
`p40_setup_job` has no Metal implementation. The host-side miner loop has to be
adapted rather than reused verbatim.
