# Pearl Metal Miner — Build Plan

**Status:** sealed
**Verification date:** 2026-08-02
**Target machine:** MacBook Pro, Apple M1 Max, 32 GB unified memory, 32-core GPU, Metal 3, macOS 14.4.1 (23E224)

Every external claim in this document carries a verification marker:

| Marker | Meaning |
| ------ | ------- |
| ✅ | Verified against the live source, API or hardware on 2026-08-02 |
| ⚠️ | Assumption. A named test in this plan settles it. Do not build on it before then. |
| ❌ | Claim that was checked and found false. Recorded so it is not reintroduced. |

---

## TL;DR

We are not writing a Pearl miner from zero. We fork `Muskwak/Open-Pearl-Miner`, keep its wallet, proof, Stratum and pool layers, and replace exactly one thing: the CUDA compute backend, with a bit-exact Metal backend.

The scope is **one backend port**, not a cryptocurrency implementation.

The single hardest constraint is not performance. It is that Pearl's proof-of-work folds a hash transcript from the **cumulative int32 GEMM partial sums at every k-tile boundary**. There is no tolerance anywhere in this pipeline:

```text
correct   = identical bytes
incorrect = rejected share
```

---

## 0. Ground truth established before planning

### 0.1 What was verified

| Claim | Status | Evidence |
| ----- | ------ | -------- |
| `Muskwak/Open-Pearl-Miner` exists, is the right fork base | ✅ | GitHub API. `python/{cuda_capi,pearl_host,luckypool_miner,gateway_client,mining_config}.py` and `csrc/{blake3,capi,gemm,tensor_hash}` all present. Language: Cuda. Last push 2026-07-05. |
| `pearl-research-labs/pearl` monorepo is live | ✅ | 282★, last push 2026-08-01. Default branch is **`master`**, not `main`. |
| Pearl Stratum V1 spec repo exists | ✅ | `nushypool/pearl_stratum_protocol_v1`, last push 2026-06-13. |
| arXiv 2606.04819 is real, and the 21,693 tiles/s M2 Metal figure is real | ✅ | "The Usefulness Gap in Proof-of-Useful-Work: An Empirical Study of Pearl's cuPOW Protocol", published 2026-06-03. Figure appears verbatim in the abstract. |
| M1 is GPU family Apple7 and supports `simdgroup_matrix` | ✅ | Apple7 introduced SIMD-scoped matrix ops (Metal 2.3+). Hardware confirms Metal 3 support. |
| A and Bᵀ fit in unified memory; the full output never can | ✅ | At M=N=131072, K=4096: each operand 131072 × 4096 × 1 B = 512 MiB, ~1 GiB total. Full int32 output would be 131072² × 4 B = 64 GiB. The miner must never materialize it. |

### 0.2 What was checked and found false

| Original claim | Status | Reality |
| -------------- | ------ | ------- |
| `pip install py-pearl-mining` | ❌ | Not on PyPI. Five name variants checked (`py-pearl-mining`, `py_pearl_mining`, `pypearl-mining`, `pearl_mining`, `pearlmining`) — all HTTP 404. It is a maturin/PyO3 Rust extension living at `py-pearl-mining/` inside the monorepo, version 0.2.0, `requires-python >=3.12`. Must be built from source. See Phase 0. |
| "No Apple pool share exists; we close that gap" | ❌ | The paper's own conclusion states 44 pool-accepted shares "across NVIDIA, AMD, CPU, and **Apple Silicon** hardware." A pool-accepted Metal share almost certainly already exists. This project is a personal milestone and a clean-room reimplementation, **not** a first. Do not frame it as one. |
| The paper's Metal source can be reused | ❌ | The paper's code repo `abhinaba/pearl-usefulness-gap` returns HTTP 404 — pulled or made private. GitHub repo search finds no mirror. We get no head start from it. |
| M1 supports "Metal 3 and Metal 4" | ❌ | This machine reports **Metal 3**. Metal 4 requires a far newer macOS. Compile with `-std=metal3.0`. Assume nothing from Metal 4. |
| Backend B = `simdgroup_matrix` on int8 | ❌ | MSL's `simdgroup_matrix<T,…>` supports `half` / `float` / `bfloat` only. There is **no integer variant on any Apple GPU** — this is a language-level absence, not an M1 limitation. Apple also exposes no DP4A-equivalent int8 dot product. The corrected design is §3. |
| "Pearl matrices are −64…64, so accumulation is small" | ❌ | That range applies to the **committed** matrices A and B, which the verifier range-checks (`MMAType.Int7xInt7ToInt32`). The operands that actually feed the PoW GEMM are the **noised, int8-clamped** matrices `ApEA` and `BpEB`, whose range is roughly ±126. This distinction drives the entire numeric-exactness analysis in §3. |

### 0.3 Local toolchain gaps (measured, not assumed)

```text
xcode-select -p     → /Library/Developer/CommandLineTools   (Command Line Tools only)
xcrun metal         → error: unable to find utility "metal"  ← BLOCKER
python3             → 3.10.2
python3.12          → 3.12.1                                 ← OK
cargo               → command not found                      ← BLOCKER
```

Two hard blockers before a single line of Metal can compile. Both are resolved in Phase 0.

---

## 1. Definition of done

```text
M1 Max connects to a Pearl pool
→ receives a job
→ generates valid Pearl PoW using Metal
→ builds a PlainProof
→ verifies it locally with py-pearl-mining
→ submits it
→ pool reports ACCEPTED
```

The first milestone is an **accepted share**, not profitability.

**Economics, stated plainly so it is not discovered later.** The paper this plan draws its benchmark from concludes that Pearl's PoUW performs zero useful AI computation and that mining is unprofitable at the PRL price it measured ($0.21) across every hardware class it tested — NVIDIA, AMD, CPU and Apple Silicon. This project is worth doing as an engineering exercise and for the accepted share. It is not worth doing for the yield. Nothing in this plan should be read as a profitability forecast.

---

## 2. The actual PoW specification

This is the part the previous draft got wrong, and it constrains every kernel decision. Source: `csrc/gemm/pearl_pow_sm61.cu`, which documents itself as reproducing the reference miner's `noisy_gemm.py` → `_tiled_matmul` + `_check_pow_target`. ✅

### 2.1 Per-tile algorithm

For noised operands `A` (m × k) and `Bᵀ` (n × k), both **int8**, computed independently per **16 × 16** output "hash" tile (`HT = 16`):

```text
transcript[0..15] = 0

for t in 0 .. k/R - 1:                       # k is tiled by R = noise rank
    Csum += A[tile, t*R:(t+1)*R] @ Bt[tile, t*R:(t+1)*R]ᵀ    # CUMULATIVE int32
    h     = XOR over the 256 int32 of the CUMULATIVE Csum (as uint32)
    transcript[t % 16] = rotl32(transcript[t % 16], 13) ^ h   # HASH_ROT = 13

digest = BLAKE3(transcript[16 × u32, little-endian], key = pow_key)
tile wins if digest <= pow_target        # uint256, little-endian
```

### 2.2 Consequences that shape the kernel

1. **The transcript folds from the *cumulative* sum, at every R-boundary.** You cannot compute a final 16×16 tile and hash it. Every intermediate cumulative `Csum` must be bit-exact int32 at each of the `k/R` boundaries. This is the load-bearing constraint of the whole port.
2. **The k-loop granularity is fixed at R.** It is not a free tuning parameter. Autotuning may vary threadgroup shape and staging, never the R-boundary fold points.
3. **XOR is associative and commutative, so the 256-element reduction order is irrelevant.** ✅ The kernel comment states this explicitly. This is real freedom: use any SIMD reduction order Metal makes fast.
4. **Alignment assumptions:** `m % 16 == 0`, `n % 16 == 0`, `k % R == 0`. Partial edge tiles and partial k-tiles **do not contribute** to the PoW in the reference and are out of scope. Do not "helpfully" handle them — that would diverge from consensus.
5. **BLAKE3 must run on the GPU.** It is a keyed BLAKE3 over a 64-byte transcript — a *single* keyed block with `CHUNK_START|CHUNK_END|ROOT` flags. No chunking, no tree, no parent nodes. This is a small, bounded port, but the previous draft omitted it entirely. Reference: `csrc/gemm/pearl_blake3_sm61.cu` and `csrc/blake3/`.

### 2.3 Noise structure

Source: `csrc/gemm/noising_sm61.cu`. ✅

```text
EAL  [M, R]   dense int8,  values in [-32, 32)
EBR  [N, R]   dense int8,  values in [-32, 32)
EAR, EBL      sparse int8, exactly one +1 and one −1 per K position

ApEA[m,k] = clamp_i8( A[m,k] + Σ_r EAL[m,r] · EAR_Rmaj[k,r] )
BpEB[n,k] = clamp_i8( B[n,k] + Σ_r EBR[n,r] · EBL_Rmaj[k,r] )
```

The kernel comment justifies the int8 fit as: `A ∈ [-63, 63]` and the noise term `∈ (-64, 64)`. The clamp is to full int8 range (±127) and is a safety net that essentially never fires.

**Therefore the GEMM operand bound is |operand| ≤ 127, and realistically ≤ 126.** Not 64.

---

## 3. Numeric exactness — the load-bearing analysis

`simdgroup_matrix` has no integer type, so any use of Apple's matrix hardware means float accumulation. Float accumulation is acceptable **only if it is provably exact for every representable input**. Here is that proof obligation, worked.

### 3.1 The bound

float32 represents every integer in `[−2²⁴, 2²⁴]` exactly, and `2²⁴ = 16,777,216`.

```text
Worst-case single R-chunk partial:   127 × 127 × R  =  16,129 · R
Exactness requires:                  16,129 · R  ≤  2²⁴
                                     R  ≤  1,040
```

With **R = 128** (the rank used in the paper's runs ⚠️ — read it from the job, never hardcode):

```text
127 × 127 × 128 = 2,064,512      vs  2²⁴ = 16,777,216
→ 8.1× headroom, about 3 spare bits.       SAFE
```

Every intermediate partial sum inside a chunk is an integer bounded by the same value, so every add is exact — integer + integer ≤ 2²⁴ never rounds.

### 3.2 Why the cumulative sum must stay int32

```text
Full-K cumulative worst case:  127 × 127 × 4096 = 66,064,384  >  2²⁴
→ needs 26 bits. float32 CANNOT hold it exactly.
```

**Correction to an earlier assessment in this project:** an intermediate draft argued that because elements are −64…64 and K = 4096, the accumulator peaks at exactly 64·64·4096 = 2²⁴ and fp32 is therefore exact across the whole K dimension. That is wrong. It used the committed-matrix range instead of the noised-operand range. With the true ±127 operand bound, full-K fp32 accumulation is off by a factor of ~4 and would silently corrupt shares.

### 3.3 The resulting design — and why it is natural

The algorithm already tiles k by R and already needs an exact int32 cumulative sum at each R-boundary. That is precisely the chunking that makes fp32 safe:

```text
per R-chunk:     fp32 simdgroup_matrix   (exact — 8× headroom, §3.1)
                        ↓ convert to int32 (exact, values well inside int32)
cumulative:      int32 accumulate         (exact — required by §2.2.1 anyway)
                        ↓
                 XOR-fold transcript at the R-boundary
```

The exactness requirement and the PoW's own structure agree. No K-splitting gymnastics are needed.

### 3.4 Non-negotiables

- **fp16 is disqualified.** 11-bit mantissa. Not remotely sufficient. Never use `simdgroup_matrix<half>` on this path.
- **`kIntToFp16ScaleFactor` and friends in `pearl_gemm_constants.hpp` belong to the CUDA *denoise* path, not the PoW path.** Do not import that scaling scheme into the Metal PoW kernel by pattern-matching.
- **Backend A must exist and must never be deleted.** It is the fallback if §3.1 fails for the job's actual R, and it is the differential oracle for Backend B forever.

---

## 4. Architecture

### 4.1 The interface to mirror — real, not invented

`metal_capi.py` must expose the same surface as `python/cuda_capi.py`. This is the **actual** exported C API, read from source ✅ — the previous draft invented a `PearlCandidate` struct that does not exist:

```c
/* lifecycle & memory */
int  p40_init(void);                  /* called at import time in cuda_capi.py — mirror this */
int  p40_device_count(void);
     p40_malloc(void**, size_t);
     p40_free(void*);
     p40_memcpy_htod(void*, void*, size_t);
     p40_memcpy_dtoh(void*, void*, size_t);
     p40_memset(void*, int, size_t);
     p40_sync(void);

/* data movement */
     p40_transpose_i8(src, dst, rows, cols, src_ld, col_off);

/* job + noise */
     p40_setup_job(A, B, Bt, key, nsA, nsB, M, N, K, R, seed /*u64*/);
     p40_noise_gen(EAL, EAR, EBL, EBR, key_A, key_B, m, n, k, R);
     p40_noise_apply_A(A, EAL, EAR_t, EBL_t, ApEA, AxEBL, M, K, R);
     p40_noise_apply_B(B, EBR, EAR, EBL, BpEB, EARxBpEB, N, K, R);
     p40_noise_gemm(X, Y, Z, out, M, K, R);   /* out = clamp_i8(Z + X @ Yᵀ over R) */

/* the PoW itself */
     p40_pearl_pow_split(A, Bt, m, n, k, R, key, target,
                         transcript, digests, found, coord, variant);
```

`p40_pearl_pow_split` contract, from the source docstring ✅:

- `transcript` — caller-owned reusable buffer, `≥ (m/16)·(n/16)·16` uint32.
- `digests` — `[num_tiles, 32]` uint8, **may be null**; mining only needs `found`/`coord`.
- `found` / `coord` — the only outputs the mining loop consumes. **No output matrix is ever returned.** The plan's original instinct here was right; only the struct was fictional.

Every function returns `0` on success; `cuda_capi._chk` raises otherwise. Mirror that convention exactly.

### 4.2 Library naming

`cuda_capi.py` loads `p40cuda.dll` on Windows, else **`libp40cuda.so`** — note `.so`, not `.dylib`. ✅ The macOS backend ships as **`libp40metal.dylib`** and `metal_capi.py` gets its own loader with the same search-path logic (next to the module, package root, `sys._MEIPASS` for frozen builds).

### 4.3 Selection

```python
if backend == "cuda":
    import cuda_capi as compute_backend
elif backend == "metal":
    import metal_capi as compute_backend
```

Pool, proof and orchestration layers stay unchanged.

### 4.4 Which CUDA path to port from

Port from the **sm61 / Pascal** path, not the Ampere tensor-core path.

| File | Size | Role |
| ---- | ---: | ---- |
| `pearl_pow_sm61.cu` | 6 KB | **The PoW reference.** Readable, fully documented, has a scalar int8 fallback next to the DP4A intrinsic that ports almost directly. |
| `pearl_pow_fused_sm61.cu` | 10 KB | Fused variant — the Phase 6 target shape |
| `noising_sm61.cu` | 5 KB | Noise application |
| `noise_gemm_sm61.cu` | 3.5 KB | `clamp_i8(Z + X@Yᵀ)` |
| `pearl_blake3_sm61.cu` | 3 KB | Keyed BLAKE3 on GPU |
| `rng_fill_sm61.cu` | 3.5 KB | Deterministic fill |
| ~~`pearl_ampere_tc.cu`~~ | 62 KB | **Do not port from this.** Tensor-core-specific, ten times the size, no analogue on Apple hardware. |

The sm61 path uses DP4A (`dp4a.s32.s32`) for the int8 contraction. Metal has no DP4A equivalent — that gap *is* the port. Usefully, the same file carries a `#else` scalar branch that extracts and multiplies int8 lanes explicitly; that branch is the direct model for Backend A.

### 4.5 Umbrel

Umbrel does not run Metal computation. Ever.

**V1** — MacBook runs pool client, Metal miner, proof builder, submission. Umbrel untouched.
**V2** — Umbrel runs `pearld` + gateway/P2Pearl + monitoring. MacBook is a mining worker only.

V2 begins only after the first accepted share. One open input: **what hardware is the Umbrel on** (Raspberry Pi / Umbrel Home / Intel-AMD mini-PC / other)? That decides whether `pearld` is even viable there.

---

## 5. Build plan

### Phase 0 — Toolchain

**Effort:** 2–4 hours (dominated by the Xcode download)
**KPI:** `xcrun metal -v` responds; `import pearl_mining` succeeds.

Both blockers from §0.3 are resolved here. This phase is entirely rewritten — the original `pip install py-pearl-mining` step could not have worked.

```bash
# ---- 1. Metal compiler --------------------------------------------------
# Command Line Tools do NOT ship the `metal` compiler. Full Xcode is required.
# macOS 14.4.1 caps you at the Xcode 15.x line (Xcode 16 requires macOS 14.5+).
# Install Xcode 15.4 from developer.apple.com/download (Apple ID required),
# OR update macOS first and take the current Xcode.
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcrun -sdk macosx metal -v            # MUST respond before Phase 2

# ---- 2. Rust + maturin (for py-pearl-mining) ----------------------------
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
cargo --version

# ---- 3. Python env ------------------------------------------------------
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install numpy blake3 pytest maturin

# ---- 4. Build py-pearl-mining FROM SOURCE (it is not on PyPI) -----------
git clone https://github.com/pearl-research-labs/pearl.git
cd pearl                              # NOTE: default branch is `master`
git rev-parse HEAD > ../PINNED_PEARL_COMMIT.txt   # pin it, §7 risk row
cd py-pearl-mining
maturin develop --release             # installs into the active venv
cd ../..

# ---- 5. Fork the miner --------------------------------------------------
git clone https://github.com/Muskwak/Open-Pearl-Miner.git
cd Open-Pearl-Miner
git rev-parse HEAD > ../PINNED_MINER_COMMIT.txt
git checkout -b feature/apple-metal

# ---- 6. Verify ----------------------------------------------------------
python - <<'PY'
import numpy, blake3, pearl_mining
print("NumPy:", numpy.__version__)
print("BLAKE3: OK")
print("pearl_mining: OK", getattr(pearl_mining, "__version__", "(no __version__)"))
PY
```

**Gate — all must pass before Phase 1:**

```text
[ ] xcrun -sdk macosx metal -v  responds
[ ] cargo --version  responds
[ ] import pearl_mining  succeeds
[ ] both upstream commits pinned to files
```

---

### Phase 1 — CPU oracle and the exactness decision

**Effort:** 1 day
**KPI:** 20/20 reduced-difficulty proofs verify locally, **and** the §3 exactness bound is confirmed against the job's real R.

Nothing is optimized here. Two jobs: build the oracle, and settle the one question that decides the Phase 3 kernel strategy.

#### 1a. Settle the exactness bound first

This is a half-hour of NumPy and it gates a multi-day design choice. Do it before anything else.

```text
[ ] Read the actual R (noise rank) from a real job — do not assume 128
[ ] Confirm operand range: instrument ApEA / BpEB, record true min/max
[ ] Assert 127² · R ≤ 2²⁴  (i.e. R ≤ 1040) for the observed R
[ ] Empirically confirm clamp_i8 fires never or almost never
[ ] Record the result in this repo as EXACTNESS.md
```

**Decision rule:**

| Outcome | Phase 3 strategy |
| ------- | ---------------- |
| `127² · R ≤ 2²⁴` | Backend B via fp32 `simdgroup_matrix` per R-chunk is **provably exact**. Build both backends. |
| `127² · R > 2²⁴` | Backend B as specified is **dead**. Backend A (manual int32) becomes the only path; performance targets in §6 must be renegotiated before committing further days. |

#### 1b. Build the oracle

The true reference is the miner-base `noisy_gemm.py` — `_tiled_matmul` and `_check_pow_target` — which is what `pearl_pow_sm61.cu` documents itself as reproducing. `pearl_host.py` (3.3 KB) sits *above* this, handling commitments, Merkle trees, `MatrixMerkleProof`, `PlainProof` and the call into Pearl's verifier. Both are needed; do not confuse their roles.

Deterministic fixtures must capture:

```text
header bytes                    noise seeds and rank R
mining configuration            EAL / EBR / EAR / EBL
A matrix, Bᵀ matrix             ApEA / BpEB (post-clamp)
expected commitment roots       cumulative Csum at EVERY R-boundary   ← critical
expected transcript[16]         expected per-tile BLAKE3 digest
expected winning row/col        serialized PlainProof
```

The per-R-boundary cumulative sums are the fixture that catches the class of bug that would otherwise only surface as a silently rejected share.

**Gate:**

```text
[ ] Commitment hashes match fixture
[ ] Noise generation matches reference bit-for-bit
[ ] ApEA / BpEB match reference (including clamp behaviour)
[ ] Cumulative Csum matches at EVERY R-boundary, not just the final one
[ ] transcript[16] matches after every fold
[ ] Keyed BLAKE3 digest matches blake3.blake3(transcript_bytes, key=pow_key)
[ ] Target comparison matches (uint256, LITTLE-endian — verify the direction)
[ ] Proof serialization round-trips
[ ] 20/20 reduced-difficulty proofs verify via py-pearl-mining
```

---

### Phase 2 — Metal backend skeleton

**Effort:** 1 day
**KPI:** Python loads `libp40metal.dylib` and runs a trivial kernel; `p40_init` / `p40_device_count` return sane values.

```text
csrc/metal/
├── p40_metal.h
├── p40_metal.mm
├── pearl_types.h
└── kernels/
    ├── gemm_baseline.metal
    ├── noise.metal
    ├── noise_gemm.metal
    ├── blake3.metal          ← omitted from the original plan; required by §2.2.5
    ├── transcript_fold.metal
    └── target_check.metal

python/metal_capi.py
packaging/build_macos.sh
tests/{test_metal_backend,test_metal_gemm_bitexact,test_metal_noise_bitexact,
       test_metal_blake3_bitexact,test_metal_pow_bitexact}.py
```

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build/macos"
mkdir -p "$BUILD"

for k in gemm_baseline noise noise_gemm blake3 transcript_fold target_check; do
  xcrun -sdk macosx metal -std=metal3.0 -O2 \
    -c "$ROOT/csrc/metal/kernels/$k.metal" -o "$BUILD/$k.air"
done

xcrun -sdk macosx metallib "$BUILD"/*.air -o "$BUILD/pearl.metallib"

clang++ -std=c++20 -O3 -dynamiclib -fobjc-arc \
  -framework Foundation -framework Metal \
  "$ROOT/csrc/metal/p40_metal.mm" -o "$BUILD/libp40metal.dylib"

echo "Built: $BUILD/libp40metal.dylib + $BUILD/pearl.metallib"
```

Two corrections to the original build script, both of which would have produced a library that builds and then fails at runtime:

1. **The metallib was compiled but never reachable.** `p40_metal.mm` must locate `pearl.metallib` at runtime via `newLibraryWithURL:`, resolved relative to the dylib's own path (`dladdr`), with an env override (`PEARL_METALLIB`) for development. Ship the two files together.
2. **`-framework MetalPerformanceShaders` was linked but is not used.** We write our own kernels precisely because MPS gives no bit-exactness guarantee on the integer path. Dropped.

`metal_capi.py` mirrors `cuda_capi.py` including its import-time `p40_init()` call and the `DBuf` wrapper (`offset`, `from_host`, `to_host`, `memset`, `free`).

---

### Phase 3 — Correctness-first GEMM

**Effort:** 2 days
**KPI:** zero mismatches across ≥1,000 randomized cases, on both backends.

#### Backend A — baseline, always kept

```text
signed char inputs
→ explicit sign extension (model on the #else branch of dp4a_pow in pearl_pow_sm61.cu)
→ int32 multiply-accumulate
→ threadgroup-memory tiles
→ exact 16×16 int32 output
```

No intrinsics. No cleverness. This is the oracle for Backend B and the fallback if §3 fails.

#### Backend B — Apple7 optimized, only if Phase 1a said yes

```text
fp32 simdgroup_matrix per R-chunk   (exact by §3.1 — NOT int8, NOT fp16)
→ exact int32 conversion at the R-boundary
→ int32 cumulative accumulate
→ XOR-fold transcript (any reduction order — XOR is commutative, §2.2.3)
→ packed int8 loads, double-buffered threadgroup memory
```

Before writing Backend B, confirm against the *installed* SDK headers which `simdgroup_matrix<T, R, C>` instantiations the M1 Max toolchain actually accepts. Do not assume an M2/M3 code path compiles or performs on Apple7.

#### Test methodology

```python
cpu = reference_gemm(A, B)          # int32
gpu = metal_gemm(A, B)
assert gpu.dtype == numpy.int32
assert numpy.array_equal(gpu, cpu)  # exact. no tolerance. ever.
```

```text
[ ] Operand extremes: −127, +127, −126, +126   (int8 range — NOT ±64)
[ ] Mixed signs, all-zero, alternating sign patterns
[ ] Adversarial: inputs maximizing |cumulative Csum| to probe the 2²⁴ boundary
[ ] Every R-boundary cumulative value, not just the final tile
[ ] Random matrices, ≥1,000 cases
[ ] Every edge tile at the 16-alignment boundary
[ ] Non-contiguous input explicitly rejected or normalized
[ ] Backend A vs Backend B differential — must be byte-identical
```

---

### Phase 4 — Full pipeline port

**Effort:** 2–4 days
**KPI:** Metal produces locally valid winning proofs at reduced difficulty.

**4.1 Buffers.** A `int8[M×K]`, Bᵀ `int8[N×K]`, Metal shared buffers, allocated once per job. Never re-copy per iteration.

**4.2 Commitments and Merkle — stay on CPU.** `pearl_host.py` already does this. Move to GPU only if profiling proves it is the bottleneck.

**4.3 Noise generation.** Port `noise_gen` / `noise_apply_A` / `noise_apply_B` / `noise_gemm` exactly per §2.3. Independent test: same key, dims, rank and seed → identical noise bytes.

**4.4 BLAKE3 in Metal.** Keyed, single 64-byte block, `CHUNK_START|CHUNK_END|ROOT`. Test standalone against `blake3.blake3(transcript_bytes, key=pow_key)` before wiring it into the PoW kernel.

**4.5 Fused PoW.** Per §2.1, at R granularity:

```text
load A/Bᵀ R-chunk → GEMM → int32 cumulative → XOR-reduce 256 → rotl32/XOR into
transcript[t%16] → after final t: keyed BLAKE3 → compare to target → discard tile
```

The GPU returns only `found`, `coord`, and optionally `digests`. Never an output matrix.

**4.6 Proof construction.** On `found`: Python extracts winning rows/cols → `pearl_host` builds the Merkle proof → `pearl_mining` verifies locally → pool client submits. Verify locally **before** every submission, always.

---

### Phase 5 — Pool integration

**Effort:** 0.5–1 day
**KPI:** first `ACCEPTED` share.

Route 1: reuse `luckypool_miner.py` unchanged, inject the Metal backend, submit through existing code. Only if that breaks, implement the documented V1 protocol (`mining.authorize` / `mining.notify` / `mining.submit`; job carries `job_id`, 76-byte hex `header`, 32-byte big-endian `target`, `height`, `difficulty`; submission carries job ID + base64 `PlainProof`).

Note the endianness asymmetry and do not let it drift: the Stratum **target** is documented big-endian, while the PoW **digest comparison** is little-endian (§2.1). Confirm both directions against the oracle in Phase 1.

```text
1. Connect                        6. Build PlainProof
2. Authorize wallet.worker        7. Verify locally  ← never skip
3. Receive mining.notify          8. Submit
4. Parse exact 76-byte header     9. result: true
5. Mine to advertised target     10. Worker visible on pool dashboard
```

---

### Phase 6 — Optimize

**Effort:** 2–5 days
**KPI:** stable, correct, sustained throughput.

| Gate | Target |
| ---- | -----: |
| Correctness | 0 mismatches |
| Local proof validity | 20/20 |
| Backend A vs B differential | byte-identical |
| Pool result | ≥1 accepted share |
| Stability | 60 min unattended, no error |
| Rejected shares | <1%, excluding stale jobs |
| Throughput — *measured baseline* | record M1 Max Backend A number first |
| Throughput — stretch | ≥21,693 tiles/s (published M2 Metal figure) |

**On the throughput numbers.** The original plan made "≥21,693 tiles/s" an *initial* gate. That is wrong twice over: it demands a first working kernel match someone's tuned result, and it compares against an unknown implementation. Your 32 GPU cores against a base M2's 10 gives real headroom, but headroom is not a guarantee — especially if Backend B rides the fp32 simdgroup rate rather than a native int8 rate that Apple does not expose. **Measure your own Backend A number, publish it in this repo, then optimize against yourself.** The M2 figure is a reference point, not an acceptance criterion. Correctness gates are hard; throughput gates are informational.

**Optimization order** (never trade correctness for any of these):

```text
1. Eliminate CPU↔GPU copies        6. Move target comparison onto GPU
2. Batch command-buffer dispatches 7. Proof building on a background CPU thread
3. Double-buffer work              8. Autotune threadgroup + staging
4. Fuse noise + GEMM               9. --intensity flag for thermal control
5. Fuse GEMM + transcript fold
```

Constraint on step 8: autotune threadgroup shape and staging freely; **never** move the R-boundary fold points (§2.2.2).

---

## 6. Risks

| Risk | Severity | Mitigation |
| ---- | -------: | ---------- |
| One integer mismatch invalidates every share | Critical | CPU oracle; per-R-boundary fixtures; ≥1,000 bit-exact cases; permanent A-vs-B differential |
| fp32 exactness fails for the job's real R | Critical | **Settled in Phase 1a, before any kernel work.** Backend A is the unconditional fallback |
| `simdgroup_matrix` has no int type | Certain, handled | Known ahead of time. fp32-per-R-chunk design (§3.3); Backend A never deleted |
| Reduction-order or endianness drift | High | XOR order is provably free (§2.2.3); endianness pinned in Phase 1 and re-checked in Phase 5 |
| GPU BLAKE3 diverges from reference | High | Standalone bit-exact test in 4.4 before integration |
| 1 GiB proof snapshot stalls a fast GPU | High | Shared buffers, background proof builder, double buffering. Upstream warns about this — it is architecture, not polish |
| Job changes mid-proof-construction | Medium | Job IDs, cancellation tokens, stale-proof rejection |
| Thermal throttling on a laptop | Medium | `--intensity`; report sustained not peak numbers |
| Upstream protocol change | Medium | Both upstream commits pinned in Phase 0 |
| Xcode 15.x ceiling on macOS 14.4.1 | Low | Accepted; Metal 3 is sufficient. Revisit only if a needed feature is 16-only |
| Umbrel architecture mismatch | Low initially | Umbrel is out of scope until after the first accepted share |

---

## 7. Schedule

```text
Day 1     Toolchain (Xcode, Rust, maturin, py-pearl-mining from source), fork, pins
Day 2     Phase 1a exactness decision → CPU oracle → per-R-boundary fixtures
Day 3     Metal skeleton, dylib loads, metallib resolution, trivial kernel
Day 4     Backend A baseline GEMM, bit-exact vs CPU
Day 5     Noise, transcript fold, GPU BLAKE3 — each bit-exact standalone
Day 6–7   Fused reduced-difficulty mining loop, local PlainProof verification
Day 8     Pool integration, first accepted-share attempt
Day 9–12  Backend B (if Phase 1a permits), dispatch/memory tuning, stability
--------  first accepted share is the milestone; everything below is V2 -------
Later     pearld/gateway on Umbrel, solo or P2Pearl, long-running packaging
```

**7–12 focused engineering days**, revised up from the original 5–10. The added days are Phase 0 (Xcode download plus a from-source Rust build that the original assumed was one `pip install`) and the GPU BLAKE3 port the original omitted. This still assumes the Python miner is reusable as-is and that no consensus arithmetic edge case appears.

---

## 8. Open questions

Tracked explicitly rather than assumed away.

1. **What is the job's real R?** ⚠️ The paper reports R = 128; the C API takes it as a runtime parameter. Phase 1a reads the real value. The whole Backend B decision hangs on it.
2. **Which `simdgroup_matrix` instantiations does the M1 Max toolchain actually accept?** ⚠️ Unanswerable until Xcode is installed. Check the SDK headers in Phase 2, not from documentation.
3. **What hardware runs your Umbrel?** Raspberry Pi / Umbrel Home / Intel-AMD mini-PC / other. Blocks V2 planning only.
4. **Does `clamp_i8` ever actually fire in practice?** ⚠️ The upstream comment implies it cannot. If it does, the noise model needs re-reading before trusting any bound.
5. **Is the reduced-difficulty path exercised the same way the pool path is?** Confirm the Phase 1 oracle and the Phase 5 pool path share one code path, so 20/20 local validity means something at production difficulty.

---

## 9. Bottom line

Fork `Open-Pearl-Miner`. Keep its host, proof and pool layers untouched. Replace `cuda_capi` with a bit-exact `metal_capi` that mirrors the real `p40_*` C API.

Port from the **sm61** path, not the Ampere path. Accumulate **fp32 per R-chunk, int32 cumulatively** — a design the PoW's own transcript structure hands you for free. Fold the transcript at **every** R-boundary from the **cumulative** sum. Never materialize an output matrix. Verify every proof locally before submitting.

Settle the Phase 1a exactness question before writing a single kernel. Everything else is downstream of that answer.
