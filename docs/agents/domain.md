# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

**Layout: single-context.** One `CONTEXT.md` and one `docs/adr/` at the repo root.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the glossary of domain terms.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

Both exist in this repo as of 2026-08-04: a root `CONTEXT.md` and six ADRs.

## File structure

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-metal-port-covers-the-hot-loop-only.md
│   ├── ...
│   └── 0006-built-for-other-people-to-run.md
└── csrc/, pearl_metal_miner/
```

If this repo ever splits into genuinely separate contexts, the multi-context layout is a root `CONTEXT-MAP.md` pointing at one `CONTEXT.md` per context, with context-scoped `src/<context>/docs/adr/` alongside the system-wide `docs/adr/`. Not needed today.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

This repo carries a lot of load-bearing vocabulary that is easy to drift on — *committed matrix* vs *noised operand*, *hash tile*, *pattern*, *dialect*, *R-boundary*, *cumulative Csum*, *transcript*, *pow key* vs *job key*, *Backend A* vs *Backend B*. `CONTEXT.md` is the source of truth for these terms. Precision here is not stylistic: §0.2 of `Plan.md` records a design error that came directly from conflating the committed-matrix range with the noised-operand range.

**`CONTEXT.md` holds terms, not values.** Every concrete number lives in `Plan.md`, where it carries a ✅/⚠️/❌ verification marker and a source. Do not quote a constant from the glossary — it isn't there — and do not put one back.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
