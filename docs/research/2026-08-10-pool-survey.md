# Pool survey — live wire evidence (Phase 1a/1b)

**Method:** `tools/pool_survey.py` — connect, handshake, log both directions
verbatim, submit nothing. Every claim below is from bytes on the wire on the
dates given, reverse-engineered where undocumented — never from any barred
source (ADR-0005).

## Kryptex — `prl-eu.kryptex.network:7048` ✅ 08-09

- `mining.subscribe` params `[agent]`; `mining.authorize` params
  `["<addr>.<worker>", "x"]` → `{"id":3,"result":true}`. Jobs flow
  immediately.
- `mining.notify` params **object**: `header` = 152 hex chars — **exactly the
  76-byte `IncompleteBlockHeader` wire form**; `height`; `job_id`
  `"<hex8>_2097152"`; `target` big-endian hex (observed
  `0x…07ff…` ≈ 2²¹¹, constant across notifies — fixed difficulty 2,097,152 in
  the diff1 = `0xFFFF·2²⁰⁸` convention); `cert_version: 2`.
- Miner-chosen m, n, k, rank, patterns (they travel in the PlainProof).
  Independent corroboration: `ascend_prl`'s kryptex frontend (MIT) uses
  rank=128, k=4096, rows `[0,32]`, cols `[0..63]`, m=n=131072, and its
  adjusted target is `pool_target × h·w × rounded_k` — the same bound formula
  Phase 0.5 proved at consensus.
- Submit: `mining.submit` params object
  `{worker: "<addr>.<worker>", job_id, plain_proof: <base64>}`, where the
  payload is upstream's `PlainProof.to_base64()` (bincode+base64). An optional
  v2 session (object authorize with `type:"v2"`) gzips the proof; we speak v1.

## LuckyPool — `pearl-eu1.luckypool.io:3360` ✅ 08-10 (reverse-engineered)

- **No `mining.subscribe`** ("method not supported"); array-params authorize
  rejected with "params must be an object".
- `mining.authorize` params **object** `{wallet, worker, agent}` →
  `{"error":null,"id":2,"result":true,"type":"plain"}`.
- `mining.notify` params object: `diff` (varDiff — observed **888888** on a
  fresh worker, below the advertised 2,000,000 floor), `header` (76-byte hex),
  `height`, `job_id` `"<hex8>_<diff>"`, `target` big-endian hex consistent
  with diff1/diff.
- Submit: object `{wallet, worker, job_id, plain_proof}` — same family as
  kryptex/k1pool. Confirmed live by an accepted share (see Plan.md Phase 5).
- The undocumented `pearl-cpu-eu1.luckypool.io:3370` **accepts TCP** — the
  endpoint exists; dialect unprobed.

## K1Pool — `eu.pearl.k1pool.com:5566` ⚠️ 08-09

- `mining.subscribe` works (proper stratum reply with
  `mining.set_difficulty`/`mining.notify` subscriptions).
- Object authorize `{wallet, worker, agent}` → error code 24:
  `Post "http://127.0.0.1:44111": connection refused` — **their auth backend
  was down** at survey time. Not a dialect failure; retry later. Deprioritized.

## LuckyPool CPU port — `pearl-cpu-eu1.luckypool.io:3370` ✅ 08-10

The undocumented port is real and lower-difficulty. Same object dialect as
3360. Advertised **diff 26,000** (vs 888,888 on 3360) → bound ≈ 2²²⁸ →
P(tile) ≈ 2⁻²⁷ ≈ 34× easier. This is the port that makes an M1 Max share
tractable in minutes rather than an hour, and the one used to prove the
submit pipeline.

## Submit pipeline, proven end-to-end ✅ 08-10

Three things were confirmed against the live pool, not reasoned about:

- **Submit framing.** Four param shapes tested with a throwaway proof; all
  four parsed (the error was about proof content, code 20, not framing). We
  use `{wallet, worker, job_id, plain_proof}`.
- **Proof encoding.** A *real* mined proof for the pool's own header came back
  **code 21 "job not found / stale"**, not code 20 "not a valid PlainProof".
  So `PlainProof.to_base64()` = `base64(bincode(...))` **decodes on the pool**
  — the format matches (independently, `ascend_prl`'s `proof-ffi` also emits
  `base64(bincode(PlainProof))`). The pool tries gzip, zstd and plain; we send
  plain.
- **Staleness is the real constraint.** Code 21 was pure timing: a 512²
  diagnostic took 180 s and the job (block target ~120 s) expired. The real
  8192² miner at ~2.3M tiles/s finds a share in ~60 s, inside the window.

**Operational gotcha — App Nap.** An unattended background miner is suspended
by macOS App Nap after ~30 s (grids advanced 11→115 in the first 30 s, then
179→233 over the next 28 min). `caffeinate -disu` does **not** stop it. The
fix ships in the backend: `pm_create` holds an
`NSActivityUserInitiated|LatencyCritical` assertion. Without it, no long run
completes and the idle socket gets closed by the pool.

## Choices (1b) and the bar (1c)

- **Primary: LuckyPool** (object dialect, varDiff, CPU port for a tractable
  share). **Second: Kryptex** (clean fixed-difficulty dialect, exercised).
  Both live-tested, satisfying ADR-0006. K1Pool is the spare.
- **The bar, corrected.** Bound = target × h·w·(k−k%r), and the digest is a
  256-bit value, so P(tile) = bound / 2²⁵⁶. Measured live: LuckyPool 3360
  bound ≈ 2²²³ → **~2³³ ≈ 8.6e9 tiles/share** (~63 min at 2.3M/s); CPU port
  3370 bound ≈ 2²²⁸ → **~2²⁷ ≈ 1.3e8 tiles/share** (~60 s). (The earlier
  "~67M tiles/share" figure understated it — a factor slip; the live bound is
  the authority.) Kernel progress against this: **0.12M (v1) → 2.31M tiles/s
  (v2, fp32-FMA blocked)**, the ADR-0002 optimisation authorised once shares
  needed to arrive in ~1 min. The mandated GPU-difficulty (3360/kryptex) case
  is genuinely ~1 hour/share on this hardware — the honest cost that the
  economics in ADR-0002 predict, and why the CPU port is the demonstration
  vehicle.
