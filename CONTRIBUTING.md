# Contributing

Thanks for looking under the hood. This project is small on purpose; the
bar for landing changes is correctness you can prove, not volume.

## Dev setup

The README's [Setup from A to Z](README.md#setup-from-a-to-z) *is* the dev
setup — there is no second, secret path: `packaging/setup.sh`,
`packaging/build_macos.sh`, then

```sh
.venv/bin/python -m pearl_metal_miner.miner --self-test
```

## The merge gate

**`--self-test` green is the gate for any kernel or dialect change.** Failure
in this domain is silent — a wrong integer doesn't crash, it produces shares
the pool refuses with no diagnostic — so the self-test is differential and
exact: every check is an integer comparison against upstream's reference,
and one mismatch fails the run. The offline checks under `tools/check_*.py`
cover the runner behavior (shutdown, reconnect, dashboard, config, battery,
economics, benchmark, job sanity); run the ones your change touches.

## The star attraction: add a pool dialect (~50 lines)

Pearl pools do not share one Stratum wire format, so everything
pool-specific lives behind one seam. A new pool is one small subclass:

1. Subclass `Dialect` in `pearl_metal_miner/stratum/dialect.py` — four
   framing points: `handshake_lines`, `parse`, `submit_line`, and the
   `miner_chooses_params` flag.
2. Model it on `stratum/luckypool.py` (~55 lines, the whole file).
3. Develop against real wire logs:
   `PRL_RAW=1 python -m pearl_metal_miner.miner --pool … --host … --port …`
   logs every raw line both directions. Capture a session, implement,
   compare bytes.
4. Register it in `DIALECTS` in `miner.py`, and say in the docstring what
   was verified live (jobs received? share accepted?) — the repo states
   verification depth exactly, per pool.

**The one hard rule (ADR-0005):** dialects here are reverse-engineered from
logged wire traffic, never from reading other miners' code with
incompatible licences. Specifically, `Muskwak/Open-Pearl-Miner` and
`minerjed/open-pearl-miner` are **barred sources** — do not read them, do
not port from them, do not cite them as evidence. Wire logs from your own
sessions are always fair game.

## Ground rules

- Zero new runtime dependencies. The three-package install is a trust
  property of a tool that generates private keys. (Stdlib-only is asserted
  by `tools/check_dashboard.py`.)
- Every number shown to a user is either measured or labeled as an
  estimate/assumption. No invented figures.
- Contributions land under **Apache-2.0** (the repo licence). **No CLA** —
  the standard Apache-2.0 inbound=outbound understanding applies.
- Benchmarks for the hardware table go to the
  [pinned reports issue](https://github.com/jonathanbtc/pearl-metal-miner/issues/37),
  not PRs.

## Security issues

Not here — see [SECURITY.md](SECURITY.md).
