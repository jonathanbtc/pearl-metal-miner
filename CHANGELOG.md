# Changelog

Notable changes, per release. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.1] — 2026-08-11

Post-v0.2.0 QA pass over the whole repo. No behaviour change to the kernels
or the wire protocol; `--self-test` is unchanged and still passes.

### Fixed

- Ctrl-C is now a designed exit for **every** command, not just the mining
  loop: `init`, `--self-test` and `--benchmark` printed a raw traceback when
  interrupted. Each now prints one line and exits non-zero — an interrupted
  self-test must never be mistaken for a pass.
- A failed startup (DNS failure, timeout, refused) no longer prints a
  `session: 0 tiles … 0 shares` summary after its own error, which read like
  a run that finished rather than one that never began.
- README's flag table said the default pool was `kryptex`; it has been
  `luckypool` since #26.
- `economics.py` and the generated `config.toml` cited `Plan.md`, an internal
  working file that is not part of the public repo. The figures now cite
  their source (hashrate.no, dated) directly.
- `MTLCompileOptions.fastMathEnabled` is deprecated in the macOS 15 SDK and
  warned on every build there. Now uses `mathMode = MTLMathModeSafe` on 15+,
  the same semantics, with the old spelling kept for macOS 14.
- `PoolConnection.send` raised `AttributeError` instead of failing the
  connection if the socket was closed underneath it.
- The offline check suite could not run on a fresh clone at all: nine of the
  checks read a payout address out of `burner_wallet.json`, which is
  gitignored and so exists only on the machine they were written on. They
  now use one published, burned test address.
- `tools/check_config.py` created a real `wallet.json` — a real private key —
  in the project folder as a side effect and left it there. It now removes a
  wallet it caused to appear, and never one that existed beforehand.

### Changed

- CI also runs the offline `tools/check_*.py` suite, not only the GPU
  self-test — CONTRIBUTING points contributors at those checks, so CI is
  what should keep them honest.
- `tools/check_benchmark.py` no longer gates on two benchmark runs agreeing
  within 15%. That asserted a property of the host (thermals, load, AC vs
  battery), not of this code, and failed on busy machines. It now asserts
  what the code owes: the published number is the measured one, over the
  window that was requested. The two rates are still printed.

## [0.2.0] — 2026-08-11

The v0.2 wave (#19): dashboard, honest economics, benchmark, front door.
Goal: impress a stranger in five minutes, and answer "is it worth it on MY
Mac?" honestly, per machine.

### Running it feels finished (batch A)

- Stopping is a designed exit: Ctrl-C/SIGTERM close the pool socket
  politely, print a session summary on every exit path, exit 0 (#20).
- Rolling 60 s hashrate + a richer heartbeat: accept %, uptime (#21).
- Stale-job watchdog (`--max-job-age`) and reconnect backoff 5→60 s with
  numbered attempts, downtime, and distinct DNS/timeout errors (#22).
- macOS notifications for accepted shares, on by default; `--no-notify` (#23).
- `--keep-awake`: a caffeinate child tied to the miner's lifetime (#24).
- A real `--help`: description, examples, wallet pointer, `PRL_RAW=1`
  documented (#25).
- Default pool is LuckyPool — the pool with pool-confirmed accepted
  shares; each pool's verification depth stated exactly (#26).

### Dashboard + config (batch B)

- `config.toml` in the project folder + `init` wizard; precedence is
  always flag > file > default (#27).
- Live terminal dashboard — hand-rolled ANSI, zero new dependencies;
  plain logs whenever piped or redirected (#28).
- On battery: pause by default, auto-resume on AC; `on_battery =
  pause|low|full`; desktops unaffected (#29).
- The money line: offline per-machine economics derived from your own
  stated assumptions, every figure labeled `est.` (#30).

### Proof (batch C)

- `--benchmark`: offline speed test + personal economics verdict + a
  paste-ready result block (#31).
- Demo GIF of a real pool-accepted share, honestly captioned (#32).
- Community hardware table, rows only from linked evidence, plus the
  pinned reports issue (#33).

### Front door (batch D)

- CI on GitHub's Apple Silicon runners — the full bit-exact GPU self-test
  passes on the hosted runner, and the badges say exactly that (#34).
- CONTRIBUTING (the add-a-pool recipe and the wire-logs-only sourcing
  rule), SECURITY (private vulnerability reporting), patent disclosure,
  canonical triage labels (#35).
- Seeded community invitations (K1Pool dialect, Kryptex verification,
  kernel-upstream offer, benchmark reports) and this release (#36).

## [0.1.0] — 2026-08-11

Everything through the pre-wave state: the first working miner.

- Bit-exact Metal port of the Pearl proof-of-work hot loop — keyed BLAKE3,
  noise generation, noise application, fused GEMM → transcript → PoW sweep
  (general + blocked fast path) — compiled at process start, no Xcode.
- Shipped `--self-test`: 51 exact-integer differential checks against the
  pinned upstream (52 once a local wallet file exists), end-to-end through
  upstream's own Rust verifier.
- Stratum client behind a dialect seam; LuckyPool and Kryptex dialects
  reverse-engineered from live wire traffic.
- First pool-accepted shares (LuckyPool, 2026-08-10/11), including a
  cold-start user-style run documented in `docs/research/`.
- Local payout wallet: create/show/verify a real taproot keypair (ADR-0008).
- Intensity dial covering GPU duty cycle and CPU threads; auto-intensity
  idle ramp.
- Three-package install (numpy, blake3, maturin) with clean-machine setup
  scripts.
