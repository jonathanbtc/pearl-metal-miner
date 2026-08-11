# Changelog

Notable changes, per release. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
- Shipped `--self-test`: 52 exact-integer differential checks against the
  pinned upstream, end-to-end through upstream's own Rust verifier.
- Stratum client behind a dialect seam; LuckyPool and Kryptex dialects
  reverse-engineered from live wire traffic.
- First pool-accepted shares (LuckyPool, 2026-08-10/11), including a
  cold-start user-style run documented in `docs/research/`.
- Local payout wallet: create/show/verify a real taproot keypair (ADR-0008).
- Intensity dial covering GPU duty cycle and CPU threads; auto-intensity
  idle ramp.
- Three-package install (numpy, blake3, maturin) with clean-machine setup
  scripts.
