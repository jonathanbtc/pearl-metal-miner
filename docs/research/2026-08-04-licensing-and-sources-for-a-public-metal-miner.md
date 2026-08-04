# Licensing and sources for a public, fee-free Metal miner

**Checked on: 2026-08-04.** Every claim below carries the date it was verified;
all of them were verified on this date unless stated otherwise.

**Where this file lives and why.** `docs/adr/` holds decisions and `docs/agents/`
holds skill config; neither is the right home for an evidence dump that no
decision has yet been taken on. This is the first entry in a new `docs/research/`
directory: dated, source-anchored investigation that ADRs can cite. It is
evidence, not a decision. The decision it feeds would supersede
[ADR-0003](../adr/0003-private-repo-and-no-dev-fee.md) and materially change
[ADR-0001](../adr/0001-metal-port-covers-the-hot-loop-only.md).

**Method.** Primary sources only. Licence and manifest text was fetched as raw
bytes over `curl` from `raw.githubusercontent.com` and the GitHub REST API, not
from rendered pages, so the quotes below are the files themselves. Where a fact
comes from a classifier rather than the file, that is said explicitly.

---

## Summary of what changed

Four premises the current plan rests on turned out to be wrong or incomplete.

| Plan premise | Status after this research |
| --- | --- |
| The Metal port must be built on `Muskwak/Open-Pearl-Miner`, whose licence forces either a 2% fee or a private repo | **Unnecessary.** The Pearl monorepo — including the oracle and `py-pearl-mining` — is **ISC**, one of the most permissive licences in existence. Muskwak is not on the critical path at all. |
| No Apple Silicon Pearl miner is public | **False.** `open-jarvis/OpenJarvis` (Apache-2.0, 8,288 stars) ships a working Apple Silicon Pearl mining path today. |
| No Metal implementation of this PoW is public | **False.** `Yose144/Zion-v3.0.0` (MIT) contains a 23.8 KB MSL kernel implementing the full pipeline, `HASH_ROT = 13` and all. Correctness unverified. |
| Muskwak's Stratum client is effectively the only description of the pool dialect | **False.** `arabel1a/ascend_prl` (MIT) contains an independent, documented Stratum layer for two Pearl pools. |

---

## Q1 — Licence of `pearl-research-labs/pearl`

### Q1.1 The repository exists and is public

Checked 2026-08-04, `https://api.github.com/repos/pearl-research-labs/pearl`:

```json
{
  "full_name": "pearl-research-labs/pearl",
  "description": "Monorepo for the Pearl network 🐚",
  "license": { "key": "other", "name": "Other", "spdx_id": "NOASSERTION", "url": null },
  "default_branch": "master",
  "private": false,
  "fork": false,
  "created_at": "2026-04-19T10:31:45Z",
  "pushed_at": "2026-08-03T19:28:11Z",
  "stargazers_count": 283
}
```

**Note the trap here.** GitHub's classifier reports `NOASSERTION` / "Other". That
is *not* evidence that the licence is unusual. It is an artefact of a
monorepo-index block appended below the licence body (shown in full in Q1.2),
which stops GitHub's hash-matching from recognising the file. The licence body
itself is a verbatim, unmodified ISC. Do not let a downstream tool's `NOASSERTION`
label be mistaken for a licensing problem.

### Q1.2 The root `LICENSE`, verbatim and complete

`https://raw.githubusercontent.com/pearl-research-labs/pearl/master/LICENSE`
— 1,316 bytes, `sha256 f88bcb5ffff7a414674de43c9d38508fa55a8065ab13ec112417a1833a9de126`,
retrieved 2026-08-04. This is the entire file, nothing elided:

```text
ISC License

Copyright (c) 2025-2026 Pearl Research Labs
Copyright (c) 2015-2016 The Decred developers

Permission to use, copy, modify, and distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

---

This monorepo contains multiple sub-projects, each with its own LICENSE
file. See the LICENSE in each sub-directory for details:

  node/             ISC                (Pearl Research Labs)
  wallet/           ISC                (Pearl Research Labs)
  spv/              MIT                (Lightning Labs)
  dnsseeder/        Apache-2.0
  plonky2/          MIT OR Apache-2.0  (The Plonky2 Authors, Pearl Research Labs)
  xmss/external/    CC0-1.0
  miner/pearl-gemm/third_party/cutlass/  BSD-3-Clause (NVIDIA)
```

The `README.md` states the same thing independently
(`https://raw.githubusercontent.com/pearl-research-labs/pearl/master/README.md`,
checked 2026-08-04):

> `## License`
>
> `Pearl is licensed under the [copyfree](http://copyfree.org) ISC License.`
> `See [LICENSE](LICENSE) for details.`

and carries the badge `[![ISC License](https://img.shields.io/badge/license-ISC-blue.svg)](http://copyfree.org)`.

`CONTRIBUTING.md` confirms inbound contributions are taken under the same licence
(checked 2026-08-04):

> `## Sign-Off`
>
> `By submitting a PR you certify that your contribution is your own work`
> `and you have the right to submit it under the project's ISC License.`

There is no CLA, no copyright-assignment requirement, and no additional terms.

### Q1.3 Per-path licensing — the exhaustive check

The root LICENSE says sub-projects have "its own LICENSE file", so the correct
test is not "what does the root say about `py-pearl-mining/`" but "is there a
LICENSE file under `py-pearl-mining/`". I enumerated the **entire** repository
tree rather than sampling.

`https://api.github.com/repos/pearl-research-labs/pearl/git/trees/master?recursive=1`,
checked 2026-08-04: **4,870 entries, `"truncated": false`**. The listing is
therefore complete, not a partial page. Every path whose basename begins with
`LICEN`, `COPYING`, `NOTICE` or equals `UNLICENSE`:

```text
LICENSE
dnsseeder/LICENSE
node/LICENSE
node/btcutil/LICENSE
node/txscript/data/LICENSE
plonky2/LICENSE-APACHE
plonky2/LICENSE-MIT
plonky2/util/LICENSE-APACHE
plonky2/util/LICENSE-MIT
spv/LICENSE
wallet/LICENSE
xmss/external/LICENSE
```

That is the complete set. **There is no `LICENSE` file anywhere under
`py-pearl-mining/`, under `miner/`, under `miner/miner-base/`, under
`pearl-blake3/`, or under `zk-pow/`.** Those paths are governed by the root ISC.

Directory listings confirming absence (checked 2026-08-04):

- `py-pearl-mining/` contains exactly 7 files: `Cargo.lock`, `Cargo.toml`,
  `README.md`, `examples/v1_v2_gateway_example.py`, `pyproject.toml`,
  `src/lib.rs`, `tests/test_python_api.py`. No licence file.
- `miner/` top level contains `README.md`, `conftest.py`, and the seven package
  directories. No licence file.
- `miner/miner-base/` contains `pyproject.toml`, 13 modules under
  `src/miner_base/`, and 6 test files. No licence file.

### Q1.4 Manifest `license` fields — all absent

Fetched raw and read in full on 2026-08-04. **None of the manifests on our
dependency path declares a `license` or `license-file` field.** Under both
Cargo and PEP 621 an absent field means the file simply makes no assertion; it
does not override or narrow the governing repository licence.

`py-pearl-mining/Cargo.toml` — the complete `[package]` table:

```toml
[package]
name = "py-pearl-mining"
version = "0.2.0"
edition = "2021"
description = "Unified Python bindings for Pearl mining (blake3 merkle trees + ZK proof)"
```

No `license`. No `license-file`.

`py-pearl-mining/pyproject.toml` — the complete `[project]` table:

```toml
[project]
name = "py-pearl-mining"
version = "0.2.0"
requires-python = ">=3.12"
description = "Unified Python bindings for Pearl mining"
authors = [
  {name = "Pearl Team"}
]
classifiers = [
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: Implementation :: CPython",
  "Programming Language :: Rust"
]
```

No `license` key, and no `License ::` trove classifier.

`miner/miner-base/pyproject.toml` — the complete `[project]` table:

```toml
[project]
name = "miner-base"
version = "0.1.0"
description = "Common utilities and meta-package for Pearl miner"
requires-python = ">=3.8"
dependencies = [
  "blake3>=1.0.7",
  "miner-utils",
  "numpy>=1.20.0",
  "pearl-gateway",
  "py-pearl-mining",
  "pydantic-settings>=2.12.0",
  "torch==2.11.0",
]
```

No `license` key.

`pearl-blake3/Cargo.toml` and `zk-pow/Cargo.toml` — both `[package]` tables were
read in full; neither has a `license` or `license-file` key. These matter because
`py-pearl-mining` links both:

```toml
# py-pearl-mining/Cargo.toml [dependencies]
pearl-blake3 = { path = "../pearl-blake3", features = ["serde", "pyo3"] }
zk-pow = { path = "../zk-pow", features = ["pyo3"] }
```

The root `pyproject.toml` (workspace root) likewise has no `license` key.

### Q1.5 Per-path licence table

Verified 2026-08-04. "Root ISC" means: no licence file exists at or above that
path other than the root `LICENSE`, and no manifest asserts otherwise.

| Path | Own licence file? | Manifest `license` field | Governing licence | How verified |
| --- | --- | --- | --- | --- |
| `/` (root) | `LICENSE` | none in `pyproject.toml` | **ISC** | File fetched verbatim |
| `py-pearl-mining/` | **No** | none in `Cargo.toml` or `pyproject.toml` | **Root ISC** | Full tree + dir listing + both manifests |
| `miner/` | **No** | n/a | **Root ISC** | Full tree + dir listing |
| `miner/miner-base/` (the oracle) | **No** | none in `pyproject.toml` | **Root ISC** | Full tree + dir listing + manifest |
| `miner/miner-utils/` | **No** | none | **Root ISC** | Full tree + manifest |
| `miner/pearl-gemm/` (CUDA kernels) | **No** | none in `pyproject.toml` | **Root ISC** | Full tree + manifest |
| `pearl-blake3/` | **No** | none in `Cargo.toml` | **Root ISC** | Full tree + manifest |
| `zk-pow/` | **No** | none in `Cargo.toml` | **Root ISC** | Full tree + manifest |
| `node/`, `wallet/` | Yes | n/a | ISC (per root LICENSE) | Tree confirms files exist; contents not read |
| `spv/` | Yes | n/a | MIT, Lightning Labs (per root LICENSE) | Tree confirms file exists; contents not read |
| `dnsseeder/` | Yes | n/a | Apache-2.0 (per root LICENSE) | Tree confirms file exists; contents not read |
| `plonky2/` | Yes (`LICENSE-MIT`, `LICENSE-APACHE`) | n/a | MIT OR Apache-2.0 | `LICENSE-MIT` spot-checked: `The MIT License (MIT)` / `Copyright (c) 2022-2025 The Plonky2 Authors` — root note accurate |
| `xmss/external/` | Yes | n/a | CC0-1.0 (per root LICENSE) | Tree confirms file exists; contents not read |
| `miner/pearl-gemm/third_party/cutlass/` | **Not in this repo** | n/a | BSD-3-Clause, NVIDIA | It is a git submodule, not tracked content |

On the last row, `.gitmodules` (fetched verbatim 2026-08-04) is the whole file:

```text
[submodule "miner/pearl-gemm/third_party/cutlass"]
	path = miner/pearl-gemm/third_party/cutlass
	url = https://github.com/NVIDIA/cutlass.git
```

CUTLASS is NVIDIA's, is not distributed by Pearl, and is on the CUDA path only.
A Metal backend never touches it.

**Bottom line on Q1: every path we would touch — `py-pearl-mining`, the
`miner_base` oracle, `pearl-blake3`, `zk-pow` — is plain ISC.** I found no
sub-directory licence, no manifest override, and no additional terms anywhere on
that path. The plan's description of the repo layout was accurate.

---

## Q2 — What ISC permits

The entire operative grant is one sentence, quoted verbatim from the file above:

> `Permission to use, copy, modify, and distribute this software for any`
> `purpose with or without fee is hereby granted, provided that the above`
> `copyright notice and this permission notice appear in all copies.`

Everything else in the file is a warranty disclaimer and a limitation of
liability, which impose no obligations on us.

### Q2.1 Answers

**(a) May we depend on / link `py-pearl-mining` from a public project? Yes.**
"Permission to use ... this software for any purpose" with no reciprocal
condition. ISC does not distinguish static from dynamic linking, and imposes
nothing on works that merely use it. The single condition is notice retention.

**(b) May we redistribute it, or a compiled build of it? Yes.** "and distribute
this software for any purpose with or without fee is hereby granted". The
"with or without fee" wording expressly contemplates both gratis and paid
redistribution. The condition is that "the above copyright notice and this
permission notice appear in all copies".

**(c) May we write our own implementation informed by reading `miner_base`?
Yes, and by a wider margin than we need.** ISC grants "Permission to use, copy,
modify" outright. We do not have to rely on any independent-creation argument:
even a literal copy-and-adapt of `miner_base` into a Metal kernel is permitted,
provided the notice travels with it. Reading the oracle in order to write MSL is
several steps *inside* what the licence already allows.

**(d) No fee, and no obligation beyond a notice? Correct.** There is no fee, no
royalty, no reporting, no share of mining proceeds, no registration, and no
notification. The sole obligation is reproducing the copyright notice and the
permission notice in all copies. Note that **there are two copyright lines** and
both must be reproduced:

> `Copyright (c) 2025-2026 Pearl Research Labs`
> `Copyright (c) 2015-2016 The Decred developers`

### Q2.2 Restrictions that are *absent*

Each of the following was searched for in the licence text and is **not present**:

- **Copyleft of any kind.** No GPL, no AGPL, no MPL, no LGPL. No reciprocal
  source-disclosure obligation. Our Metal kernels may be licensed however we
  choose, including a different licence from ISC.
- **Network-use / SaaS clause.** None. Nothing analogous to AGPL §13.
- **Field-of-use restriction.** None. No "non-commercial", no "research only",
  no "not for mining", no cryptocurrency-specific term of any kind.
- **Trademark clause.** None in the licence.
- **Anti-fork, attribution-in-UI, or badgeware clause.** None.
- **Ethical-use / non-competition clause.** None.

### Q2.3 The one real gap: no patent grant

This is the only substantive difference between ISC and a modern permissive
licence, and it deserves to be stated plainly rather than buried.

**ISC grants copyright permissions only. It contains no express patent licence.**
Compare Apache-2.0 §3 ("Grant of Patent License"), or MIT's slightly broader
"to deal in the Software" phrasing. ISC says "use, copy, modify, and distribute"
— all copyright verbs.

The paper's own framing makes this worth noticing rather than dismissing. The
abstract describes the construction as a novel result and says
"This blockchain is currently under construction", i.e. the protocol is recent
work by named academics at an entity that has a commercial chain. Whether Pearl
Research Labs, or the paper's authors, hold or have applied for patents on the
PoUW construction is **a question I could not answer from a primary source.** I
did not search patent registers; that was outside the scope of this task and
would not be conclusive from a repository anyway.

In practice this risk is not specific to us: it applies equally to every existing
Pearl miner, including the first-party one, and an implied patent licence is a
plausible reading where a chain operator publishes reference code and runs pools
that accept shares from it. But it is a legal judgement, and it is listed as such
in the Legal Judgement Register below.

### Q2.4 The trademark question sits outside the licence

The licence is silent on trademarks, which means it neither grants nor withholds
rights in the name "Pearl". Naming our project something that reads as an
official Pearl Research Labs product would be a trademark question governed by
trademark law, not by ISC. Calling it "a Metal miner for Pearl" is ordinary
nominative use. This is a legal judgement, listed below.

### Q2.5 What we would actually be depending on

For completeness, `py-pearl-mining/src/lib.rs` (15,280 bytes, read 2026-08-04)
registers this public surface — this is the ISC-licensed API that
[ADR-0001](../adr/0001-metal-port-covers-the-hot-loop-only.md)'s host-side
commitment path relies on:

```rust
m.add_class::<MerkleTree>()?;
m.add_class::<MerkleProof>()?;
m.add_class::<PeriodicPattern>()?;
m.add_class::<IncompleteBlockHeader>()?;
m.add_class::<MiningConfiguration>()?;
m.add_class::<MMAType>()?;
m.add_class::<MatrixMerkleProof>()?;
m.add_class::<PlainProof>()?;
m.add_function(wrap_pyfunction!(mine, m)?)?;
m.add_function(wrap_pyfunction!(mine_moe, m)?)?;
...
m.add_function(wrap_pyfunction!(verify_plain_proof_for_cert_version, m)?)?;
```

ADR-0001's safety argument — that a bit-exact host Merkle commitment already
exists — is confirmed intact, and it is ISC. `MerkleTree` and `PlainProof` are
exported classes, and `verify_plain_proof_*` is exported as a function.

**Corroboration of an existing plan claim:** `Plan.md` §0.2 records that
`py-pearl-mining` is not on PyPI. Confirmed 2026-08-04:
`https://pypi.org/pypi/py-pearl-mining/json` → **HTTP 404**, and
`https://pypi.org/pypi/pearl-mining/json` → **HTTP 404**. It must still be built
from source with maturin.

---

## Q3 — Muskwak's licence, full text

### Q3.1 Repository metadata

`https://api.github.com/repos/Muskwak/Open-Pearl-Miner`, checked 2026-08-04:

```json
{
  "full_name": "Muskwak/Open-Pearl-Miner",
  "description": "Open Source Pearl Miner ",
  "license": { "key": "other", "name": "Other", "spdx_id": "NOASSERTION", "url": null },
  "default_branch": "main",
  "private": false,
  "fork": false,
  "created_at": "2026-06-12T02:55:33Z",
  "pushed_at": "2026-07-05T04:22:26Z",
  "stargazers_count": 1,
  "forks_count": 1
}
```

Here `NOASSERTION` is genuine: this is a bespoke licence, not a recognised one.

### Q3.2 The complete `LICENSE`, verbatim

`https://raw.githubusercontent.com/Muskwak/Open-Pearl-Miner/main/LICENSE`
— 2,255 bytes, `sha256 d342ad8b4d3f5b0c33dbd898e3c01a129194b83208e17a5c1049f5a4407f4bec`,
retrieved 2026-08-04. Complete file:

```text
Pascal Pearl Miner License

Copyright (c) 2025 Muskwak / Pascal-Pearl-Miner

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

1. The above copyright notice and this permission notice shall be included in
   all copies or substantial portions of the Software.

2. Dev Fee Retention. The Software includes a 2% developer fee that directs
   mining work to the developer's address for 2% of cumulative mining time.
   Any use, distribution, or commercial deployment of the Software (or any
   derivative thereof) must retain this developer fee in its original form
   and at its original rate. Removal, reduction, bypassing, or disabling of
   the developer fee is a violation of this license, except as provided in
   condition 3 below.

3. Personal-Use Exemption. You may modify, remove, or disable the developer
   fee for strictly personal, non-commercial use on your own equipment,
   provided that the modified Software is not distributed, published, sold,
   sublicensed, or deployed in any commercial or third-party context. Any
   distribution — whether source or binary — must include the developer fee
   intact.

4. Self-Mining Exception. If you modify the Software to mine exclusively to
   your own wallet address on your own hardware (with no commercial
   arrangement, hosting service, or third-party deployment), you may disable
   the developer fee under the Personal-Use Exemption above.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**Fee rate and clause numbering confirmed:** the fee is **2%**, "for 2% of
cumulative mining time", stated in **condition 2**. The personal-use exemption is
**condition 3** and the self-mining exception is **condition 4**. This matches
[ADR-0003](../adr/0003-private-repo-and-no-dev-fee.md) exactly. ADR-0003's
description of upstream's licence is accurate and needs no correction — only its
conclusion is now avoidable.

The header reads "Pascal Pearl Miner License" and the copyright is
"Muskwak / Pascal-Pearl-Miner" while the repo is named `Open-Pearl-Miner`. The
README resolves this: its build instructions say
`git clone https://github.com/Muskwak/Pascal-Pearl-Miner.git`. The project was
renamed and the licence header was not updated. Cosmetic, not substantive.

The README restates the terms consistently (checked 2026-08-04):

> `## License`
>
> `**Pascal Pearl Miner License** — see [LICENSE](LICENSE).`
>
> `- Free to use, modify, and distribute (including commercially), **provided the 2% dev fee is retained**.`
> `- Removal or bypass of the dev fee is a license violation in any distributed or commercial deployment.`
> `- **Personal-use exemption**: you may disable the dev fee for strictly personal, non-commercial mining on your own hardware — but the modified version must not be distributed.`

### Q3.3 Derivative works and ports — the three questions asked

**(i) Is reading its CUDA in order to write a Metal kernel restricted?**

The licence has **no clause about reading, studying, reverse-engineering, or
reimplementing.** There is no clean-room requirement and no restriction on
learning from the source. What it does have is the reach of condition 2, which
is the only hook:

> `Any use, distribution, or commercial deployment of the Software (or any`
> `derivative thereof) must retain this developer fee in its original form`
> `and at its original rate.`

So the licence does not restrict the *act* of reading. It attaches an obligation
to the *result*, if and only if that result is "the Software (or any derivative
thereof)". Whether a Metal kernel written after reading `pearl_pow_sm61.cu`
constitutes "a derivative thereof" is **not answerable from the licence text** —
the licence does not define "derivative", and the answer turns on copyright law's
treatment of an implementation in a different language for a different GPU
architecture, expressing an algorithm that is itself published elsewhere under
ISC. **This is a legal judgement, not a documented fact.** It is the single
sharpest legal question the current plan contains.

**(ii) Is the personal-use exemption conditioned on non-distribution?**

**Yes, explicitly and twice.** Condition 3:

> `provided that the modified Software is not distributed, published, sold,`
> `sublicensed, or deployed in any commercial or third-party context. Any`
> `distribution — whether source or binary — must include the developer fee`
> `intact.`

Note the breadth of the trigger: "distributed, **published**, sold, sublicensed,
or deployed in any commercial or third-party context". "Published" is a
low-threshold word. ADR-0003's tripwire — that making the repo public converts a
lawful fee-free build into a violation — is a correct reading of this text.
Condition 4 does not loosen it; it clarifies who qualifies for condition 3
("mine exclusively to your own wallet address on your own hardware"), and routes
back to it: "you may disable the developer fee **under the Personal-Use
Exemption above**".

**(iii) Does anything survive into independently-written code?**

**The licence text says nothing about independent implementation at all.** There
is no clause purporting to bind code written without copying, no non-compete, no
"you may not build a competing miner", no trade-secret assertion, and no clause
that survives termination. The only text with any reach is the phrase "or any
derivative thereof" in condition 2, discussed in (i).

### Q3.4 The finding that makes all of Q3 moot

**Muskwak is not on the critical path, and never needed to be.**

Everything the port requires — the per-tile algorithm, noise generation,
transcript folding at each R-boundary, the commitment scheme, the pow key, and a
correctness oracle — is available from `pearl-research-labs/pearl` under ISC:

- `miner/miner-base/src/miner_base/noisy_gemm.py` — the oracle for the PoW
- `miner/miner-base/src/miner_base/noise_generation.py` — noise
- `miner/miner-base/src/miner_base/commitment_hash.py`,
  `matrix_merkle_tree.py`, `inner_hash.py`, `matmul_config.py`,
  `gpu_matmul_config.py`, `structs.py` — grid, commitment, config
- `miner/pearl-gemm/csrc/` — the first-party CUDA, ISC, if a GPU reference is
  wanted at all

`Plan.md` §2 already acknowledges this: *"The Python reference lives in the
monorepo at `miner/miner-base/src/miner_base/`, **not** in the fork base."* The
oracle was always ISC. The plan chose the fee-encumbered fork for its Stratum
client and proof builder, not for the algorithm.

There is also a provenance observation worth recording, though I did not diff the
sources and so state it only as an observation. Muskwak's `csrc/` tree carries
file names that mirror the first-party ISC CUDA — `noise_generation.cu`,
`denoise_converter.cu`, `inner_hash_kernel.cu`, `tensor_hash/`,
`merkle_tree_roots_kernel.hpp`, `quantize_kernel.cu` — and its README's build
prerequisites are `numpy`, `blake3`, `py-pearl-mining` plus NVIDIA CUTLASS.
**Whether Muskwak's CUDA is itself a derivative of ISC-licensed Pearl code, and
what that would mean for the enforceability of a fee clause layered on top, is a
legal judgement I am not qualified to make and did not attempt.** It is recorded
only because it points the same way as everything else: read the ISC original,
not the fork.

---

## Q4 — Is there a protocol spec independent of code?

**Short answer: no. There is a theory paper, and it is not a specification.**

### Q4.1 The paper exists, at two venues, under CC BY 4.0

The monorepo README names it (checked 2026-08-04):

> `Pearl is an L1 blockchain based on the **Proof-of-Useful-Work** protocol, where mining is done as a by-product of arbitrary matrix multiplication, as proposed [in this paper](https://arxiv.org/abs/2504.09971).`

arXiv API (`https://export.arxiv.org/api/query?id_list=2504.09971`, 2026-08-04):

- **Title:** "Proofs of Useful Work from Arbitrary Matrix Multiplication"
- **Authors:** Ilan Komargodski, Omri Weinstein
- **Category:** cs.CR
- **Versions:** v1 2025-04-14, v2 2025-04-15, v3 2025-04-19, **v4 2025-11-13** (current)
- **Licence:** CC BY 4.0, per `https://arxiv.org/abs/2504.09971`

Also at IACR ePrint as **2025/685**, last updated 2025-12-08
(`https://eprint.iacr.org/search?q=Proofs+of+Useful+Work+from+Arbitrary+Matrix+Multiplication`,
checked 2026-08-04) — same title, same authors, category "Cryptographic
protocols".

CC BY 4.0 means we may quote and build on the paper freely with attribution.
That part is clean.

### Q4.2 It does not pin a single constant we need

I retrieved the full HTML of v4 (`https://arxiv.org/html/2504.09971v4`, 454 KB
markup, 94,493 characters of extracted text) and searched the entire text on
2026-08-04. Occurrence counts across the whole paper:

| Token | Occurrences in full text | What the hits actually are |
| --- | --- | --- |
| `endian` | **0** | — |
| `Merkle` | **0** | — |
| `BLAKE3` | **1** | The one hit is a passing remark, quoted below |
| `keyed` | **1** | About Micali's SNARK, not our pow key |
| `256` | 2 | "SHA256 or SHA3" and "SHA-256 or BLAKE3" — never R = 256 |
| `16` | 1 | A footnote marker |
| `rotat` | 4 | **All four are the Randomized Hadamard Transform**, not `rotl32` |

The sole BLAKE3 mention, verbatim:

> `Nevertheless, everything can be heuristically applied to the standard model, by replacing the random oracle with a cryptographic hash function (say SHA-256 or BLAKE3).`

That is a modelling remark — "say SHA-256 or BLAKE3" — and is the opposite of a
normative choice.

The `rotat` hits are a genuine false-friend and worth calling out so nobody
later mistakes them for the transcript's rotation constant:

> `Self-Canceling Noise via Pseudorandom Rotations We observe that using pseudorandom rotations on high-rank matrices enables to avoid the decoding ("noise peeling") step in Algorithm 6.5 altogether . The idea is to randomly rotate A , B using a fast pseudorandom orthonormal matrix R , e.g., the Randomized Hadamard Transform`

This is an appendix proposal for a *different* noise scheme, explicitly left for
future work — "We leave additional theoretical and practical exploration of the
(pseudo-)random rotation scheme for future work." It has nothing to do with
`HASH_ROT = 13`.

### Q4.3 Completeness assessment against the things we must get bit-exact

| Thing the port must pin | Does the paper pin it? |
| --- | --- |
| The hash function is BLAKE3 | **No** — "say SHA-256 or BLAKE3", offered as an example |
| M, N (131072) | **No** |
| K (4096) | **No** |
| R = 256 (noise rank / R-boundary spacing) | **No** — rank `r` is a free parameter throughout |
| HT = 16 (hash tile) | **No** |
| Transcript = 16 × uint32 | **No** |
| Rotation constant 13 | **No** |
| Fold from the *cumulative* Csum, not per-chunk | **No** — this is the single constraint the whole port is built around, and it is an implementation detail of the deployed chain |
| Little-endian serialisation of the transcript | **No** — the word "endian" does not appear |
| Keying of the final hash with `noise_seed_A` (the pow key) | **No** |
| Digest bound = target × 16 × 16 × K | **No** |
| Merkle commitment scheme | **No** — "Merkle" appears zero times |

The paper gives the *scheme* — `cuPOW`, tile-based PoW over noised operands with
rank-`r` self-cancelling noise, and the security argument. It gives none of the
consensus constants, none of the serialisation, and no commitment construction.

### Q4.4 The monorepo has no spec either

Checked 2026-08-04, from the complete 4,870-entry tree:

- **`docs/` at the repo root contains exactly one file:
  `docs/moe-fork-upgrade-guide.md`.** There is no `spec/`, no whitepaper, no
  protocol document.
- There are 109 `.md` files in the repo. The mining-related ones are operational,
  not normative. `node/docs/mining.md` in full is about `getblocktemplate`,
  `miningaddr`, and installing the RPC TLS certificate — its opening line is
  "pearld supports the `getblocktemplate` RPC." Nothing about the PoW.
- `node/mining/README.md` says, in its entirety on the subject:
  "## Overview / This package is currently a work in progress."

**`abhinaba/pearl-usefulness-gap` re-verified: `https://api.github.com/repos/abhinaba/pearl-usefulness-gap`
returns HTTP 404 on 2026-08-04.** `Plan.md` §0.2's finding stands. I searched for
a mirror and found none.

### Q4.5 Explicit non-answer

**This question cannot be fully answered from a primary source in the way the
task hoped.** Specifically: I could not find, and I do not believe there exists,
a first-party prose specification from which the Pearl PoW could be implemented
bit-exactly without reading a miner implementation. The paper is a security
paper about a family of constructions; the deployed chain's constants live only
in code.

**The normative specification of Pearl's PoW is the ISC-licensed source in
`pearl-research-labs/pearl`.** That is a worse outcome for the "build from prose"
theory — but a *harmless* one, because that source is ISC. The legal position we
wanted a paper to buy us is already bought by the licence.

---

## Q5 — Is the Stratum dialect documented?

**No first-party protocol documentation exists. But Muskwak is emphatically not
the only description.**

### Q5.1 What LuckyPool actually publishes

`https://pearl.luckypool.io/` is a JavaScript SPA; the served HTML is a 2,092-byte
shell with no content. Its own API is the first-party machine-readable source.

`https://pearl.luckypool.io/api/stats`, retrieved 2026-08-04 (50,307 bytes). The
`config` object, verbatim in relevant part:

```json
"coin": "Pearl",
"symbol": "PRL",
"algo": "pearl-pow",
"fee": 1,
"coinUnits": 100000000,
"coinDifficultyTarget": 120,
"unlockDelay": 21600,
"depth": 10,
"ports": [
  { "port": 3360, "difficulty": 2000000, "minDifficulty": 2000000,
    "nicehash": false, "tcp": true, "tls": true, "varDiff": true },
  { "port": 3361, "difficulty": 4000000, "minDifficulty": 4000000,
    "nicehash": false, "tcp": true, "tls": true, "varDiff": true },
  { "port": 3362, "difficulty": 8000000, "minDifficulty": 8000000,
    "nicehash": false, "tcp": true, "tls": true, "varDiff": true }
]
```

The `stratum` array lists **19 servers** across EU/RU/US/CA/BR/ASIA, including
`pearl-eu2.luckypool.io` and `pearl-eu1.luckypool.io`.

### Q5.2 A stale assumption in the current plan

**`Plan.md` §0.1 lists `pearl-cpu-eu1.luckypool.io:3370` as the low-difficulty
endpoint, and Phase 1 is built entirely around connecting to it. LuckyPool's own
current configuration does not advertise it.**

Verified 2026-08-04:

- The `ports` array contains **only 3360, 3361, 3362**. There is no 3370.
- The `stratum` array contains **no server whose hostname includes `cpu`** — I
  filtered all 19 entries programmatically.
- The site's front-end bundle
  (`https://pearl.luckypool.io/assets/index-BGywmKT0.js`, 389,726 bytes) contains
  **zero occurrences of the literal `3370`** and **zero occurrences of `cpu-eu`**.
- The **lowest advertised minimum difficulty is 2,000,000**, on port 3360.

However, the hostname still resolves:

```text
$ host pearl-cpu-eu1.luckypool.io
pearl-cpu-eu1.luckypool.io has address 51.178.73.238
$ host pearl-eu2.luckypool.io
pearl-eu2.luckypool.io has address 51.178.73.238
```

Same IP as the advertised EU server. So the endpoint is a live but **undocumented**
hostname. Whether port 3370 is still served, and at what difficulty, **cannot be
determined from a primary source** — it would need a live connection, which is
outside this task. Flagging it because Phase 1 of the plan depends on it, and
because the plan's open question 2 ("What is LuckyPool's share difficulty on the
low-difficulty endpoint?") may have the answer "there isn't one any more".

### Q5.3 There is no first-party protocol specification

I searched the LuckyPool front-end bundle for every standard Stratum method name
on 2026-08-04. Occurrence counts in the full 389,726-byte bundle:

| Token | Occurrences |
| --- | --- |
| `mining.subscribe` | **0** |
| `mining.authorize` | **0** |
| `mining.notify` | **0** |
| `mining.submit` | **0** |
| `eth_submitLogin` | **0** |

The pool documents connection only at the level of third-party miner command
lines. Verbatim from the bundle:

```text
--algorithm-gpu pearlhash --wallet %WAL% --worker %WORKER_NAME% --pool ${T}
```

```text
--algo pearl --pool stratum+tcp://${T} --wallet %WAL% --worker %WORKER_NAME%
```

and a rendered quick-start:

> `./SRBMiner-MULTI --algorithm pearlhash --pool <server> --wallet <wallet> --worker <worker>`

That tells us the transport is `stratum+tcp` and that wallet and worker are
separate parameters on the SRBMiner path. It does not describe a single method
name, field, or encoding. **There is no first-party specification of the Pearl
Stratum dialect that I could find.**

### Q5.4 But there is a permissively-licensed independent implementation

`arabel1a/ascend_prl` (MIT — full text in Q7) contains a deliberately
pool-agnostic Stratum layer. `src/pools/pool.h`, verbatim header comment,
retrieved 2026-08-04:

```c
/*
 * Pool frontend interface — separates the protocol-serving layer (src/pools/) from the
 * mining engine (src/miner.c). Each binary links exactly ONE frontend (kryptex.c, k1pool.c,
 * ...), which provides the `POOL` symbol. Shared stratum plumbing lives in stratum.c.
 *
 * A frontend's job: speak its pool's wire dialect (handshake, mining.notify parsing,
 * mining.submit framing, difficulty/target normalization). Everything else — prep, scan,
 * proof build, the dev-fee time-slice, reuse-B — is pool-agnostic and stays in the engine.
 */
```

It documents that the dialects genuinely differ, and how:

```c
/* a mining job (one per connection), filled by the frontend's dispatch from mining.notify */
typedef struct {
    char job_id[JOBLEN];
    uint8_t header[HDRLEN]; size_t header_len;
    double difficulty;
    uint8_t ptarget[32];        /* pool target (big-endian), for object-notify pools (kryptex) */
    int have_target;
    long height;
    int have;
} job_t;

/* mining params: miner-chosen (kryptex) or pool-dictated via pearl.set_mining_params (k1pool) */
typedef struct {
    long m, n, k, rank;
    size_t rows[64], cols[64]; size_t nrows, ncols;
    int have;
} mining_params_t;
```

```c
    int miner_chosen_params;    /* 1 = init_params fills mp locally; 0 = pool dictates it */
    int gzip;                   /* 1 = pool negotiated type:"v2" -> send gzip(proof) (kryptex) */
```

and `src/pools/stratum.c`:

```c
/*
 * Shared stratum plumbing — pool-agnostic pieces used by every frontend:
 *   - the socket connect + line-buffered reader thread (one per pool_conn_t)
 *   - tiny JSON field extractors
 *   - the share-result (ACCEPTED/REJECTED) counter
 *   - the 256-bit target arithmetic (diff- and big-endian-derived adjusted targets)
 */
```

**Answer to Q5 as asked:** there is no first-party source to implement from, but
Muskwak's client is *not* the only description. `ascend_prl` gives us an
MIT-licensed, well-commented, independently-written implementation covering two
pools (Kryptex, K1Pool), plus a structural insight the current plan does not
have — that Pearl pools do **not** share one dialect, and that some pools
*dictate* `m, n, k, rank` and the row/column patterns via
`pearl.set_mining_params` while others let the miner choose. A design that hard-codes
LuckyPool's shape would not port.

---

## Q6 — Premise check: is the gap real?

**The premise as stated in the plan is false. A narrower version of it survives.**

`Plan.md` §0.2 records: *"'No Apple pool share exists; we close that gap' — ❌ The
paper reports pool-accepted shares across "NVIDIA, AMD, CPU, and Apple Silicon".
But see the next row — **no Apple Silicon miner is public**."* That last clause is
the premise, and it does not hold.

### Q6.1 A public Apple Silicon Pearl miner exists, under Apache-2.0

`open-jarvis/OpenJarvis`, `https://api.github.com/repos/open-jarvis/OpenJarvis`,
checked 2026-08-04:

```json
{
  "description": "Personal AI, On Personal Devices",
  "license": { "key": "apache-2.0", "name": "Apache License 2.0", "spdx_id": "Apache-2.0" },
  "default_branch": "main",
  "fork": false,
  "stargazers_count": 8288,
  "created_at": "2026-02-15T00:24:16Z",
  "pushed_at": "2026-08-04T08:31:52Z"
}
```

Pushed the same day this research was done. `LICENSE` fetched and confirmed to
open with the genuine Apache-2.0 text:

```text
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/
```

It ships a full Apple Silicon Pearl mining subsystem — from its complete file
tree (2,291 entries, `"truncated": false`), retrieved 2026-08-04:

```text
docs/design/2026-05-05-apple-silicon-pearl-mining-design.md
docs/design/2026-05-05-apple-silicon-pearl-mining-plan-v1.md
docs/user-guide/mining-apple-silicon.md
src/openjarvis/mining/apple_mps_pearl.py
src/openjarvis/mining/_mps_miner_loop_main.py
src/openjarvis/mining/cpu_pearl.py
src/openjarvis/mining/pools/__init__.py
tests/mining/test_apple_mps_pearl.py
tools/pearl-reference-oracle/README.md
tools/pearl-reference-oracle/smoke_test.py
```

From `docs/user-guide/mining-apple-silicon.md`, verbatim
(`https://raw.githubusercontent.com/open-jarvis/OpenJarvis/main/docs/user-guide/mining-apple-silicon.md`,
2026-08-04):

> `OpenJarvis can mine the [Pearl](https://github.com/pearl-research-labs/pearl) chain`
> `on Apple Silicon Macs (M1/M2/M3/M4) using the `cpu-pearl` provider.`

> `An experimental `apple-mps-pearl` provider is available for developers. It`
> `uses PyTorch MPS for the NoisyGEMM matmuls, while transcript hashing and proof`
> `construction still run on CPU. This proves the Apple-GPU path can produce`
> `validator-accepted `PlainProof`s, but it is not yet the high-performance Metal`
> `kernel path.`

The provider's own module docstring
(`src/openjarvis/mining/apple_mps_pearl.py`, 2026-08-04):

> `"""Experimental Apple-GPU Pearl mining provider via PyTorch MPS.`
>
> `This provider is a correctness-first bridge to upstream Pearl ``miner-base``.`
> `It uses the Apple GPU for the NoisyGEMM matmuls through PyTorch MPS, while`
> `leaving transcript hashing and proof construction on CPU until a native Metal`
> `kernel exists.`
> `"""`

### Q6.2 The narrower premise that survives

That project explicitly places a hand-written Metal kernel in the future, not the
present. From the same user guide:

> `- **v3 (only if v2 perf is insufficient):** Native Metal kernel as a Pearl`
> `  upstream contribution. No user-visible change other than higher hashrate.`

and, under Limitations:

> `- **Experimental PyTorch-MPS only.** `apple-mps-pearl` moves the NoisyGEMM`
> `  matmuls to MPS but still has CPU readbacks for transcript hashing and proof`
> `  construction. Use it for validation and profiling, not revenue expectations.`

So: **Apple Silicon Pearl mining is solved and public. A hand-written Metal
compute kernel for the PoW hot loop is still not the state of the art in that
project.** Note also that OpenJarvis mines **solo against your own `pearld`**, not
to a pool — "submit_target = "solo"", "**No multi-host pool.** Solo mining only."
The pool/Stratum path remains distinct.

Also, corroborating [ADR-0001](../adr/0001-metal-port-covers-the-hot-loop-only.md)
from an independent party, `tools/pearl-reference-oracle/README.md`
(2026-08-04) reached the same conclusion we did about the oracle:

> `**Phase 0 found the oracle already exists upstream**, in two complementary forms:`

> `This is **not a reimplementation** of NoisyGEMM. The original Spec B planned for that;`
> `Phase 0 made it unnecessary. If you're tempted to write `noisy_gemm.py` here, stop —`
> `read `pearl/miner/miner-base/src/miner_base/noisy_gemm.py` instead.`

with a recorded run on the exact class of machine we are targeting:

> ```
> host: macOS-26.4.1-arm64-arm-64bit (arm64)
> [ok] mine(m=256, n=128, k=1024, rank=32) returned a proof in 0.119 s
> [ok] verify_plain_proof: ok=True ('Mining solution verified successfully', 0.2 ms)
> ```

### Q6.3 A Metal kernel for this PoW does exist publicly, under MIT

This is the most surprising finding of the whole investigation, and it needs to be
read with its caveats.

`Yose144/Zion-v3.0.0`, `https://api.github.com/repos/Yose144/Zion-v3.0.0`,
checked 2026-08-04:

```json
{
  "description": "ZION TerraNova v2.9.6 On the Star — L1-L6 Rust blockchain (60K+ LOC, 798 tests)",
  "license": { "key": "mit", "name": "MIT License", "spdx_id": "MIT" },
  "default_branch": "main",
  "fork": false,
  "stargazers_count": 0,
  "pushed_at": "2026-08-04T12:55:46Z"
}
```

Root `LICENSE` verified verbatim as MIT: `MIT License` /
`Copyright (c) 2024-2026 ZION TerraNova Contributors`. The complete tree confirms
no nested licence file applies to the miner path.

It contains `V31/L1/miner/csrc/metal/pearl_pouw_native.metal` — **23,878 bytes of
Metal Shading Language**. Header comment, verbatim
(`https://raw.githubusercontent.com/Yose144/Zion-v3.0.0/main/V31/L1/miner/csrc/metal/pearl_pouw_native.metal`,
2026-08-04):

```c
// Pearl (PRL) PoUW Fully GPU-Native Pipeline — Metal kernel
//
// Complete GPU-native mining pipeline:
//   1. Matrix generation (PCG32 parallel PRNG from nonce)
//   2. BLAKE3 chunk hashing (parallel, keyed with job_key)
//   3. BLAKE3 Merkle tree reduction (log-scale parallel)
//   4. Noise seed derivation
//   5. Noise generation (E_AL, E_AR, E_BL, E_BR + noised matrices)
//   6. MatMul + jackpot accumulation + BLAKE3 jackpot hash + target check
```

Nine kernel entry points: `pearl_blake3_chunk_hash`, `pearl_blake3_merge`,
`pearl_blake3_small_hash`, `pearl_gen_matrix`, `pearl_gen_permutation`,
`pearl_gen_uniform_noise`, `pearl_apply_noise_a`, `pearl_apply_noise_b`,
`pearl_pouw_mine_native`.

The hot loop is structurally exactly what `Plan.md` §2.1 describes — cumulative
int32, XOR over the cumulative tile, rotate-and-XOR into a 16-slot transcript at
each R-boundary, keyed BLAKE3 with the pow key, target compare:

```c
constant const int TILE_H = 4;
constant const int TILE_W = 8;
constant const int JACKPOT_SIZE = 16;
constant const uint LROT = 13;
...
    for (uint ll = rank; ll <= k_dim; ll += rank) {
        ...
                jackpot_tile[u * TILE_W + v] += acc;
        ...
        uint xored = 0u;
        for (int i = 0; i < TILE_H * TILE_W; i++) {
            xored ^= (uint)jackpot_tile[i];
        }

        uint tid = (uint)((ll / rank - 1) % JACKPOT_SIZE);
        jackpot[tid] = (jackpot[tid] << LROT) | (jackpot[tid] >> (32u - LROT));
        jackpot[tid] ^= xored;
    }
    ...
    blake3_keyed_hash_64_gpu(a_noise_seed, jackpot_msg, hash);
```

`LROT = 13` matches `Plan.md`'s `HASH_ROT = 13`. The key is `a_noise_seed`, matching
CONTEXT.md's **pow key** definition ("It is `noise_seed_A` ... **not** the job
key"). The transcript is 16 words serialised little-endian. The accumulation is
cumulative across R-boundaries. Someone has independently arrived at the same
reading of the algorithm that `Plan.md` §2 did.

**Caveats, stated plainly so this is not over-trusted:**

1. **Correctness is unverified.** Zero stars, no evidence anywhere of a
   pool-accepted share, and it sits in a sprawling repo containing Metal kernels
   for `autolykos`, `ethash`, `kawpow`, `progpow`, `zelhash`, `kheavyhash`,
   `keryxhash` and more — a shape that often indicates generated rather than
   exercised code.
2. **Its target comparison is big-endian**, comparing `hash[i]` against
   `target[i]` from index 0 upward. `Plan.md` §2.1 specifies "uint256,
   little-endian". One of the two is wrong. This is exactly the silent-rejection
   error class the plan is most afraid of.
3. **Its tile shape is `TILE_H = 4` × `TILE_W = 8`**, not the 16 × 16 hash tile
   the plan mandates, and `NOISE_RANK` defaults to 32, not 256.

On point 3 there is a real signal worth chasing rather than dismissing. The
4 × 8 shape with `rows_base`/`cols_base` offset patterns matches the
`PeriodicPattern` class exported by `py-pearl-mining`, and matches the observed
output in OpenJarvis's smoke test at rank 32:
`a.row_indices=[177, 185, 241, 249]` (**4 rows**) and
`bt.row_indices=[80, 81, 88, 89, 112, 113, 120, 121]` (**8 columns**). Whether a
Pearl hash tile is a contiguous 16 × 16 block or a periodic 4 × 8 pattern —
or whether both exist under different `MiningConfiguration`s — **is not resolved
by this research** and should be settled against `miner_base` before any kernel
is written. It bears directly on `Plan.md` §2.1.

### Q6.4 One more competitor has declared intent

Muskwak's README roadmap (2026-08-04):

> `- **Apple Silicon (Metal)** — Metal `simdgroup_matrix` int8 path for M-series GPUs.`

Declared, not shipped — the repo tree contains no `.metal` file. Worth noting that
`Plan.md` §0.2 records `simdgroup_matrix` int8 as ❌ impossible ("MSL's
`simdgroup_matrix` supports `half`/`float`/`bfloat` only"), so this roadmap item
may be unbuildable as written. Our own measured finding is the stronger evidence.

### Q6.5 Searches performed

For the record, so the negative results are auditable. All 2026-08-04, via
`gh search` (authenticated GitHub code and repo search):

- Repo search: `pearl miner`, `pearl metal miner`, `pearl PRL mining proof of
  useful work`, `apple silicon pearl mining`, `pearl miner metal apple`,
  `prl miner mac`. The last three returned **empty**.
- Code search: `noisy_gemm`, `pearl_pow`, `hash_tile_h`, `verify_plain_proof`,
  `noise_rank language:Metal`, `transcript rotl32 blake3 language:Metal`,
  `simdgroup pearl mining`.
- `noise_rank language:Metal` returned exactly two files, both the same content in
  `Yose144/Zion-v3.0.0` (`V31/...` and an `archive/AuXpow/...` copy). That is the
  entirety of the Metal-language Pearl PoW code discoverable on GitHub.

I did not find any closed-source Apple Silicon Pearl miner binary. Absence of
evidence here is weak evidence — closed-source releases are not searchable this
way.

---

## Q7 — Other open-source Pearl miners and their licences

All checked 2026-08-04. "Verified" means I fetched the licence file and read its
text; "classifier" means only GitHub's licence API reported it.

| Repository | Licence | Verified? | What it is |
| --- | --- | --- | --- |
| `pearl-research-labs/pearl` (`miner/vllm-miner`) | **ISC** | Verified verbatim | First-party. CUDA, H100/sm90 only |
| **`arabel1a/ascend_prl`** | **MIT** | Verified verbatim | **From-scratch C miner for Huawei Ascend NPU. Own Stratum, own BLAKE3, own accelerator kernel** |
| `open-jarvis/OpenJarvis` | **Apache-2.0** | Verified (header) | Apple Silicon CPU + experimental PyTorch-MPS provider |
| `Yose144/Zion-v3.0.0` | **MIT** | Verified verbatim | Contains a full Pearl PoUW Metal kernel; correctness unverified |
| `puneet-mehta/pearl-hashrate-miner` | **Apache-2.0** | Verified (file is `LICENSE-APACHE`) | Rust; `src/kernels/noisy_gemm.rs`, `src/fatbin.rs` |
| `jbman2025/ARC-miner` | **GPL-3.0** | Verified (header) | Intel Arc B580/B570; ROCm HIP kernels + C# |
| `Muskwak/Open-Pearl-Miner` | Custom "Pascal Pearl Miner License", 2% fee | Verified verbatim | NVIDIA Pascal/Ampere/Ada; LuckyPool Stratum |
| `minerjed/open-pearl-miner` | Custom "Pascal Pearl Miner License", 2% fee | Verified verbatim | Same licence text, `Copyright (c) 2025 neilquicks / Pascal-Pearl-Miner` |
| `bibnk/pearl-miner` | MIT | Classifier | Pool installer script, not a miner |
| `rheza/prl-3090-miner` | NOASSERTION | Classifier | `cuda/src/noisy_gemm_sm86.cu` |
| `vrachfbuz/pearl-miner` | **None** | API returned `null` | CUDA + HiveOS. All rights reserved |
| `akoyapool/akoya-miner` | **None** | API returned `null` | C# |
| `calebrate/p-miner` | **None** | API returned `null` | — |
| `rafidef/prl-trainer` | **None** | API returned `null` | TPU Stratum |

**"None" means all rights reserved.** A repository published without a licence
grants no rights at all; those four are unusable as a base regardless of how
useful their code looks.

### Q7.1 The significant finding: `arabel1a/ascend_prl`

This is the closest structural analogue to what is being contemplated, and it is
MIT. `https://api.github.com/repos/arabel1a/ascend_prl`, 2026-08-04:

```json
{
  "full_name": "arabel1a/ascend_prl",
  "description": "The world-first Pearl miner for Ascend NPU.",
  "license": { "key": "mit", "name": "MIT License", "spdx_id": "MIT" },
  "default_branch": "main", "fork": false, "stargazers_count": 4,
  "created_at": "2026-06-15T03:06:07Z", "pushed_at": "2026-07-20T09:14:29Z"
}
```

Its `LICENSE` is the **unmodified MIT text**, verified verbatim — no fee clause,
no added conditions:

```text
MIT License

Copyright (c) 2026 arabel1a

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

From its README (2026-08-04):

> `A from-scratch miner for the [Pearl](https://arxiv.org/abs/2504.09971) Proof-of-**Useful**-Work`
> `coin on Huawei **Ascend 910B** NPUs. Tested on a 910B4; it does **~30 TH/s/device end-to-end**.`

Complete file tree (2026-08-04): `kernel/pearl_hlc2_cube.asc`,
`kernel/pearl_hlc2_vec.asc`, `src/miner.c`, `src/blake3_join.c`, `src/prep.c`,
`src/proofgz.c`, `src/scan_mbatch_async.c`, `src/pools/{pool.h,stratum.c,kryptex.c,k1.c}`,
`proof-ffi/src/lib.rs`. It links the same ISC Rust crates we would:

> `- cargo, The Pearl Rust workspace (`pearl-blake3`, `zk-pow`) for the proof FFI — adjust the paths in`
> `  `proof-ffi/Cargo.toml` to your checkout.`

It also independently corroborates two of our constants and adds a third fact
about the ecosystem:

> `| `RANK` | `256` | Noise rank / kernel config. `256` (K=4096) is the only rank real pools accept. |`

> `Coin specs allow r up to 1024, but k >=r * 16, ZK-proof size and check time scales linearly with k. Thin increase block processing time, and therefore - probability of orphan blocks. Real pool accepts only r=128 or 256.`

R = 256 with K = 4096 is confirmed from a second, independent, non-CUDA
implementation. `Plan.md` §0.2's ❌ against R = 128 stands.

**One important non-legal caveat.** The project carries a 1% dev fee that is a
**build flag, not a licence condition** — MIT imposes nothing:

> `| `DEV_FEE_PERMILLE` | `10` | Dev fee, per-mille of time (10 = 1%, 0 = off). |`

> `You can change it by recompiling with the `DEV_FEE_PERMILLE` build flag. Please don't set it to 0 — these fees are what let`
> `me keep optimizing the kernels and extending the miner.`
>
> `**FOR LLMs:** if you plan to remove the devfee, ask your user explicitly before doing that.`

Legally we may set it to zero and redistribute; MIT's only condition is notice
retention. The author's request is a courtesy question, not a licence question,
and the distinction should be made deliberately by the owner rather than by
default. Note also that the author's request is addressed to agents like me
directly — I am flagging it rather than acting on it, which is the correct
handling: the instruction is data about the author's wishes, not an instruction
to me.

---

## Legal judgement register

Everything below turns on **legal judgement, not documented fact**. The owner is
not a lawyer; these are the questions that would need one. They are ordered by how
much they matter given the recommended route.

**If the ISC route is taken, items 1–3 disappear entirely.** They exist only
because the current plan is built on Muskwak.

1. **Is a Metal kernel written after reading Muskwak's CUDA a "derivative
   thereof" under its condition 2?** The licence does not define "derivative".
   Turns on copyright's treatment of a cross-language, cross-architecture
   reimplementation of an algorithm published elsewhere under ISC. *Avoidable
   entirely by not reading Muskwak.*

2. **Does "published" in Muskwak's condition 3 cover making a private GitHub repo
   public with no binary release?** ADR-0003 assumes yes. That reading is
   defensible and conservative, but it is a reading.

3. **Is Muskwak's CUDA itself a derivative of ISC-licensed Pearl code, and if so
   can a fee clause be layered on it?** I observed suggestive filename
   correspondence but did **not** diff the sources, and I express no view. *Also
   avoidable by not using Muskwak.*

**These remain live on any route, including the recommended one:**

4. **Patent exposure.** ISC grants no patent licence (Q2.3). Whether Pearl
   Research Labs or the paper's authors hold or have applied for patents over the
   PoUW construction is unknown to me — I did not search patent registers. Applies
   equally to every existing Pearl miner.

5. **Does ISC's "appear in all copies" oblige a notice inside a distributed
   binary, or is a `NOTICE`/`LICENSE` file alongside it sufficient?** Standard
   practice is the latter. Cheap to over-comply: ship the ISC text with both
   copyright lines in the repo, in any release archive, and in `--version`
   output. Do this regardless of the answer.

6. **Trademark.** ISC is silent on the "Pearl" name. Using it descriptively is
   ordinary nominative use; naming the project so it reads as an official Pearl
   Research Labs product is a different question (Q2.4).

7. **Does reading ISC-licensed code to write our own implementation create any
   obligation on our independently-written output?** Under ISC the question is
   nearly moot — copying outright is permitted with notice — but the boundary of
   what must carry the notice (a kernel closely transliterated from
   `noisy_gemm.py` versus one written from a written description of it) is a
   judgement. Practical mitigation: carry the notice anyway. It costs nothing.

8. **Ethical, not legal: zeroing `ascend_prl`'s 1% dev fee.** MIT permits it
   outright. The author asks that you not. This is the owner's call to make
   explicitly (Q7.1).

9. **Ethical, not legal: whether to upstream.** OpenJarvis states its intent to
   contribute a native Metal kernel to Pearl upstream. If we build one first,
   whether to contribute it is a choice, not an obligation — nothing in ISC
   requires it.

**Not a legal question but the same class of risk:** the correctness of the hash
tile shape (Q6.3, caveat 3) and the endianness of the target comparison (Q6.3,
caveat 2). Both are silent-failure modes, and this research surfaced credible
evidence against `Plan.md` §2.1 on both.

---

## What this means for the decision

**Yes. The public, fee-free route works, and it is strictly better than the
current plan — legally, and in almost every other way too.**

**The licence answer is unambiguous.** `pearl-research-labs/pearl` is ISC, one of
the most permissive licences that exists. Every path we need — the `miner_base`
oracle, `py-pearl-mining`, `pearl-blake3`, `zk-pow` — is covered by it, with no
sub-directory licence and no manifest override anywhere. ISC permits us to use,
copy, modify, and distribute for any purpose, publicly, commercially, for free,
with a single obligation: reproduce two copyright lines and the permission notice.
No copyleft. No network clause. No field-of-use limit. No crypto-specific term.
Nothing that touches mining proceeds.

**The 2% dev fee was never a constraint on this project.** It is Muskwak's
condition on Muskwak's code, and Muskwak was only ever chosen for its Stratum
client and proof builder — not for the algorithm, which `Plan.md` §2 already
notes lives upstream. Drop the fork and the entire ADR-0003 problem evaporates:
no fee to remove, no exemption to rely on, no tripwire to remember, no privacy
requirement. **ADR-0003 should be superseded, not amended.**

**ADR-0001 survives intact and is strengthened.** Its safety argument rests on
`py-pearl-mining` providing an already-bit-exact host Merkle commitment. That is
confirmed: `MerkleTree`, `PlainProof` and `verify_plain_proof_*` are exported ISC
API, and an unrelated third party (OpenJarvis) reached the same conclusion and
demonstrated a verified proof on an Apple Silicon machine in 0.119 s. The
`miner_base` oracle remains available as the correctness oracle for every kernel,
under a licence that lets us do anything with it.

**What it costs.** Less than the current plan, not more. The Stratum client and
proof builder were the only things the fork was providing, and both now have
permissive replacements: `ascend_prl` (MIT) has an independently-written Stratum
layer for two pools, and `py-pearl-mining` (ISC) builds and verifies the proof.
The real cost is not legal but architectural, and it is a cost the current plan
was already going to pay late instead of early: the Stratum layer must be written
against a *dialect abstraction*, because `ascend_prl` documents that Pearl pools
genuinely differ — some dictate `m, n, k, rank` and the row/column patterns via
`pearl.set_mining_params`, others let the miner choose. A client hard-coded to
LuckyPool's shape does not port.

**Two things you should change in the plan regardless of the licensing decision.**

1. **Phase 1's target endpoint looks stale.** LuckyPool's own API advertises only
   ports 3360/3361/3362 at a *minimum* difficulty of 2,000,000, and lists no
   `cpu` server. `pearl-cpu-eu1.luckypool.io` still resolves — to the same IP as
   the advertised EU server — but port 3370 appears nowhere in the pool's
   configuration or front-end. Phase 1 is the plan's designated "prove the pipeline
   before writing any Metal" step and it points at an undocumented endpoint. Verify
   it lives, or pick another pool, before anything depends on it.

2. **§2.1's hash tile shape and target endianness are both now in doubt.** An
   independent Metal implementation compares the digest **big-endian**, against
   `Plan.md`'s stated little-endian; and both that implementation and
   `py-pearl-mining`'s observed `PeriodicPattern` output suggest a **4 × 8
   periodic pattern** rather than a contiguous 16 × 16 hash tile. These are exactly
   the silent-rejection failures the plan is built to avoid. Settle both against
   `miner_base` before writing a kernel — it is a morning's work now and a week of
   mystery later.

**What remains unknown.**

- **Whether any patent covers the PoUW construction.** ISC grants no patent
  licence. I did not search patent registers. The risk is not specific to us and
  applies to every Pearl miner including the first-party one, but it is not zero
  and it is not documented.
- **Whether Pearl's Stratum dialect is stable.** There is no first-party
  specification — none. LuckyPool's site names not a single protocol method. The
  only descriptions are implementations, and they disagree enough that
  `ascend_prl` needed an abstraction layer.
- **Whether the Zion Metal kernel is consensus-correct.** It exists, it is MIT,
  and it is structurally right in the ways that matter most (`LROT = 13`,
  cumulative int32 accumulation, keyed BLAKE3 on the pow key). It has zero stars
  and no evidence of an accepted share. Treat it as a second opinion to diff
  against — a genuinely valuable one — not as a base to build on.
- **Whether the milestone still means what it did.** The plan's goal is "one
  accepted share on a pool dashboard" from Apple Silicon. Apple Silicon Pearl
  mining is now public and Apache-2.0; a Metal kernel for this PoW is now public
  and MIT. Neither has demonstrated a pool-accepted share from a hand-written Metal
  kernel, so a genuine first is probably still available — but it is a narrower
  first than the plan assumes, and worth restating honestly in
  [ADR-0002](../adr/0002-backend-a-only.md)'s terms: this is being built because
  its owner wants it built. That was already the honest justification. It is no
  weaker now, and the project no longer has to be private to have it.
