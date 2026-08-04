# This is built for other people to run

Until 2026-08-04 this was a personal artifact. [[0003-private-repo-and-no-dev-fee]]
said so explicitly: *"It earns nothing and now benefits nobody else either. It is
being built because its owner wants it built."* Going public under
[[0005-public-apache-2-built-from-isc-upstream]] made "benefits somebody else"
possible for the first time, and we are choosing to intend it rather than let it
happen by accident.

**Definition of done becomes a usable release**, not a lone accepted share: an
accepted share from our own Metal kernel, plus `LICENSE`, `NOTICE`, a truthful
`README`, a build script that works on a machine that is not this one, and at
least one documented pool other than the one used to get the share.

This is the expensive answer, and it was taken with the price in view.

## What it buys in

**A self-test that ships.** The oracle harness — a live differential comparing
every Metal stage against `miner_base`'s Python — becomes a user-facing command
rather than a developer's pytest suite. This is the single highest-leverage
thing the decision adds. We can verify M1 Max and nothing else, but this
project's failure mode is silent: a subtly wrong kernel does not crash, it burns
a stranger's electricity producing shares the pool rejects. A shipped self-test
turns "unverified on your hardware" from a disclaimer into a proof the user runs
themselves, on their own machine, against the reference implementation, before
mining anything. The `README` claims verification on M1 Max only, and points
every other machine at the command.

**A real dialect seam.** `ascend_prl` documents that Pearl pools do not share
one Stratum dialect — some dictate `m, n, k, rank` and the row/column patterns
to the miner via `pearl.set_mining_params`, others let the miner choose. A
client hardcoded to one pool's shape does not port. Two pools must actually
work, and both must be pools we have tested. Shipping a wire-protocol
implementation we have never run would contradict the reasoning behind the
self-test.

**Nothing hardcoded that a pool might dictate.** Tile height and width, rank and
the row/column patterns come from the job. Because
[[0004-no-xcode-runtime-shader-compilation]] already compiles MSL at process
start, these can be Metal *function constants*: the compiler folds them into the
generated code exactly as if they had been literals, so portability costs no
speed in the hottest loop in the project. That decision was taken to avoid a
10 GB Xcode install and turns out to pay a second dividend.

**Speed becomes a gate.** See the amendment in [[0002-backend-a-only]].

## What it costs

The schedule roughly doubles, from 5–6 days to about 8.5–10.5. Most of the
increase is the dialect seam and the second pool. `Plan.md` §6 carries the
breakdown.

We are also not competing on the axis it first appears. `open-jarvis/OpenJarvis`
(Apache-2.0, 8,288 stars) has publicly declared a native Metal kernel as future
work — but it mines **solo against your own node** and states *"No multi-host
pool. Solo mining only."* Solo mining a laptop against a 28.54 EH/s network has
an expected time to a block of effectively never. The differentiator here is
therefore **pool mining on Apple Silicon**, not a hand-written kernel — the
configuration in which a Mac produces a result you can actually see, and the
half OpenJarvis has explicitly declined to build.

## Consequences

The project is standalone and pool-first. Contributing the kernel to Pearl or to
OpenJarvis stays an option to exercise after it works, mentioned in the `README`
as welcome; it is not a commitment made before it works, because code written to
be contributed has to match someone else's conventions and review from the first
line.

A support promise is hard to withdraw. This ADR records what was promised —
a working build, an honest verification claim, two tested pools — so that
anything beyond it can be declined by pointing here rather than by argument.
