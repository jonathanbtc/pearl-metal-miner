# This repo stays private, and the developer fee is removed

Upstream `Muskwak/Open-Pearl-Miner` ships under a custom licence (not MIT,
despite resembling it) whose clause 2 mandates a 2% developer fee and forbids
removing it in anything distributed. Clauses 3 and 4 carve out an exemption:
you may disable the fee for strictly personal, non-commercial use, on your own
hardware, mining to your own wallet, provided the modified software is never
distributed, published, sold, sublicensed, or deployed in any third-party
context.

We are taking that exemption. `DEV_FEE` goes to zero and the dev-fee wallet
switching is bypassed.

## The constraint this creates

**`jonathanbtc/perle-minig` must stay private.** It is private today, which is
what makes this lawful. A private remote is not distribution; making the repo
public — or handing anyone a build — would be, and at that moment a fee-free
build becomes a licence violation.

So: if this is ever published, the developer fee must be restored to its
original form and rate *first*. Restoring it is a two-line change; noticing that
it is required is the hard part, which is why it is written down here.

Note also that this decision withdraws the project's only external
justification. It earns nothing (see
[[0002-backend-a-only]]) and now benefits nobody else either. It is being built
because its owner wants it built, which is reason enough — but it should not be
mistaken for anything more.
