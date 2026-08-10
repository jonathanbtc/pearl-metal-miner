# The hash tile is pattern-selected, and the partition is consensus

**Date:** 2026-08-09. Written at the close of Phase 0.5, against evidence from
the ISC upstream at the pinned commit (`PINNED_PEARL_COMMIT.txt`), verified by
executing `tools/phase05_experiments.py` on this machine — twenty live checks,
all green, including a `PlainProof` crafted by our own NumPy pipeline that
upstream's Rust verifier accepts, and a difficulty flip-point that lands on the
exact integer our digest computation predicts.

## What a hash tile actually is

The old plan carried three competing stories: a contiguous 16 × 16 block (from
the barred source), a 4 × 8 pattern (Zion, OpenJarvis smoke test), and open
doubt. All three were wrong in part. The truth, from
`zk-pow/src/api/proof_utils.rs` and `ffi/plain_proof.rs`:

- A tile is selected by **two `PeriodicPattern`s** — one over A's rows, one
  over Bᵀ's rows — each a generalized arithmetic progression encoded in 6
  bytes as three `(stride, length)` levels. Indices are
  `a·s₀ + b·s₁ + c·s₂`. The patterns and their dimensions are **job fields**,
  committed into the job key via the 52-byte `MiningConfiguration`; nothing
  about them is a client constant.
- The tile's row set is `t_rows + rows_pattern`, its column set
  `t_cols + cols_pattern`. `h = |rows_pattern|`, `w = |cols_pattern|`, with
  consensus constraints `2 | h`, `2 | w`, `32 ≤ h·w ≤ 256`
  (`sanity_checks.rs`).
- The reference CPU miner's example patterns are `[0, 8, 64, 72]` ×
  `[0, 1, 8, 9, 32, 33, 40, 41]`; the first-party GPU miner's settings are
  `[0, 8]` × the 64-index `[0,1,8,9,…,248,249]` (h·w = 128). A contiguous
  block is merely the degenerate pattern `[0…h-1]`.

## The finding that was almost missed

The base offsets `(t_rows, t_cols)` are **not free**. `list_to_pattern`
(`ffi/plain_proof.rs`) rejects any proof whose base fails
`pattern.offset_is_valid(offset)` — we proved this live (experiment E6: base 9
under pattern `[0,8,64,72]` → *"offset 9 is not valid for pattern"*). Valid
bases make the tiles **partition the output matrix exactly**: for the
production shapes, every output element belongs to exactly one tile. So the
search space per grid is `m·n / (h·w)` tiles, fixed by consensus — a miner can
neither skip the awkward ones nor invent extra ones.

Consequence for the kernel: the sweep enumerates
`{o ∈ [0,m) : rows_pattern.offset_is_valid(o)} × {o ∈ [0,n) : cols…}`, and
both dimensions must be multiples of the respective pattern periods.

## What else Phase 0.5 nailed down (summary)

- **Digest comparison is little-endian**, inclusive (`hash ≤ bound`), settled
  twice: `noisy_gemm.py` and `U256::from_little_endian` in
  `sanity_checks.rs`. Zion's big-endian comparison is its bug, not ours.
- **Bound = target × h × w × dot_product_length**, where
  `dot_product_length = k − k mod r`. The rank penalty multiplies by
  `PENALTY_BASE_RANK / r` (neutral at r = 128, halves at 256); it is
  fork-gated and applied by callers, not by `verify_plain_proof`.
- **Transcript**: 16 × u32, slot `(chunk_index) mod 16`, rotate-left 13 then
  XOR of the cumulative tile's element-XOR. Serialised little-endian into 64
  bytes; keyed BLAKE3 with `pow_key = a_noise_seed`.
- **No `clamp_i8` anywhere.** Committed elements are range-checked by the
  verifier to `[−64, +64]`; noise is `[−63, 63]` by construction; the GEMM
  consumes their **i32 sum** in `[−127, 127]`. The old clamp story is dead.
- **Every BLAKE3 the GPU needs is a single 64-byte-block keyed hash** (noise
  blocks and the jackpot digest). The chunked/Merkle hashing stays on the
  host in `pearl-blake3` via `py-pearl-mining`.

## Consequences

The Metal `pow` kernel's function constants are: `h`, `w`, the two pattern
shapes, `r`, `k`, and the noised-operand layout — all from the job. The
partition rule fixes the dispatch grid. The transcript fold and digest are
per-tile-local, so the kernel never materialises anything beyond h·w i32 per
tile in flight — exactly the design ADR-0001 assumed, now standing on
executed evidence rather than reading.

`pearl_metal_miner/reference.py` is the pinned NumPy restatement of all of
this; `tools/phase05_experiments.py` re-derives its authority from upstream on
demand. When upstream moves the pinned commit, run it again before trusting
anything above.
