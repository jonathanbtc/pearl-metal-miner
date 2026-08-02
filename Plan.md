# Pearl Metal Miner — Build Plan

**Status:** current — supersedes the sealed plan of 2026-08-02 (see §0.2)
**Verification date:** 2026-08-02
**Target machine:** MacBook Pro, Apple M1 Max, 32 GB unified memory, 32-core GPU,
Metal 3, macOS 14.4.1 (23E224)

Every external claim carries a verification marker:

| Marker | Meaning |
| ------ | ------- |
| ✅ | Verified against the live source, API or hardware on 2026-08-02 |
| ⚠️ | Assumption. A named step in this plan settles it. Do not build on it before then. |
| ❌ | Claim that was checked and found false. Recorded so it is not reintroduced. |

Decisions live in `docs/adr/`. Vocabulary lives in `CONTEXT.md`. This file holds
only what to do, and in what order.

---

## TL;DR

Fork `Muskwak/Open-Pearl-Miner`. Keep its Stratum client and its proof builder
untouched. Write a Metal backend for the **mining hot loop only**, and a fresh
~200-line miner around it. Grid setup and the Merkle commitment stay on the
host.

The goal is **one accepted share on a pool dashboard**. It is not profit, and it
is not a public release.

The load-bearing constraint is that Pearl's proof-of-work folds a hash
transcript from the **cumulative int32 partial sums at every k-tile boundary**:

```text
correct   = identical bytes
incorrect = rejected share, silently
```

---

## 0. Ground truth

### 0.1 Verified

| Claim | Evidence |
| ----- | -------- |
| `Muskwak/Open-Pearl-Miner` is the right fork base ✅ | GitHub API. `python/{cuda_capi,pearl_host,miner_capi,pool_common,luckypool_miner}.py` and `csrc/{blake3,capi,gemm,tensor_hash}` all present. Last push 2026-07-05. |
| **The mandated dimensions are M = N = 131072, K = 4096, R = 256, HT = 16** ✅ | `python/pool_common.py:16-19`, and `real_config()` builds the `MiningConfiguration` with `common_dim=K, rank=R, mma_type=Int7xInt7ToInt32`. |
| **`miner_capi.py` is the torch-free miner; `luckypool_miner.py` is the torch one** ✅ | `miner_capi.py` docstring: *"Same pipeline as luckypool_miner.py but with NO torch."* `luckypool_miner.py` imports `torch` and `p40_pearl_gemm_cuda`. |
| **`p40_setup_job` generates A/B and commits them on the GPU** ✅ | `csrc/capi/p40_capi.cu:113` — `launch_fill_rand_i8` ×2 → `launch_transpose_i8` → `tensor_hash` ×2 → `commitment_hash_from_merkle_roots`. |
| **The miner chooses A and B; the job fixes only the key and target** ✅ | `miner_capi.mine_job` docstring: *"the job only fixes the key (from the header) and the target — the A,B matrices are miner-chosen (random Philox seed)."* |
| **`pow_key` is `noise_seed_A` (== commitment A), not the job key** ✅ | `luckypool_miner.py:248-250`, which warns that using the job key makes every win fail the verifier. |
| **The digest bound is `target × 16 × 16 × K`** ✅ | `miner_capi.mine_job`: `factor = cfg.hash_tile_h * cfg.hash_tile_w * cfg.rounded_common_dim; bound = min(target_int * factor, 2²⁵⁶−1)`. |
| **Upstream's licence mandates a 2% dev fee** ✅ | `LICENSE` clause 2, with a personal-use exemption in clauses 3–4. See [ADR-0003](docs/adr/0003-private-repo-and-no-dev-fee.md). |
| **Pool endpoints** ✅ | `miner_capi.py:41-42` — `pearl-eu2.luckypool.io:3360` (GPU difficulty), `pearl-cpu-eu1.luckypool.io:3370` (low difficulty). We use the latter. |
| **`py-pearl-mining` ships a reference miner and a verifier with a difficulty override** ✅ | `py-pearl-mining/src/lib.rs` — `mine(m,n,k,header,config,signal_range,wrong_jackpot_hash)` and `verify_plain_proof(header, proof, nbits_override=None)`. |
| **Runtime MSL compilation needs no Xcode; int32 MAC is exact on this GPU** ✅ | `tools/metal_probe.mm`, built with Command Line Tools only and run on this machine. See [ADR-0004](docs/adr/0004-no-xcode-runtime-shader-compilation.md). |
| **Economics** ✅ | hashrate.no, 2026-08-02: PRL $0.26, network 28.54 EH/s, block reward 2460 PRL, **$0.00829 per TH/s per day**. |

### 0.2 Checked and found false

The first eight were found before this plan's first draft. The rest were found
on 2026-08-02 by checking the earlier draft against upstream source, and each
one would have cost real time.

| Claim | Reality |
| ----- | ------- |
| `pip install py-pearl-mining` | ❌ Not on PyPI. It is a maturin/PyO3 Rust extension inside the monorepo, `requires-python >=3.12`. Build from source. |
| "No Apple pool share exists; we close that gap" | ❌ The paper reports pool-accepted shares across *"NVIDIA, AMD, CPU, and Apple Silicon"*. But see the next row — no Apple Silicon *miner* is public. |
| The paper's Metal source can be reused | ❌ `abhinaba/pearl-usefulness-gap` returns HTTP 404. No mirror. |
| M1 supports "Metal 3 and Metal 4" | ❌ Metal 3. Confirmed directly by `tools/metal_probe.mm`: `MTLGPUFamilyApple7` yes, `Apple8` no. |
| Backend B = `simdgroup_matrix` on int8 | ❌ MSL's `simdgroup_matrix` supports `half`/`float`/`bfloat` only. No integer variant on any Apple GPU, and no DP4A equivalent. |
| "Pearl matrices are −64…64, so accumulation is small" | ❌ That range is the **committed** matrices (`MMAType.Int7xInt7ToInt32`). The GEMM consumes the **noised, int8-clamped** operands, range ≈ ±127. |
| **R = 128** | ❌ **R = 256.** `pool_common.py:18`. The paper's figure is not this miner's constant. |
| **"Read the actual R from a real job"** | ❌ R is a **client-side constant**, not a job field. There is nothing to read. It must match consensus, so it is a thing to *verify*, not to discover. |
| **"Reuse `luckypool_miner.py` unchanged, inject the Metal backend"** | ❌ That file imports `torch` and calls the compiled torch extension `p40_pearl_gemm_cuda`, not `cuda_capi`. The torch-free path is `miner_capi.py`. |
| **"Commitments and Merkle stay on CPU — `pearl_host.py` already does this"** | ❌ Not in the path that matters: `miner_capi.mine_job` calls `cc.setup_job(...)` per grid, which commits **on the GPU**. A host path exists and we are choosing it ([ADR-0001](docs/adr/0001-metal-port-covers-the-hot-loop-only.md)) — but that is a decision, not a description of upstream. |
| **"`xcrun metal` missing is a BLOCKER"** | ❌ macOS ships the shader compiler inside the Metal framework. `newLibraryWithSource:` compiles at runtime with no Xcode, and the CLT SDK carries the Metal headers. Proven on this machine. |
| **"Verify locally before every submission"** (as written) | ❌ Misleading. `verify_proof_local(header, proof)` checks **block** difficulty — upstream's own log calls it *"informational"* and it returns `False` for valid shares. It only means something with `nbits_override` set to the pool's share difficulty. |
| **Stretch target ≥ 21,693 tiles/s** | ❌ Not a meaningful gate. Upstream's own logs put a Pascal card at ~7.25 TH/s ≈ **7.25M tiles/s** — ~334× the paper's M2 figure. Left as a curiosity, not a target. |
| **`MTLCreateSystemDefaultDevice()`** | ❌ Returns **nil** for a plain command-line binary on this machine. Use `MTLCopyAllDevices()[0]`. |

### 0.3 Local toolchain (measured)

```text
xcode-select -p     → /Library/Developer/CommandLineTools   (sufficient — see ADR-0004)
xcrun metal         → not found                              (NOT a blocker)
clang++             → Apple clang 15.0.0, arm64              OK
Metal.framework     → present in the CLT SDK                 OK
python3.12          → 3.12.1                                 OK
cargo               → not found                              ← the only real blocker
```

---

## 1. Definition of done

```text
M1 Max connects to LuckyPool's low-difficulty endpoint
→ receives a job
→ generates a grid and commits it on the host
→ mines it with Metal
→ finds a winning hash tile
→ builds a PlainProof and verifies it locally AT SHARE DIFFICULTY
→ submits it
→ the worker appears on the pool dashboard with an accepted share
```

**Economics, stated so they are not rediscovered later.** At $0.00829/TH/s/day,
upstream's Pascal card earns about **$0.06/day**. This machine draws 60–90 W
mining, i.e. **$0.25–0.75/day** of electricity. Mining loses roughly 9× what it
earns at any speed. Pool payout thresholds mean coins may never actually move.

**The milestone is the accepted share on the dashboard, not the coins.** This is
built because its owner wants it built. See
[ADR-0002](docs/adr/0002-backend-a-only.md) and
[ADR-0003](docs/adr/0003-private-repo-and-no-dev-fee.md).

---

## 2. The proof-of-work specification

Source: `csrc/gemm/pearl_pow_sm61.cu`, which documents itself as reproducing the
reference `noisy_gemm.py` → `_tiled_matmul` + `_check_pow_target`. ✅ The Python
reference lives in the monorepo at
`miner/miner-base/src/miner_base/`, **not** in the fork base.

### 2.1 Per-tile algorithm

For noised operands `A` (m × k) and `Bᵀ` (n × k), both int8, computed
independently per 16 × 16 hash tile:

```text
transcript[0..15] = 0

for t in 0 .. k/R - 1:                       # R = 256
    Csum += A[tile, t*R:(t+1)*R] @ Bt[tile, t*R:(t+1)*R]ᵀ    # CUMULATIVE int32
    h     = XOR over the 256 int32 of the CUMULATIVE Csum (as uint32)
    transcript[t % 16] = rotl32(transcript[t % 16], 13) ^ h   # HASH_ROT = 13

digest = BLAKE3(transcript[16 × u32, little-endian], key = pow_key)
tile wins if digest <= bound              # uint256, little-endian
```

With K = 4096 and R = 256 there are **16 fold points**, so each transcript slot
is written exactly once. `pow_key` is `noise_seed_A`. `bound` is the pool's
target multiplied by `16 × 16 × 4096`.

### 2.2 Consequences

1. **The transcript folds from the *cumulative* sum at every R-boundary.** You
   cannot compute a final tile and hash it. Every intermediate cumulative value
   must be bit-exact int32. This is the constraint the whole port serves.
2. **The k-loop granularity is fixed at R.** Never a tuning parameter.
3. **XOR is associative and commutative, so the 256-element reduction order is
   free.** ✅ Stated explicitly in the kernel comment. Use whatever Metal makes
   fast.
4. **Alignment:** `m % 16 == 0`, `n % 16 == 0`, `k % R == 0`. Partial tiles do
   not contribute and are out of scope. Do not "helpfully" handle them.
5. **BLAKE3 runs on the GPU**, keyed, over a single 64-byte block with
   `CHUNK_START|CHUNK_END|ROOT`. No chunking, no tree. **The same primitive also
   drives noise generation** (§2.3), so it is written once.

### 2.3 Noise

Source: `csrc/gemm/noising_sm61.cu` and `miner_base/noise_generation.py`. ✅

```text
EAL  [M, R]   dense int8, from keyed BLAKE3 of (index, seed)
EBR  [N, R]   dense int8, likewise
EAR, EBL      sparse int8, exactly one +1 and one −1 per K position

ApEA[m,k] = clamp_i8( A[m,k] + Σ_r EAL[m,r] · EAR_Rmaj[k,r] )
BpEB[n,k] = clamp_i8( B[n,k] + Σ_r EBR[n,r] · EBL_Rmaj[k,r] )
```

**The GEMM operand bound is therefore |operand| ≤ 127, not 64.**

Noise generation needs roughly 2.1M keyed BLAKE3 digests per grid. ⚠️ Python is
too slow for this (est. 7–10 s/grid) and `py-pearl-mining` does not expose it
separately, so it must be a Metal kernel. Settled in Phase 3.

---

## 3. Numeric exactness

**Backend A accumulates in int32 and is exact by construction.** Worst case is
`127 × 127 × 4096 = 66,064,384`, which fits int32 with three orders of magnitude
to spare.

This was not merely argued — `tools/metal_probe.mm` ran exactly that worst case
on this GPU on 2026-08-02 and returned 66,064,384 for 256/256 rows. ✅

**Why Backend B is deferred, kept here so the reasoning is not lost.**
`simdgroup_matrix` has no integer type, so it would accumulate in fp32, exact
only while every partial stays inside `[−2²⁴, 2²⁴]`:

```text
per R-chunk worst case:  127 × 127 × 256 = 4,129,024   vs  2²⁴ = 16,777,216
                         → 4.06× headroom, about 2 spare bits
full-K worst case:       127 × 127 × 4096 = 66,064,384  > 2²⁴
                         → fp32 CANNOT hold the cumulative sum. int32 is mandatory.
```

So the chunked shape would work in principle — but the argument also assumes
IEEE fp32 semantics from undocumented Apple matrix hardware, and a violation
would not crash, it would silently emit rejected shares. Backend B buys only
speed, and speed is worth $0.00 here. See
[ADR-0002](docs/adr/0002-backend-a-only.md).

**Non-negotiable:** fp16 is disqualified anywhere on this path. 11-bit mantissa.

---

## 4. Architecture

```text
 metal_miner.py        ← ours, ~200 lines: connect, grid, mine, throttle, submit
   ├── pool_common.py  ← upstream, UNCHANGED (Stratum client, mandated config)
   ├── pearl_host.py   ← upstream, UNCHANGED (commitment, proof, local verify)
   └── metal_capi.py   ← ours (ctypes → libp40metal.dylib)
         └── csrc/metal/  ← ours (Objective-C++ host + embedded MSL)
```

### 4.1 What Metal implements

Four kernels. Everything else is host-side.

| Kernel | Purpose |
| ------ | ------- |
| `blake3` | Keyed BLAKE3, single 64-byte block. Serves both noise generation and the jackpot digest. |
| `noise_gen` | EAL, EAR, EBL, EBR from the two noise seeds. |
| `noise_apply` | `ApEA`, `BpEB` — `clamp_i8(base + low-rank product)`. |
| `pow` | Fused: GEMM → cumulative int32 → transcript fold → BLAKE3 → target compare. Emits `found` and `coord` only. |

**Never materialise an output matrix.** At M = N = 131072 the full int32 output
would be 64 GiB. The operands are ~1 GiB total and fit comfortably.

### 4.2 What the host does

Generate A and B (any RNG — they are miner-chosen), compute the commitment via
`pearl_host.commitment_hashes`, build and verify the proof on a hit. See
[ADR-0001](docs/adr/0001-metal-port-covers-the-hot-loop-only.md).

`metal_capi` is therefore **not** a drop-in for `cuda_capi`: there is no
`p40_setup_job`. That is deliberate.

### 4.3 Device notes (measured, §0.1)

- Use `MTLCopyAllDevices()[0]`. `MTLCreateSystemDefaultDevice()` returns nil.
- **Threadgroup memory: 32,768 bytes.** The binding constraint on tiling. A
  16-row × 256-column int8 stage for each operand is 4 KB each — ample room.
- Max 1024 threads per threadgroup. A 16 × 16 tile maps to 256 threads.
- Unified memory: `MTLResourceStorageModeShared` everywhere; host/device copies
  are memory writes, not transfers.

### 4.4 Which CUDA path to read

Port from the **sm61 / Pascal** path. `pearl_pow_sm61.cu` (6 KB) is the readable
reference and carries a scalar int8 `#else` branch that is the direct model for
our kernel. `noising_sm61.cu`, `pearl_blake3_sm61.cu` and `rng_fill_sm61.cu`
cover the rest. **Do not read `pearl_ampere_tc.cu`** (62 KB, tensor-core
specific, no Apple analogue).

### 4.5 Out of scope

- Umbrel / `pearld` / P2Pearl. Revisit only after an accepted share, if ever.
- zk certificates (V1 ZkDense, V2 ZkMoe). Shares carry a `PlainProof` with an
  empty certificate slot. ✅
- Multi-GPU, solo mining, gateway mode, HiveOS packaging.
- Backend B, and any optimisation phase.

---

## 5. Build plan

### Phase 0 — Toolchain and wallet (2–3 hours)

**Gate:** `import pearl_mining` succeeds; a `prl1p…` address exists.

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install numpy blake3 pytest maturin

git clone https://github.com/pearl-research-labs/pearl.git   # default branch: master
cd pearl && git rev-parse HEAD > ../PINNED_PEARL_COMMIT.txt
cd py-pearl-mining && maturin develop --release && cd ../..
```

Import upstream's miner into this repo, preserving history:

```bash
git remote add upstream https://github.com/Muskwak/Open-Pearl-Miner.git
git fetch upstream
git merge --allow-unrelated-histories upstream/main
git rev-parse upstream/main > PINNED_MINER_COMMIT.txt
```

Install the official Pearl desktop wallet from
`pearl-research-labs/pearl` releases and record the receiving address.

No Xcode. No `metal` compiler. See [ADR-0004](docs/adr/0004-no-xcode-runtime-shader-compilation.md).

---

### Phase 1 — Prove the pool pipeline before writing any Metal (0.5 day)

**KPI:** an accepted share on the dashboard, produced by `pm.mine`.

This is the highest-value half-day in the plan. It exercises wallet, Stratum,
job parsing, proof serialisation, submission and acceptance — everything except
the GPU — while there is still nothing of ours to blame.

```text
[ ] Connect to pearl-cpu-eu1.luckypool.io:3370, authorize wallet.worker
[ ] Capture one real mining.notify; record job_id, header, target, difficulty
[ ] Assert the advertised config matches pool_common: M=N=131072, K=4096, R=256
[ ] Record the share difficulty  ← determines whether shares take minutes or days
[ ] Mine one proof with pm.mine() at reduced size/difficulty
[ ] Verify it with verify_plain_proof(header, proof, nbits_override=<share nbits>)
[ ] Submit it; confirm the pool accepts and the worker appears
```

If this phase cannot produce an accepted share, **stop**. Nothing downstream
can succeed, and the cause is not Metal.

---

### Phase 2 — Metal skeleton (0.5 day)

**KPI:** Python loads `libp40metal.dylib`, compiles all four kernels at startup,
runs a trivial one, and reads the result back.

```text
csrc/metal/
├── p40_metal.h
├── p40_metal.mm          ← MTLCopyAllDevices()[0]; newLibraryWithSource:
└── kernels/*.metal       ← embedded as strings at build time
python/metal_capi.py      ← ctypes, DBuf over MTLResourceStorageModeShared
tools/metal_probe.mm      ← already written and passing
packaging/build_macos.sh  ← clang++ only; no metallib step
```

Compile **every** kernel in a startup smoke test, so shader syntax errors
surface in one place rather than at first dispatch ([ADR-0004](docs/adr/0004-no-xcode-runtime-shader-compilation.md)).

---

### Phase 3 — Kernels, each bit-exact standalone (2.5–3 days)

**KPI:** every stage matches the Python reference on ≥1,000 random cases.

Test method throughout — live differential, no fixture files:

```python
ref = miner_base_reference(...)      # the monorepo's Python, called directly
gpu = metal_stage(...)
assert numpy.array_equal(gpu, ref)   # exact. no tolerance. ever.
```

Build in this order, each fully green before the next:

1. **`blake3`** — against `blake3.blake3(data, key=k).digest()`. Do this first;
   two later stages depend on it.
2. **`noise_gen`** — against `miner_base.noise_generation`. Same seeds, dims and
   rank must give identical bytes.
3. **`noise_apply`** — against the reference, including clamp behaviour.
   Instrument whether `clamp_i8` ever fires.
4. **`pow`** — against `miner_base.noisy_gemm`.

Coverage for the `pow` kernel:

```text
[ ] Cumulative Csum matches at EVERY R-boundary, not just the last
[ ] transcript[16] matches after every fold
[ ] Operand extremes: ±127, ±126, mixed signs, all-zero, alternating
[ ] Adversarial inputs maximising |cumulative Csum|
[ ] Digest matches blake3.blake3(transcript_bytes, key=noise_seed_A)
[ ] Target comparison correct (uint256, LITTLE-endian — verify the direction)
[ ] Small sizes for stage tests; mandated sizes only in Phase 5
```

The per-R-boundary check is the one that matters most: it is the only error
class that end-to-end testing cannot localise, and it fails silently.

---

### Phase 4 — Mining loop and intensity (0.5–1 day)

**KPI:** runs for an hour unattended; the machine stays usable throughout.

`metal_miner.py`: connect → job → generate grid → commit on host → sweep in
throttled bursts → on hit, build proof, verify at share difficulty, submit →
abandon the grid when a new job arrives.

**Intensity is a first-class control, not a polish item.**

- Mechanism: short dispatches with sleeps between them. Required anyway — macOS
  will kill a long-running GPU kernel — so throttling is just choosing the gap.
- `--intensity 0-100` sets the floor. After a few minutes with no keyboard or
  mouse input, ramp to 100; drop back to the floor the instant input resumes.
- **The dial must cover the CPU too.** The host commitment is a multi-core
  BLAKE3 burst of a second or two per job and is not affected by GPU throttling.
  Cap it via `RAYON_NUM_THREADS`, which `py-pearl-mining` reads. ✅ Without this,
  "gentle mode" will not feel gentle.

---

### Phase 5 — First accepted share (0.5 day)

**KPI:** the milestone.

Run at mandated dimensions against the low-difficulty endpoint. Record the
measured tiles/s — the first real Apple Silicon number for this algorithm, and
worth having even though nothing gates on it.

```text
[ ] Local verify at share difficulty passes before every submission
[ ] Pool returns result: true
[ ] Worker visible on the dashboard
[ ] 60 minutes unattended, no errors, machine usable
[ ] Rejected shares < 1% excluding stale jobs
```

---

## 6. Schedule

```text
Phase 0   Rust, py-pearl-mining, upstream import, wallet        2-3 hours
Phase 1   Prove the pool pipeline with pm.mine                  0.5 day
Phase 2   Metal skeleton                                        0.5 day
Phase 3   blake3 → noise_gen → noise_apply → pow, each exact    2.5-3 days
Phase 4   Mining loop, intensity dial, auto-idle                0.5-1 day
Phase 5   First accepted share                                  0.5 day
--------------------------------------------------------------------------
                                                                5-6 days
```

Down from 7–12, because Backend B, the optimisation phase, the tensor_hash port,
the Philox port, the fixture apparatus and the Xcode install are all gone.

---

## 7. Risks

| Risk | Severity | Mitigation |
| ---- | -------: | ---------- |
| One integer mismatch invalidates every share | Critical | Live differential per stage; per-R-boundary checks; ≥1,000 cases |
| Backend A too slow for shares to arrive | Medium ⚠️ | Estimated ~1 TH/s, **not measured**. Phase 1 records the real share difficulty; if the gap is hopeless, that is known on day one |
| Share difficulty higher than expected | Medium ⚠️ | Settled in Phase 1, before any Metal work |
| GPU BLAKE3 diverges from reference | High | Standalone test first, before two dependent stages |
| Reduction-order or endianness drift | Medium | XOR order is provably free (§2.2.3); endianness pinned in Phase 1 and rechecked in Phase 5 |
| Local verify gives false confidence | High | Always pass `nbits_override`; without it the check is theatre (§0.2) |
| Host commitment stalls a fast GPU | Medium | Overlap with the previous grid's sweep; revisit only if measured |
| Job changes mid-proof | Medium | Job IDs, abandon grid on new job, stale-proof rejection |
| Thermal throttling / unusable laptop | Medium | Intensity dial covering GPU **and** CPU; report sustained, not peak |
| Repo accidentally made public with the fee removed | Low, severe | [ADR-0003](docs/adr/0003-private-repo-and-no-dev-fee.md) records the tripwire |
| Upstream protocol change | Low | Both upstream commits pinned in Phase 0 |

---

## 8. Open questions

1. **How fast is Backend A really?** ⚠️ Estimated ~1 TH/s from hardware
   characteristics. Measured in Phase 5.
2. **What is LuckyPool's share difficulty on the low-difficulty endpoint?** ⚠️
   Answered in Phase 1.
3. **Does `pool_common`'s Stratum dialect still match the live pool?** ⚠️
   Upstream last changed 2026-07-05. Answered in Phase 1.
4. **Does the desktop wallet require a heavy chain sync?** ⚠️ Phase 0.
5. **Does `clamp_i8` ever fire?** ⚠️ The upstream comment implies it cannot.
   Instrumented in Phase 3. If it fires, re-read the noise model before trusting
   any bound.

---

## 9. Bottom line

Import upstream. Keep `pool_common` and `pearl_host` untouched. Write four Metal
kernels and a small miner around them.

Accumulate in **int32** — proven exact on this GPU, not merely argued. Fold the
transcript at **every** R-boundary from the **cumulative** sum. Commit on the
host. Never materialise an output matrix. Verify at **share** difficulty before
every submission.

Prove the pool pipeline with `pm.mine` before writing any Metal. Everything
downstream depends on that working, and none of it is your code.
