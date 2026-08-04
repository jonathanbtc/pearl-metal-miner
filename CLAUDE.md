# pearl-metal-miner

A bit-exact Apple Metal compute backend for the Pearl (PRL) proof-of-useful-work
miner, built from the ISC-licensed `pearl-research-labs/pearl` upstream, for
pool mining on Apple Silicon. See `Plan.md` for the build plan, `CONTEXT.md` for
the glossary, and `docs/adr/` for the decisions and their reasoning.

## Two rules that override convenience

**1. Everything added must be publishable.** This repo is private today and goes
public under Apache-2.0 at the release (Phase 6). Nothing may be added — code,
dependency, vendored file, snippet — whose licence would block that. When in
doubt, check the licence before adding, not before releasing.
See `docs/adr/0005-public-apache-2-built-from-isc-upstream.md`.

**2. `Muskwak/Open-Pearl-Miner` and `minerjed/open-pearl-miner` are barred.**
Never clone them, never read them, never cite them as evidence. Their custom
licence mandates a 2% fee on "the Software or derivative thereof" and does not
define "derivative". This bar has one predictable pressure point — they are the
only description of LuckyPool's Stratum dialect — and the answer there is to
reverse-engineer from logged wire traffic. Same ADR.

## Things that are easy to get wrong here

- **The oracle defines correctness.** `miner_base` in the `pearl` monorepo. Other
  implementations (`Zion`, `ascend_prl`, `OpenJarvis`) are cross-checks, never
  sources of truth, and `Plan.md` §4.5 sets the order in which they may be read.
- **Failure in this domain is silent.** A wrong integer does not crash; it
  produces shares the pool refuses with no diagnostic. Hence: no tolerances
  anywhere, differential tests per stage, and `--self-test` as a shipped command.
- **`Plan.md` carries ✅/⚠️/❌ markers on every external claim.** Do not restate a
  ⚠️ as settled fact, and do not move a claim to ✅ without naming the source and
  the date.
- **`CONTEXT.md` holds terms, not values.** Concrete numbers live in `Plan.md`
  where they carry a marker. Do not put constants back in the glossary.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `jonathanbtc/pearl-metal-miner`, via the `gh` CLI.
See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name.
See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root.
See `docs/agents/domain.md`.
