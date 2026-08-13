# Changelog

Notable changes, per release. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.4] — 2026-08-13

Three loose ends left by the v0.2.3 pass, plus what looking at the first one
properly turned up. No behaviour change to the kernels or the wire protocol;
`--self-test` is unchanged and still passes with 53 exact checks.

### Fixed

- **Numeric flags had no bounds, and several misbehaved badly without them.**
  `--intensity` was documented as 1–100 and enforced nowhere: `--intensity 0`
  didn't error, it made the miner ~100× slower, which reads as "broken"
  rather than "you typed a bad number". Checking its neighbours found worse —
  `--region-rows 0` raised `ZeroDivisionError` on the general kernel, a
  negative `--max-job-age` made the watchdog fire every pass and reconnect
  forever, and a negative `--time-limit`/`--max-accepted` exited before
  mining anything. All eight numeric flags now carry the range they mean and
  refuse anything outside it by name. The same values in `config.toml` take
  the opposite path deliberately — warn and fall back to the default, per
  that module's rule that a typo in a file never stops a machine that was
  mining fine.
- `Buf.array` guarded the only thing standing between a miscomputed view and
  a read past the end of a GPU buffer with an `assert`, which `python -O`
  strips. It is now a real check, plus a use-after-release guard.

### Changed

- `--self-test`'s blocked-kernel stage runs at k=1024, rank=128 — deliberately
  below consensus's `k ≥ 16·rank`, so `validate_shape` would refuse it as a
  *mining* shape. That is legitimate (the stage compares GPU against the NumPy
  reference on identical inputs, where dimensions don't matter, and a small k
  keeps the exhaustive per-tile comparison quick) but nothing said so. Now the
  docstring does.
- `tools/check_job_sanity.py` grew the numeric-flag cases and the config
  warn-and-fall-back case: 11 bad shapes, 12 bad numbers, out-of-range config,
  and the malformed-job pool.

## [0.2.3] — 2026-08-13

A QA pass over the whole repo focused on one theme: **a bad job must be
refused, never a traceback.** Both sources of a bad job — the command line
and the pool — could end in an uncaught Python exception on a user's screen,
and one of them could instead mine forever without ever being able to win.
No behaviour change to the kernels or the wire protocol; `--self-test` is
unchanged and still passes with 53 exact checks.

### Added

- `reference.validate_shape` — a restatement of upstream's own
  `zk-pow/src/api/sanity_checks.rs::public_params_sanity_check`, covering the
  shape a user can set from the command line, run once at startup for both
  mining and `--benchmark`. Each rule carries the flag it constrains, so a
  refusal reads as instructions rather than as a stack trace.
- `tools/check_job_sanity.py` — 11 bad shapes must exit 2 with the rule
  named and no traceback, the shipped default must still pass, and a fake
  pool sending a zero target and two wrong-length headers must be survived
  with the miner going on to mine the next good job. CI picks it up
  automatically (it globs `tools/check_*.py`).

### Fixed

- **A `--rank` that is not a power of two mined forever and could never
  win.** Noise generation draws its permutation indices with `u & (rank-1)`,
  a mask that only works for powers of two, and consensus separately
  requires `32 ≤ rank ≤ 1024` and `16·rank ≤ k ≤ 4·rank²`. `--rank 100`
  passed every existing check, connected, swept the GPU at full speed, and
  produced tiles upstream's verifier would reject forever — with nothing on
  screen to say so. This is exactly the silent-failure class the project
  exists to refuse, reachable from one mistyped flag; it is now refused
  before the Metal context is even created.
- **Out-of-range shape flags printed a raw traceback.** `--m 100` raised an
  `AssertionError` from deep in `Pattern.valid_offsets`, `--rows 5,0` one
  from `Pattern.from_list`, and `--k 0` surfaced as `MetalError:
  pm_alloc(0) failed`. All now exit 2 through `argparse` like any other bad
  flag. The two asserts became `ValueError`s while passing: they validate
  user input, and `python -O` would have stripped them.
- **A pool sending `target: "0"` crashed the miner** with
  `ZeroDivisionError` the moment the job was adopted (the expected-tiles
  figure divides by the bound), and a negative target raised `OverflowError`
  — both one line away from the existing guard for the *opposite* extreme,
  `bound overflows 2^256`.
- **A pool sending a wrong-length header crashed the miner hours later.**
  A 40- or 96-byte header sailed past parsing, committed grids to a job that
  could never verify, and raised `ValueError: Expected 76 bytes` only once a
  tile finally won — the worst possible moment, and after an unbounded
  stretch of wasted mining. Both checks now live in `Job.__post_init__`, so
  the reader thread logs and drops the line, the miner waits for a usable
  job, and every future dialect inherits the guard by constructing a `Job`.

## [0.2.2] — 2026-08-12

Two QA passes over the whole repo, with the v0.2 additions in focus. The two
user-visible defects are the same kind — a number shown to the user that no
longer matched what the machine was doing: a paused miner billing itself for
power, and `--benchmark` publishing a throttled speed unmarked. No behaviour
change to the kernels or the wire protocol; `--self-test` is unchanged and
still passes.

### Added

- `--benchmark` records whether it measured on AC or battery, in its log
  line and in the paste-ready block, and says so when it is on battery. The
  benchmark deliberately ignores `--on-battery` and sweeps at full
  intensity, so an unplugged laptop was publishing its throttled number with
  nothing to mark it — and the README's own table puts that gap at ~15%
  (2.31M vs 1.95M on the reference M1 Max), larger than the differences
  between chips the table exists to show. Not hypothetical: the seed row in
  the benchmark reports issue is a battery run, and had to carry a
  hand-written "this run was on battery" note the block could not supply.
  The issue template's sample row matches the new format.
- `--self-test` now checks our job-config serialisation against upstream's
  own `MiningConfiguration.to_bytes()` (53 checks, was 52). The job key is
  `BLAKE3(header ‖ config)`, so those 52 bytes are a consensus input: a wrong
  one commits every grid to the wrong key and the pool refuses every share
  with no diagnostic. It was previously only implied by the end-to-end
  verify, which cannot say *which* input was wrong.

### Changed

- `PROMPT_FOR_AI_DEV.md` described the v0.1 flow: it never mentioned `init`
  and `config.toml`, `--benchmark`, `--keep-awake`, the live dashboard, or
  that the miner pauses on battery by default. An agent following it
  produced a working but v0.1-shaped setup.
- Shipped code comments no longer refer to the internal wave map by its
  labels (`B4 money line`, `A4`, `C3`, `Phase 0.5, E3`, "grill decision",
  "house rule"). They said the same things in vocabulary only this project's
  own planning documents defined, and those documents are not public. The
  `tools/check_*.py` docstrings keep their labels — each pairs with a public
  issue number.
- `--help` said the self-test runs "52 exact checks". It runs 51 on a fresh
  clone: the wallet-file check only exists once there is a wallet file. Now
  "~50", which is true before and after.

### Fixed

- A miner paused on battery still billed itself for electricity. The money
  line prices power from the live intensity, and the pause path returned to
  the top of the loop without touching it, so the panel kept the pre-pause
  value and charged the full chip wattage — `est. −$0.19/day` for a GPU
  dispatching nothing. Pausing now sets intensity 0, and `gpu_watts_est`
  treats duty cycle 0 as 0 W rather than clamping up to 1. A pause is the
  one moment this miner costs nothing, and it was the moment it claimed to
  cost most. `tools/check_battery.py` gained a case that fails if the paused
  money line ever charges again.
- Reconnect backoff computed `2 ** (attempt - 1)` with no cap on the
  exponent. Attempts are unbounded, so a long outage grew a multi-thousand-
  bit integer to produce a number that has been 60 s since attempt 5. Same
  sequence (5, 10, 20, 40, 60…), bounded arithmetic.
- `pm_destroy` never ended the `NSProcessInfo` activity token that
  suppresses App Nap, and the one failure path in `pm_create` leaked it
  outright. Harmless for the miner (the token dies with the process) but
  wrong for any caller that creates and destroys a context and keeps going.
- Dead locals in `dashboard.py`, `selftest.py` and `tools/check_battery.py`,
  and a stray `%%` in a `pearl_metal.mm` comment.

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
