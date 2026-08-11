# Security policy

## Reporting

Please report vulnerabilities privately via GitHub's private vulnerability
reporting:
**<https://github.com/jonathanbtc/pearl-metal-miner/security/advisories/new>**

No email address is published for this; the GitHub flow is the channel.
Response is best-effort by a small maintainer team; there is no bounty
program. Please include reproduction steps and your environment (chip,
macOS version, `--version` output).

## What this tool is, security-wise

- **`wallet.json` holds a real private key.** It is generated locally with
  the OS's cryptographic randomness, written with file mode `0600`,
  gitignored, and **never transmitted anywhere** — the pool only ever sees
  the public address. The file is the only claim on mined funds; anything
  that could exfiltrate, weaken, or silently corrupt it is in scope and
  serious.
- **The miner's only network contact is the pool** you point it at (TCP,
  line-framed JSON). No telemetry, no price feeds, no update checks. A
  change that makes it contact anything else is a bug even when
  well-intentioned.
- **It never asks for admin rights.** No sudo, no privileged helpers; the
  only subprocesses it starts are Apple's own unprivileged tools
  (`caffeinate`, `pmset`, `osascript`, `ioreg`).
- Shares are verified locally before submission; consensus-relevant code is
  differentially tested against the pinned upstream by `--self-test`.

Findings that contradict any statement above are exactly what we want to
hear about.
