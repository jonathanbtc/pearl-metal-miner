# The included wallet is a bare keypair, validated like a kernel

Decided 2026-08-10, when wallet creation was promoted from a testing-only
tool into a first-class command (`python -m pearl_metal_miner.wallet new`).
The request that prompted it: a person cloning this repo should have
everything needed to mine, an address included — without first finding,
vetting and installing a separate wallet application.

## The decision

The repo ships wallet **creation**, not a wallet **application**. What
`wallet new` writes is a single file holding a keypair and its payout
address; there is no balance display, no transaction building, no sending.
Spending means importing the private key into any taproot-capable wallet,
and both the file's `note` field and `show --reveal-private-key` say so.

Three reasons to stop there:

**Custody honesty scales with surface.** A bare file is a custody story a
non-expert can actually hold in their head — *the file is the money; back it
up; whoever reads it owns it* — and the README says exactly that, three
bullets, no fine print. A wallet app implies balances, sync, and recovery
flows we would then own. [ADR-0006](0006-built-for-other-people-to-run.md)
promised a working miner, not custody software; this ADR records the line so
future feature requests can be declined by pointing here.

**The failure mode is the domain's worst, so it gets the domain's medicine.**
A mistyped payout address, or a mis-tweaked key, does not crash — it mines
value nobody can ever claim. That is the same silent-failure shape as a
wrong kernel integer, and it gets the same treatment: the format authority
is upstream's ISC gateway decoder (`get_script_pubkey_from_p2tr_address`:
witness v1, 32-byte program, bech32m); the key→address math is
differentially tested against `bitcoinutils` 0.8.2 — the very library that
gateway pays addresses with — via `tools/wallet_differential.py`, with four
vectors baked into `--self-test` stage 0; the miner validates **every**
payout address before its first byte reaches a pool; and `wallet verify`
re-derives an existing file from the private key up. Live evidence: a
LuckyPool-accepted share on 2026-08-10 paying an address this code
generated.

**Licences stay clean.** Upstream's `wallet/` sub-project is one of the
monorepo's licence exceptions and is neither read nor needed: address
handling is restated from the BIPs and mirrored against the gateway (an ISC
path), `bitcoinutils` (MIT) is a dev-only dependency of the differential
tool, and nothing touches the barred repositories
([ADR-0005](0005-public-apache-2-built-from-isc-upstream.md)).

## Consequences

- The default payee when `--address` is omitted is the local wallet file —
  found by its canonical name `wallet.json`, or the pre-08-10 name
  `burner_wallet.json`, which keeps working forever because a name change
  must never orphan a file that may already own mined funds. For the same
  reason `wallet new` refuses to overwrite, and refuses to shadow an
  existing legacy file with a fresh canonical one.
- An invalid `--address` is a startup error, not a warning. A pool might
  accept what the chain cannot pay; we refuse first.
- The README recommends an established wallet's address for anything the
  user would mind losing. The included wallet is the zero-dependency path,
  not a custody recommendation.
