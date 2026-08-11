# First user-style run: cold start → pool-accepted share → visible on the pool

**Method:** the shipped commands only (`setup.sh`, `build_macos.sh`,
`--self-test`, `wallet`, `miner`), run 2026-08-10/11 exactly as the README
prescribes, on the reference machine (Apple M1 Max, macOS 14.4.1), driven by
an AI agent session on behalf of a non-developer user. Log lines below are
verbatim from that session's `mining.log` (worker label redacted); pool-side
data is LuckyPool's public API queried seconds after the accept. Times are
local (UTC+3).

## The run ✅ 08-11

| step | evidence |
| ---- | -------- |
| setup + build (idempotent rerun) | `setup complete`, `built build/libpearlmetal.dylib` |
| self-test, same session | `SELF-TEST PASS — 52 checks, all exact (2.3s)` |
| wallet | existing `burner_wallet.json` honoured (`wallet new` refuses to overwrite); `WALLET VERIFY PASS — 5 checks` |
| pool | LuckyPool `pearl-eu1.luckypool.io:3360`, varDiff 888,888 |
| settings | `--intensity 60 --auto-intensity`, every job-shape flag at default |

23:36:02 connect; first job about a second later:

```
[23:36:03] job b1ea5ce5_888888 height=98206: grid #1 ready in 0.65s (~2^223 bound, 524288 tiles/grid)
```

Observed rate 1.02–1.38 M tiles/s (intensity 60 with the auto-ramp; the same
machine measures ~2.3 M at 100). 2 h 03 m 56 s after the first job:

```
[01:39:59] share ACCEPTED (job 2b94f17c_888888) — {"error":null,"id":11,"result":true}
[01:40:07] 1.377M tiles/s | grids 19609 | shares 1/1 accepted (0 rejected)
```

19,609 grids × 524,288 tiles ≈ 1.03 × 10¹⁰ tiles searched, against the
~2³³ ≈ 8.6 × 10⁹ expected at the ~2²²³ bound — 1.2× the mean, an
unremarkable draw. Zero rejects and zero reconnects over the whole run.

## The pool agrees ✅ 08-11

`GET /api/stats_address?address=prl1pgzw934…qwg9dcm` on
`pearl.luckypool.io`, seconds after the accept (abridged):

```
"wallet":         "prl1pgzw934sxncsd40h7ae940l4ukc5rh6nkwvyzt6ve25a29ajycf8qwg9dcm",
"lastShare":      "1786401617777",      ← 2026-08-10T22:40:17Z = 01:40:17 local
"acceptedShares": "3",
"unlocked":       5999
```

`lastShare` lands 18 s after the miner's accept line (pool processing plus
clock skew). `acceptedShares` reads 3 because this address already carried
two accepted shares from the 08-10 dialect bring-up (see the pool survey);
this run's share is the third. The address — absent from every explorer
beforehand, as any never-paid address is — now exists in the pool's ledger
with an `unlocked` balance of 5,999 × 10⁻⁸ PRL.

## What this run is evidence of

- The README path works cold, with no manual intervention, on a machine
  meeting the stated prerequisites: every command as printed.
- The project's whole definition of done holds off the developer's own
  hands: Metal kernel → winning tile → local verify at share difficulty →
  submit → pool `result:true` → address visible on the pool.
- The economics are exactly as stated, not better: ~2 hours of an M1 Max at
  intensity 60 earned ≈ 6 × 10⁻⁵ PRL ≈ $0.000016 at the day's price.

What it is **not** evidence of: any chip other than M1 Max (every other
machine proves itself with `--self-test` — that is the design, ADR-0006),
or any pool endpoint other than LuckyPool `:3360`.
