# Pearl Metal Miner — Build Plan

**Status:** current — supersedes the plan of 2026-08-02 (see §0.2)
**Verification dates:** hardware and upstream source 2026-08-02; licensing,
sources and pool configuration 2026-08-04
**Target machine:** MacBook Pro, Apple M1 Max, 32 GB unified memory, 32-core GPU,
Metal 3, macOS 14.4.1 (23E224)

Every external claim carries a verification marker:

| Marker | Meaning |
| ------ | ------- |
| ✅ | Verified against the live source, API or hardware on the date given |
| ⚠️ | Assumption. A named step in this plan settles it. Do not build on it before then. |
| ❌ | Claim that was checked and found false. Recorded so it is not reintroduced. |

Decisions live in `docs/adr/`. Vocabulary lives in `CONTEXT.md`. This file holds
what to do, in what order, and the evidence for every number.

---

## TL;DR

Build from `pearl-research-labs/pearl` (ISC). Write our own Stratum client
against a **dialect seam**, our own Metal backend for the mining hot loop, and a
small miner around them. Grid setup and the Merkle commitment stay on the host,
using upstream's already-bit-exact Rust path.

The goal is **a usable release**: an accepted share from our own Metal kernel,
plus the licence, notices, README, clean-machine build and second working pool
that make it something another person can run. See
[ADR-0006](docs/adr/0006-built-for-other-people-to-run.md).

`Muskwak/Open-Pearl-Miner` is **not used, not cloned and not read**. See
[ADR-0005](docs/adr/0005-public-apache-2-built-from-isc-upstream.md).

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
| **`pearl-research-labs/pearl` is ISC, including every path we depend on** ✅ 08-04 | Root `LICENSE` read verbatim. Its sub-project index names every exception — `node/`, `wallet/`, `spv/`, `dnsseeder/`, `plonky2/`, `xmss/external/`, CUTLASS under `miner/pearl-gemm/third_party/`. Full tree of 4,870 entries holds 12 licence files; **none** under `py-pearl-mining/`, `miner/miner-base/`, `pearl-blake3/` or `zk-pow/`. GitHub's `NOASSERTION` label is its parser failing on the appended index, not a finding. |
| **`py-pearl-mining` ships a reference miner and a verifier with a difficulty override** ✅ 08-02 | `py-pearl-mining/src/lib.rs` — `mine(m,n,k,header,config,signal_range,wrong_jackpot_hash)` and `verify_plain_proof(header, proof, nbits_override=None)`. Exported ISC API. |
| **`miner_base` is the oracle and lives upstream, not in any fork** ✅ 08-02 | `miner/miner-base/src/miner_base/` — `noisy_gemm.py`, `noise_generation.py`. Independently confirmed by OpenJarvis's own Phase 0 write-up: *"Phase 0 found the oracle already exists upstream."* |
| **A verified proof runs on Apple Silicon today** ✅ 08-04 | OpenJarvis's recorded run: `macOS-26.4.1-arm64`, `mine(m=256,n=128,k=1024,rank=32)` in 0.119 s, `verify_plain_proof: ok=True`. Corroborates [ADR-0001](docs/adr/0001-metal-port-covers-the-hot-loop-only.md) from an unrelated party. |
| **R = 256 with K = 4096 is what real pools accept** ✅ 08-04 | `arabel1a/ascend_prl` README: *"`256` (K=4096) is the only rank real pools accept"*, and *"Real pool accepts only r=128 or 256."* An independent non-CUDA implementation. |
| **Pearl pools do not share one Stratum dialect** ✅ 08-04 | `ascend_prl/src/pools/pool.h`: *"mining params: miner-chosen (kryptex) or pool-dictated via `pearl.set_mining_params` (k1pool)"*, with `long m, n, k, rank; size_t rows[64], cols[64];` in the job struct. Two frontends, `kryptex.c` and `k1.c`. |
| **LuckyPool advertises three ports, minimum difficulty 2,000,000, and no CPU server** ✅ 08-04 | `https://pearl.luckypool.io/api/stats`, 50,307 bytes. `ports` = 3360 / 3361 / 3362 at 2,000,000 / 4,000,000 / 8,000,000. 19 stratum servers, none with `cpu` in the hostname. Front-end bundle contains zero occurrences of `3370` or `cpu-eu`. |
| **No first-party Pearl Stratum specification exists** ✅ 08-04 | LuckyPool's 389,726-byte front-end bundle contains **zero** occurrences of `mining.subscribe`, `mining.authorize`, `mining.notify`, `mining.submit` or `eth_submitLogin`. It documents connection only via third-party miner command lines. |
| **Runtime MSL compilation needs no Xcode; int32 MAC is exact on this GPU** ✅ 08-02 | `tools/metal_probe.mm`, built with Command Line Tools only and run on this machine. `127 × 127 × 4096 = 66,064,384` returned exactly, 256/256 rows. See [ADR-0004](docs/adr/0004-no-xcode-runtime-shader-compilation.md). |
| **Economics** ✅ 08-02 | hashrate.no: PRL $0.26, network 28.54 EH/s, block reward 2460 PRL, **$0.00829 per TH/s per day**. |

**Citations withdrawn under [ADR-0005](docs/adr/0005-public-apache-2-built-from-isc-upstream.md).**
The following were verified on 2026-08-02 against `Muskwak/Open-Pearl-Miner`.
That repository is now barred, so these facts can no longer be re-checked at
their original source and are **downgraded to ⚠️ until re-verified against
`miner_base` in Phase 0.5.** This is the honest cost of the pivot, not a
regression in what is true.

| Claim | Status |
| ----- | ------ |
| The mandated dimensions M = N = 131072, K = 4096 | ⚠️ Re-source. R = 256 and K = 4096 survive independently via `ascend_prl`. |
| **HT = 16 (a 16 × 16 hash tile)** | ⚠️ **Actively contradicted** — see §0.2 and §2.1. The single most important thing Phase 0.5 settles. |
| `pow_key` is `noise_seed_A`, not the job key | ⚠️ Re-source. Corroborated by `Zion`'s `a_noise_seed`, which is not an oracle. |
| The digest bound is `target × hash_tile_h × hash_tile_w × K` | ⚠️ Doubly unsourced — barred citation, *and* it multiplies by tile dimensions that are themselves in doubt. |
| The miner chooses A and B; the job fixes only key and target | ⚠️ Re-source. Partly contradicted: some pools dictate `m, n, k, rank` and the pattern. |
| `p40_setup_job` generates A/B and commits on the GPU | Deleted. It describes a codebase we do not use. |

### 0.2 Checked and found false

| Claim | Reality |
| ----- | ------- |
| `pip install py-pearl-mining` | ❌ Not on PyPI. A maturin/PyO3 Rust extension inside the monorepo, `requires-python >=3.12`. Build from source. |
| The paper's Metal source can be reused | ❌ `abhinaba/pearl-usefulness-gap` returns HTTP 404. No mirror. |
| M1 supports "Metal 3 and Metal 4" | ❌ Metal 3. `MTLGPUFamilyApple7` yes, `Apple8` no. Confirmed by `tools/metal_probe.mm`. |
| Backend B = `simdgroup_matrix` on int8 | ❌ MSL's `simdgroup_matrix` supports `half`/`float`/`bfloat` only. No integer variant on any Apple GPU, no DP4A equivalent. |
| "Pearl matrices are −64…64, so accumulation is small" | ❌ That is the **committed** matrix range. The GEMM consumes the **noised, int8-clamped** operands, which span the full int8 range. |
| **R = 128** | ❌ **R = 256** at K = 4096. Confirmed twice, independently. |
| **"Reuse `luckypool_miner.py` unchanged, inject the Metal backend"** | ❌ Moot — that repository is barred. We write our own miner. |
| **"`xcrun metal` missing is a BLOCKER"** | ❌ macOS ships the shader compiler inside the Metal framework. Proven on this machine. |
| **"Verify locally before every submission"** (as written) | ❌ Misleading. Verification checks **block** difficulty unless `nbits_override` is set to the pool's share difficulty. Without it the check is theatre. |
| **Stretch target ≥ 21,693 tiles/s** | ❌ Not a meaningful gate. A Pascal card reportedly does ~7.25 TH/s ≈ 7.25M tiles/s. The real gate is derived in Phase 1 — see [ADR-0002](docs/adr/0002-backend-a-only.md). |
| **`MTLCreateSystemDefaultDevice()`** | ❌ Returns **nil** for a plain command-line binary on this machine. Use `MTLCopyAllDevices()[0]`. |
| **"We must fork `Muskwak/Open-Pearl-Miner`"** | ❌ 08-04. Upstream is ISC and supplies the algorithm, the oracle, the commitment, `PlainProof` and the verifier. The fork supplied only a Stratum client and a proof builder, both of which have permissive replacements. |
| **"No public Apple Silicon Pearl miner exists"** | ❌ 08-04. `open-jarvis/OpenJarvis` (Apache-2.0, 8,288 stars) ships one — PyTorch MPS matmuls, CPU hashing and proof construction. But it mines **solo against your own node**: *"No multi-host pool. Solo mining only."* |
| **"No public Metal implementation of this PoW exists"** | ❌ 08-04. `Yose144/Zion-v3.0.0` (MIT) has 23.8 KB of it, structurally right on rotation constant 13, cumulative int32 and keyed BLAKE3 on the pow key. Correctness unverified: zero stars, no evidence of an accepted share. |
| **"R is a client-side constant, not a job field. There is nothing to read."** | ❌ 08-04. Some pools dictate `m, n, k, rank` and the pattern via `pearl.set_mining_params`. R must match consensus, so it is a value to **read and validate**, not to assume in either direction. |
| **"Muskwak is the only description of the Stratum protocol"** | ❌ 08-04. `ascend_prl` (MIT) has an independent one for two pools. It does **not** cover LuckyPool — see §5 Phase 1. |

### 0.3 Local toolchain (measured 2026-08-02)

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
M1 Max connects to the chosen pool
→ receives a job
→ generates a grid and commits it on the host
→ mines it with our Metal kernel
→ finds a winning hash tile
→ builds a PlainProof and verifies it locally AT SHARE DIFFICULTY
→ submits it
→ the worker appears on the pool dashboard with an accepted share
```

**and** the result is something another person can run:

```text
→ LICENSE (Apache-2.0), NOTICE (ISC text + attributions)
→ README stating what is verified, on what, and by whom
→ a build script that works on a machine that is not this one
→ `--self-test` proving bit-exactness against the oracle on the user's own Mac
→ a second pool dialect, tested, not merely written
```

**Economics, stated so they are not rediscovered later.** At $0.00829/TH/s/day, a
Pascal card earns about **$0.06/day**. This machine draws 60–90 W mining, i.e.
**$0.25–0.75/day** of electricity. Mining loses roughly 9× what it earns at any
speed. Pool payout thresholds mean coins may never actually move.

**The milestone is the release, not the coins.** See
[ADR-0002](docs/adr/0002-backend-a-only.md),
[ADR-0005](docs/adr/0005-public-apache-2-built-from-isc-upstream.md) and
[ADR-0006](docs/adr/0006-built-for-other-people-to-run.md).

---

## 2. The proof-of-work specification

Source: `miner/miner-base/src/miner_base/` in the ISC monorepo — `noisy_gemm.py`
(`_tiled_matmul`, `_check_pow_target`) and `noise_generation.py`. This is the
**oracle**. Where our output and its output disagree, we are wrong.

### 2.1 Per-tile algorithm

For noised operands `A` (m × k) and `Bᵀ` (n × k), both int8, computed
independently per **hash tile**:

```text
transcript[0 .. T-1] = 0

for t in 0 .. k/R - 1:
    Csum += A[pattern_rows, tR:(t+1)R] @ Bt[pattern_cols, tR:(t+1)R]ᵀ  # CUMULATIVE int32
    h     = XOR over all elements of the CUMULATIVE Csum (as uint32)
    transcript[t % T] = rotl32(transcript[t % T], HASH_ROT) ^ h

digest = BLAKE3(transcript as u32, key = pow_key)
tile wins if digest <= bound
```

**Every parameter in that listing, with its current status:**

| Parameter | Value | Status |
| --------- | ----- | ------ |
| `HASH_ROT` | 13 | ✅ Independently corroborated by `Zion`'s `LROT = 13` |
| Fold points | at every R-boundary, from the **cumulative** sum | ✅ The constraint the whole port serves |
| `pow_key` | `noise_seed_A` (the A-side commitment hash) | ⚠️ Re-source in Phase 0.5. Corroborated by `Zion`'s `a_noise_seed` |
| Hash tile dimensions | ? | ⚠️ **Phase 0.5.** Plan previously said 16 × 16 from a now-barred source; `Zion` uses 4 × 8; OpenJarvis's rank-32 smoke test printed 4 row indices and 8 column indices |
| Tile selection | pattern (row/column index lists) or contiguous block? | ⚠️ **Phase 0.5.** `py-pearl-mining` exports `PeriodicPattern`; `ascend_prl` carries `rows[64]`/`cols[64]` |
| `T` (transcript slots) | 16 | ⚠️ Phase 0.5. `Zion`'s `JACKPOT_SIZE = 16`, and its `% JACKPOT_SIZE` implies slots can be written more than once when k/R > T |
| Transcript serialisation | u32 little-endian | ⚠️ Phase 0.5 |
| `bound` | `target × tile_h × tile_w × k` | ⚠️ Phase 0.5. Depends on the tile dimensions above |
| Digest comparison | little-endian **or** big-endian? | ⚠️ **Phase 0.5.** Plan says little-endian; `Zion` compares `hash[i]` against `target[i]` from index 0 upward, i.e. big-endian. One of them is wrong |

The last two ⚠️ rows and the tile-shape rows are the whole reason Phase 0.5
exists. Each is a silent-rejection failure: get one wrong and the miner runs
perfectly, finds wins, submits them, and every one is refused with no diagnostic
that points at the cause.

### 2.2 Consequences

1. **The transcript folds from the *cumulative* sum at every R-boundary.** You
   cannot compute a final tile and hash it. Every intermediate cumulative value
   must be bit-exact int32. This is the constraint the whole port serves.
2. **The k-loop granularity is fixed at R.** Never a tuning parameter.
3. **XOR is associative and commutative, so the reduction order within a fold is
   free.** ✅ Use whatever Metal makes fast.
4. **Alignment:** `k % R == 0`, and the tile dimensions must divide m and n.
   Partial tiles do not contribute and are out of scope. Do not "helpfully"
   handle them.
5. **BLAKE3 runs on the GPU**, keyed, over a single 64-byte block with
   `CHUNK_START|CHUNK_END|ROOT`. No chunking, no tree. **The same primitive also
   drives noise generation** (§2.3), so it is written once.

### 2.3 Noise

Source: `miner_base/noise_generation.py`. ✅

```text
EAL  [M, R]   dense int8, from keyed BLAKE3 of (index, seed)
EBR  [N, R]   dense int8, likewise
EAR, EBL      sparse int8, exactly one +1 and one −1 per K position

ApEA[m,k] = clamp_i8( A[m,k] + Σ_r EAL[m,r] · EAR_Rmaj[k,r] )
BpEB[n,k] = clamp_i8( B[n,k] + Σ_r EBR[n,r] · EBL_Rmaj[k,r] )
```

**The GEMM operand bound is therefore the full int8 range, not the committed
matrices' narrower one.** This distinction has already caused one wrong design.

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

The chunked shape would work in principle — but the argument assumes IEEE fp32
semantics from undocumented Apple matrix hardware, and a violation would not
crash, it would silently emit rejected shares. In a miner other people run, that
is not a risk to take for speed. See
[ADR-0002](docs/adr/0002-backend-a-only.md).

**Non-negotiable:** fp16 is disqualified anywhere on this path. 11-bit mantissa.

---

## 4. Architecture

Everything here is ours. No upstream Python module is vendored; `py-pearl-mining`
is called as the ISC-licensed Rust extension it is.

```text
pearl_metal_miner/
  miner.py          ← connect, job, grid, mine, throttle, submit
  selftest.py       ← live differential vs the oracle, user-facing
  host.py           ← commitment + PlainProof + verify, via py-pearl-mining (ISC)
  metal_capi.py     ← ctypes → libpearlmetal.dylib
  stratum/
    dialect.py      ← the seam: handshake, notify parsing, submit framing,
                      difficulty/target normalisation, who chooses the params
    <pool>.py       ← one module per dialect
csrc/metal/         ← Objective-C++ host + embedded MSL
```

### 4.1 What Metal implements

Four kernels. Everything else is host-side.

| Kernel | Purpose |
| ------ | ------- |
| `blake3` | Keyed BLAKE3, single 64-byte block. Serves both noise generation and the tile digest. |
| `noise_gen` | EAL, EAR, EBL, EBR from the two noise seeds. |
| `noise_apply` | `ApEA`, `BpEB` — `clamp_i8(base + low-rank product)`. |
| `pow` | Fused: GEMM → cumulative int32 → transcript fold → BLAKE3 → target compare. Emits `found` and `coord` only. |

**Never materialise an output matrix.** At M = N = 131072 the full int32 output
would be 64 GiB. The operands are ~1 GiB total and fit comfortably.

### 4.2 Nothing a pool might dictate is hardcoded

Tile dimensions, rank and the pattern come from the job. They are passed as
Metal **function constants** at library-creation time, so the shader compiler
folds them into the generated code exactly as if they had been literals — full
loop unrolling and constant propagation, with no portability lost. This works
only because [ADR-0004](docs/adr/0004-no-xcode-runtime-shader-compilation.md)
already compiles MSL at process start; a precompiled `.metallib` could not do
it. Recompilation is needed only when a job changes the shape, which is rare.

### 4.3 What the host does

Generate A and B, compute the commitment via `py-pearl-mining`'s `MerkleTree`,
build and verify the proof on a hit. See
[ADR-0001](docs/adr/0001-metal-port-covers-the-hot-loop-only.md).

### 4.4 Device notes (measured 2026-08-02)

- Use `MTLCopyAllDevices()[0]`. `MTLCreateSystemDefaultDevice()` returns nil.
- **Threadgroup memory: 32,768 bytes** on this device. The binding constraint on
  tiling. ⚠️ Whether the same limit holds on Apple8/Apple9 is unverified — query
  it at runtime and refuse to dispatch a tiling that will not fit, rather than
  assuming this machine's number.
- Max 1024 threads per threadgroup on this device. Query, do not assume.
- Unified memory: `MTLResourceStorageModeShared` everywhere; host/device copies
  are memory writes, not transfers.

### 4.5 What we read, and in what order

**Barred entirely:** `Muskwak/Open-Pearl-Miner` and `minerjed/open-pearl-miner`
(same custom fee licence). Never cloned, never read, never cited.
[ADR-0005](docs/adr/0005-public-apache-2-built-from-isc-upstream.md).

**The oracle first, always:** `miner_base` (ISC). It defines correctness.

**Then, as cross-checks only, never as sources to transliterate:**

- `arabel1a/ascend_prl` (MIT) — for the dialect seam's *shape*, not its code.
- `Yose144/Zion-v3.0.0` (MIT) — for Metal-specific engineering only
  (threadgroup layout, memory strategy), and **only after Phase 0.5** has
  settled the facts. Read before that, it would anchor us on an unverified
  implementation whose endianness and tile shape are both suspect. Read after,
  every disagreement is immediately legible as its bug or ours.
- `open-jarvis/OpenJarvis` (Apache-2.0) — for the Apple Silicon host path.

MIT and ISC notices are carried in `NOTICE` regardless of how little is taken.

### 4.6 Out of scope

- Umbrel / `pearld` / P2Pearl / solo mining.
- zk certificates (V1 ZkDense, V2 ZkMoe). Shares carry a `PlainProof` with an
  empty certificate slot. ✅
- Multi-GPU, gateway mode, HiveOS packaging.
- Backend B.
- Non-Apple-Silicon hardware.

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

Install the official Pearl desktop wallet from `pearl-research-labs/pearl`
releases and record the receiving address.

No Xcode. No `metal` compiler. No fork merge — nothing is imported into this
repo's history.

---

### Phase 0.5 — Settle the specification against the oracle (0.5 day)

**Gate: every ⚠️ in §2.1's parameter table becomes ✅ or ❌.**
**Blocks every kernel in Phase 3. Nothing GPU-shaped starts before this is green.**

This is the cheapest half-day in the plan. Each item below is a silent-failure
mode: get it wrong and the miner works, finds wins, submits them, and every one
is refused with nothing to point at.

```text
[ ] Hash tile — dimensions, and whether it is a contiguous block or selected by
    a pattern of row/column indices
[ ] Whether tile dimensions, rank and pattern are job fields, client constants,
    or both depending on the pool
[ ] Target comparison endianness — little or big
[ ] The bound factor formula, in terms of the tile dimensions just settled
[ ] Transcript length T, the fold index formula, and its serialisation
[ ] HASH_ROT, re-confirmed at the oracle
[ ] pow_key == noise_seed_A, re-sourced to miner_base
[ ] The miner-chooses-A-and-B property, and what a pool may override
[ ] Element ranges: committed matrices vs noised operands, at the oracle
[ ] M, N, K and the R/K constraint
```

Method: read `miner_base` and, where reading is ambiguous, *run* it — the
reference miner produces observable output at small sizes in a fifth of a
second on this class of machine. A printed value beats an inferred one.

Update §2.1's table and `CONTEXT.md` as each lands. Write the tile-shape ADR at
the end of this phase, when it can be recorded against evidence.

---

### Phase 1 — Pool survey, then prove the pipeline (1 day)

**KPI:** an accepted share on a dashboard, produced by the reference miner, on a
pool we have chosen with evidence.

Dropping the fork dropped the only existing description of **LuckyPool's**
dialect. `ascend_prl` documents Kryptex and K1Pool instead. So the pool question
is now open, and it is answered by measurement rather than by inheritance.

**1a — Survey.** A throwaway script that connects, authorises and logs both
directions verbatim. For each of LuckyPool (3360, and probe the undocumented
`pearl-cpu-eu1:3370`), Kryptex and K1Pool:

```text
[ ] Does the endpoint accept a connection at all
[ ] The handshake, verbatim
[ ] Does the pool dictate m, n, k, rank and the pattern, or does the miner choose
[ ] The real share difficulty — and its UNITS. Do not compute a rate from
    a number whose units are unestablished
[ ] Whether the advertised configuration matches what Phase 0.5 settled
```

**1b — Choose.** Primary pool and second pool, from the survey. Prior favours
Kryptex and K1Pool, because `ascend_prl` documents their dialects and nothing
documents LuckyPool's; and because K1Pool's pool-dictates-parameters variant
forces the dialect seam to be real rather than decorative. If LuckyPool wins
anyway, its dialect is reverse-engineered from the logged traffic — never from
the barred source.

**1c — Derive the bar.** Share difficulty → required tiles/s for a share in
reasonable time. Write it down **now**, before any measurement exists to move it
against. This is the optimisation gate in
[ADR-0002](docs/adr/0002-backend-a-only.md).

**1d — Prove the pipeline.**

```text
[ ] Mine one proof with the reference miner at reduced size/difficulty
[ ] Verify it with verify_plain_proof(header, proof, nbits_override=<share nbits>)
[ ] Submit it; confirm the pool accepts and the worker appears
```

If 1d cannot produce an accepted share, **stop**. Nothing downstream can
succeed, and the cause is not Metal.

---

### Phase 2 — Metal skeleton (0.5–1 day)

**KPI:** Python loads `libpearlmetal.dylib`, compiles all four kernels at
startup with function constants bound, runs a trivial one, and reads the result
back.

```text
csrc/metal/
├── pearl_metal.h
├── pearl_metal.mm        ← MTLCopyAllDevices()[0]; newLibraryWithSource:
│                            + MTLFunctionConstantValues for the job shape
└── kernels/*.metal       ← embedded as strings at build time
pearl_metal_miner/metal_capi.py   ← ctypes, DBuf over MTLResourceStorageModeShared
tools/metal_probe.mm              ← already written and passing
packaging/build_macos.sh          ← clang++ only; no metallib step
```

Compile **every** kernel in a startup smoke test, so shader syntax errors
surface in one place rather than at first dispatch
([ADR-0004](docs/adr/0004-no-xcode-runtime-shader-compilation.md)). Query
threadgroup memory and max threads at runtime; refuse a tiling that will not
fit rather than assuming this machine's numbers.

---

### Phase 3 — Kernels, each bit-exact standalone (3–3.5 days)

**KPI:** every stage matches the oracle on ≥1,000 random cases, via a runner
that ships as `--self-test`.

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
[ ] The transcript matches after every fold
[ ] Operand extremes: ±127, ±126, mixed signs, all-zero, alternating
[ ] Adversarial inputs maximising |cumulative Csum|
[ ] Digest matches blake3.blake3(transcript_bytes, key=noise_seed_A)
[ ] Target comparison correct, in the endianness Phase 0.5 established
[ ] At least two distinct tile shapes, to prove the function constants work
[ ] Small sizes for stage tests; mandated sizes only in Phase 5
```

The per-R-boundary check matters most: it is the only error class end-to-end
testing cannot localise, and it fails silently.

**Packaging, not an afterthought.** This runner is the shipped `--self-test`
([ADR-0006](docs/adr/0006-built-for-other-people-to-run.md)). It must be
runnable by someone who has never seen the repo, print a plain verdict, and exit
non-zero on any mismatch.

---

### Phase 4 — Mining loop, dialect seam and intensity (1.5–2 days)

**KPI:** runs for an hour unattended against both chosen pools; the machine
stays usable throughout.

`miner.py`: connect → job → generate grid → commit on host → sweep in throttled
bursts → on hit, build proof, verify at share difficulty, submit → abandon the
grid when a new job arrives.

**The dialect seam is the bulk of this phase**, and it is the real work the fork
was hiding. Both chosen pools must actually work, and both must be pools we have
run against — a dialect written from documentation and never executed does not
count ([ADR-0006](docs/adr/0006-built-for-other-people-to-run.md)).

```text
[ ] dialect.py: handshake, notify parsing, submit framing, difficulty/target
    normalisation, miner-chosen vs pool-dictated parameters
[ ] Primary pool dialect, tested against the live pool
[ ] Second pool dialect, tested against the live pool
[ ] Job shape changes trigger shader recompilation, not a wrong kernel
```

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

### Phase 5 — First accepted share, and the bar (0.5 day, + 0–2 days contingency)

**KPI:** an accepted share from our own Metal kernel.

Run at mandated dimensions against the chosen pool.

```text
[ ] Local verify at share difficulty passes before every submission
[ ] Pool returns result: true
[ ] Worker visible on the dashboard
[ ] 60 minutes unattended, no errors, machine usable
[ ] Rejected shares < 1% excluding stale jobs
[ ] Measured tiles/s recorded — the first real Apple Silicon number for this
    algorithm from a hand-written Metal kernel
```

**Then compare against the Phase 1c bar.** Clear it and stop. Miss it and
optimise Backend A — tiling, memory layout, occupancy, all inside int32
exactness, never fp32 — until it clears, then stop
([ADR-0002](docs/adr/0002-backend-a-only.md)).

---

### Phase 6 — Release (1 day)

**KPI:** someone else could run this.

```text
[x] Rename the repository to pearl-metal-miner        ← done 2026-08-04
[ ] LICENSE — Apache-2.0
[ ] NOTICE — ISC text with both upstream copyright lines; attribution to
    pearl-research-labs, arabel1a/ascend_prl, and Yose144/Zion-v3.0.0 if read
[ ] `--version` prints the ISC notice (over-compliance, deliberately)
[ ] README — what it is; "Not affiliated with Pearl Research Labs"; no dev fee
    and why; verified on M1 Max / macOS 14.4.1 only; how to run --self-test;
    build instructions; the honest economics
[ ] Build verified from scratch on a clean checkout with no venv and no Rust
[ ] Make the repository public
```

Only at this point does the repo go public. Until then the operative rule is
**everything added must be publishable**
([ADR-0005](docs/adr/0005-public-apache-2-built-from-isc-upstream.md)).

---

## 6. Schedule

```text
Phase 0     Rust, py-pearl-mining, pearl clone, wallet          2-3 hours
Phase 0.5   Settle the spec against the oracle                  0.5 day
Phase 1     Pool survey, choose, derive the bar, prove pipeline 1 day
Phase 2     Metal skeleton + function constants                 0.5-1 day
Phase 3     blake3 → noise_gen → noise_apply → pow, + self-test 3-3.5 days
Phase 4     Mining loop, dialect seam ×2, intensity             1.5-2 days
Phase 5     First accepted share, measured against the bar      0.5 day
            (optimisation contingency, only if the bar is missed) 0-2 days
Phase 6     Release                                             1 day
--------------------------------------------------------------------------
                                                              8.5-10.5 days
```

Up from 5–6. The increase is almost entirely Phase 4's dialect seam and Phase 6,
and it is the price of [ADR-0006](docs/adr/0006-built-for-other-people-to-run.md).
Phase 0.5 is new but pays for itself the first time it prevents a week of
debugging a correct-looking kernel.

---

## 7. Risks

| Risk | Severity | Mitigation |
| ---- | -------: | ---------- |
| Hash tile shape or endianness wrong | **Critical** | Phase 0.5, before any kernel. Both are silently-failing and both are actively contradicted today |
| One integer mismatch invalidates every share | Critical | Live differential per stage; per-R-boundary checks; ≥1,000 cases |
| Backend A too slow for shares to arrive | Medium ⚠️ | Bar derived in Phase 1c, measured in Phase 5, optimisation authorised only on a miss |
| Share difficulty higher than any pool we can reach | Medium ⚠️ | Phase 1 surveys three pools before any Metal work. LuckyPool's advertised minimum is 2,000,000 |
| GPU BLAKE3 diverges from reference | High | Standalone test first, before two dependent stages |
| Local verify gives false confidence | High | Always pass `nbits_override`; without it the check is theatre |
| A user's Mac produces silently wrong results | High | `--self-test` ships and is the documented first step. We verify M1 Max; their machine verifies itself |
| Second dialect written but never run | Medium | Both shipped dialects must be tested against the live pool. Non-negotiable in Phase 4 |
| Threadgroup limits differ on Apple8/9 | Medium ⚠️ | Query at runtime; refuse a tiling that will not fit rather than assuming |
| Host commitment stalls a fast GPU | Medium | Overlap with the previous grid's sweep; revisit only if measured |
| Job changes mid-proof | Medium | Job IDs, abandon grid on new job, stale-proof rejection |
| Thermal throttling / unusable laptop | Medium | Intensity dial covering GPU **and** CPU; report sustained, not peak |
| Pressure to read the barred source | Low, severe | [ADR-0005](docs/adr/0005-public-apache-2-built-from-isc-upstream.md) names the moment it will happen and the answer |
| Upstream protocol change | Low | `pearl` commit pinned in Phase 0 |

---

## 8. Open questions

1. **What shape is a hash tile, and in which endianness is the digest
   compared?** ⚠️ Phase 0.5. Blocks everything.
2. **Which pool, at what difficulty, in what units?** ⚠️ Phase 1a.
3. **How fast is Backend A really?** ⚠️ Estimated ~1 TH/s from hardware
   characteristics; measured in Phase 5 against the Phase 1c bar.
4. **Does the desktop wallet require a heavy chain sync?** ⚠️ Phase 0.
5. **Does `clamp_i8` ever fire?** ⚠️ Instrumented in Phase 3. If it fires,
   re-read the noise model before trusting any bound.
6. **Do Apple8/Apple9 GPUs share this device's threadgroup limits?** ⚠️
   Unverifiable here; handled by querying at runtime rather than answering.

---

## 9. Bottom line

Build from ISC upstream. Write our own Stratum client behind a dialect seam,
four Metal kernels, and a small miner around them. Read nothing from the barred
source, and read the other Metal implementation only after the oracle has
spoken.

Settle the tile shape and the endianness **before writing a kernel** — a
morning now, a week of mystery later.

Accumulate in **int32** — proven exact on this GPU, not merely argued. Fold the
transcript at **every** R-boundary from the **cumulative** sum. Commit on the
host. Never materialise an output matrix. Hardcode nothing a pool might dictate.
Verify at **share** difficulty before every submission.

Prove the pool pipeline with the reference miner before writing any Metal.
Everything downstream depends on that working, and none of it is your code.

Then ship it so somebody else can run it.
