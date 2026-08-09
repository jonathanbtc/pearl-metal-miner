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

## Choices (1b) and the bar (1c)

- **Primary: LuckyPool** (easier varDiff start, largest Pearl pool).
  **Second: Kryptex** (clean fixed-difficulty dialect, already exercised).
  Both are live-tested dialects, satisfying ADR-0006. K1Pool is the spare.
- **The bar:** at Kryptex's fixed target (diff 2,097,152, factor
  h·w·k = 2¹⁹ with the 2×64 k=4096 shape), P(tile) ≈ 2⁻²⁶ → **~67M tiles per
  share**. For a share every ≤10 minutes: **≥ 112K tiles/s**. For a share
  every minute: ≥ 1.1M tiles/s. LuckyPool's varDiff (observed start 888888 ≈
  2.36× easier) lowers the entry bar to ~28M tiles/share and adapts further.
  The v1 correctness-first kernel measured **0.12M tiles/s** — above the
  10-minute bar, an order of magnitude short of comfortable. Optimisation is
  authorised by ADR-0002 the moment we decide shares should arrive in ~1
  minute; the target is **≥1M tiles/s**, with the known move being a
  GEMM-blocked kernel with cross-tile operand reuse (the v1 kernel re-reads
  Bᵀ per tile with no reuse and is bandwidth-bound at ~35 GB/s effective).
