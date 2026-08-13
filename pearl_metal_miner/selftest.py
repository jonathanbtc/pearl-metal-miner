"""The shipped self-test: live differential of every Metal stage against the
reference, on the machine it runs on.

This exists because the failure mode of this domain is silent: a subtly wrong
kernel does not crash, it produces shares the pool refuses with no diagnostic.
We verified an M1 Max; your machine verifies itself here (ADR-0006).

Stages, each exact — a single differing integer fails the run:

  0. wallet     host-side payout codec: key→address against vectors
                differentially generated from `bitcoinutils` 0.8.2 (the
                library upstream's gateway pays addresses with) and
                upstream's own coinbase fixture, 2026-08-10, re-runnable via
                tools/wallet_differential.py; the address validator's reject
                paths; and the local wallet file, if one exists
  1. blake3     GPU keyed BLAKE3 (64-byte blocks) vs the `blake3` library
  2. noise      GPU uniform tables + permutation pairs + noised operands vs
                the NumPy reference (itself pinned to upstream by
                tools/phase05_experiments.py)
  3. pow        GPU digests for EVERY tile vs reference, on random and
                adversarial operands, across two distinct job shapes;
                cumulative int32 tile and transcript checked at EVERY
                R-boundary (the one error class end-to-end testing cannot
                localise)
  4. end-to-end our job-config serialisation against upstream's own (it feeds
                the job key, so a wrong byte silently invalidates every
                share), then a Metal-found win, committed on the host,
                crafted into a PlainProof, accepted by upstream's Rust
                consensus verifier

Exit code 0 with "SELF-TEST PASS" on success; non-zero otherwise.
"""

from __future__ import annotations

import os
import secrets
import sys
import time

import blake3
import numpy as np

from . import reference as ref
from . import wallet
from .metal_capi import HITS_BUF_BYTES, HITS_CAPACITY, JobShape, Metal

CHECKS = {"pass": 0, "fail": 0}


def _check(name: str, ok: bool, detail: str = ""):
    mark = "ok " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS["pass" if ok else "fail"] += 1


SHAPES = [
    # (k, r, rows_pattern, cols_pattern, m, n) — two genuinely different tile
    # shapes so the function-constant machinery is exercised, not decorated.
    (1024, 64, [0, 8, 64, 72], [0, 1, 8, 9, 32, 33, 40, 41], 128, 256),
    (4096, 256, [0, 8],
     [0, 1] + [x for b in range(8, 256, 8) for x in (b, b + 1)], 64, 512),
]


def _job(shape_row) -> tuple[JobShape, int, int]:
    k, r, rows, cols, m, n = shape_row
    return (
        JobShape(k=k, r=r, rows_pattern=ref.Pattern.from_list(rows),
                 cols_pattern=ref.Pattern.from_list(cols)),
        m, n,
    )


# Key→address vectors, generated 2026-08-10 by tools/wallet_differential.py:
# each private key run through an independent BIP-341 implementation
# (`bitcoinutils` 0.8.2 — the library upstream's gateway uses) produced the
# identical witness program, and upstream's gateway decoder returned exactly
# 5120‖program for each address. Keys are BIP-340 even-Y normalised — and
# published here, so these are burned test keys: never mine to them.
WALLET_VECTORS = [
    ("33ece10a66420c4097c8c6f49bac05899b7d8dc8cf503d7202860cdd5b9cc965",
     "prl1pmc2s6zx50hyk2rcjn236jhg84jn9gswexwkwjpm9n5s3vvphx5mslmmuz3"),
    ("86d9a5994ef5db96b94921e36ac9eae692ec732e4c0e3076ccf98e920a60c2ad",
     "prl1pd8vsujrh8ktkum4xkxrg7ug2qr60k3lqarex8ulwx09uqpazjgrq9sz5ap"),
    ("c6bcd7838de549832466c6c86c5291f9368caed486624eb02aa4db87d90543b7",
     "prl1pnr59m0fwyxse08lv7c4eyckd9snyc65709ezwded8ccayhm0pq9s29xq7h"),
    ("6479fab62c587a9c3f1a7756178a8fca3a8189e6d0d6adfb4c86b8f2d1a90d96",
     "prl1p7js9pasfc539vpswjsw5vz9u8t2c00a9p6j4839k77ysvg5qpjnsfs6wle"),
]

# The witness program inside upstream's own coinbase fixture
# (pearl-gateway/tests/test_blockchain_utils.py, scriptPubKey 5120‖program).
UPSTREAM_FIXTURE_PROGRAM = "8635cb51e0601a2f55b17b1ba41b21a511b3753a0bf4610bd52eb1a15d69a281"


def test_wallet():
    for i, (key_hex, addr) in enumerate(WALLET_VECTORS):
        norm, derived = wallet.derive_address(int(key_hex, 16))
        _check(f"key→address differential vector {i}",
               derived == addr and f"{norm:064x}" == key_hex,
               "" if derived == addr else f"derived {derived}")

    fix = bytes.fromhex(UPSTREAM_FIXTURE_PROGRAM)
    _check("upstream coinbase fixture round-trips through our codec",
           wallet.decode_payout_address(wallet.encode_address(fix)) == fix)

    _, fresh = wallet.derive_address(secrets.randbelow(wallet.N - 1) + 1)
    _check("fresh key round-trip (derive → validate → decode)",
           wallet.validate_payout_address(fresh.upper()) == fresh)

    # The validator must reject, loudly, everything the chain cannot pay —
    # a mistyped address that slipped through would mine unclaimable value.
    data5 = [1] + wallet._convertbits(fix, 8, 5)
    pm = wallet._bech32_polymod(wallet._hrp_expand("prl") + data5 + [0] * 6) ^ 1
    bech32_not_m = "prl1" + "".join(
        wallet.CHARSET[d] for d in data5 + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])
    good = WALLET_VECTORS[0][1]
    rejects = [
        ("a one-character typo", good[:-1] + ("q" if good[-1] != "q" else "p")),
        ("a bech32 (not bech32m) encoding", bech32_not_m),
        ("a Bitcoin address", wallet.encode_address(fix, hrp="bc")),
        ("a non-taproot witness version", wallet.encode_address(fix, witver=0)),
        ("a truncated program", wallet.encode_address(fix[:16])),
    ]
    for what, bad_addr in rejects:
        try:
            wallet.validate_payout_address(bad_addr)
            _check(f"validator rejects {what}", False, "was accepted")
        except ValueError:
            _check(f"validator rejects {what}", True)

    found = wallet.find_wallet_file()
    if found is None:
        print("  (no local wallet file — nothing on disk to check)")
        return
    bad = [c for c in wallet.verify_wallet(found) if not c[1]]
    _check(f"local wallet file re-derives from its key ({os.path.basename(found)})",
           not bad, bad[0][0] if bad else "")


def test_blake3(m: Metal, rng: np.random.Generator, cases: int = 1024):
    msgs = rng.integers(0, 256, size=(cases, 64), dtype=np.int64).astype(np.uint8)
    keys = rng.integers(0, 256, size=(cases, 32), dtype=np.int64).astype(np.uint8)
    mb, kb, ob = m.from_numpy(msgs), m.from_numpy(keys), m.alloc(cases * 32)
    m.blake3_64(mb, kb, ob, cases)
    gpu = ob.array(np.uint8, (cases, 32)).copy()
    want = np.stack([
        np.frombuffer(blake3.blake3(msgs[i].tobytes(), key=keys[i].tobytes()).digest(),
                      dtype=np.uint8)
        for i in range(cases)
    ])
    _check(f"blake3: {cases} random 64-byte keyed messages", np.array_equal(gpu, want))
    for b in (mb, kb, ob):
        b.release()


def test_noise(m: Metal, job: JobShape, rows: int, rng: np.random.Generator):
    key = rng.bytes(32)
    k, r = job.k, job.r

    ub = m.alloc(rows * r)
    m.noise_uniform(ref.SEED_LABEL_A, key, ub, rows)
    gpu_uniform = ub.array(np.int8, (rows, r)).copy()
    want_uniform = ref.uniform_noise_rows(ref.SEED_LABEL_A, key, range(rows), r)
    _check(f"noise_uniform: {rows}×{r} table", np.array_equal(gpu_uniform, want_uniform))

    pb = m.alloc(k * 8)
    m.noise_pairs(ref.SEED_LABEL_B, key, pb)
    gpu_pairs = pb.array(np.uint32, (k, 2)).copy()
    want_pairs = ref.permutation_pairs(ref.SEED_LABEL_B, key, k, r)
    _check(f"noise_pairs: {k} (+1,−1) index pairs", np.array_equal(gpu_pairs, want_pairs))
    ok_disjoint = bool(np.all(gpu_pairs[:, 0] != gpu_pairs[:, 1]))
    _check("noise_pairs: +1 and −1 never collide", ok_disjoint)

    base = rng.integers(ref.SIGNAL_MIN, ref.SIGNAL_MAX + 1,
                        size=(rows, k), dtype=np.int64).astype(np.int8)
    bb, ob = m.from_numpy(base), m.alloc(rows * k)
    tb = m.from_numpy(want_uniform)
    pb2 = m.from_numpy(want_pairs.astype(np.uint32))
    m.noise_apply(bb, tb, pb2, ob, rows)
    gpu_noised = ob.array(np.int8, (rows, k)).copy()
    noise = ref.noise_rows(ref.SEED_LABEL_A, key, range(rows), k, r, want_pairs)
    want_noised = (base.astype(np.int32) + noise.astype(np.int32)).astype(np.int8)
    _check(f"noise_apply: {rows}×{k} noised operand", np.array_equal(gpu_noised, want_noised))
    for b in (ub, pb, bb, ob, tb, pb2):
        b.release()


def _reference_digests(an, bnt, job: JobShape, m_dim, n_dim, a_seed):
    rows_b = job.rows_pattern.valid_offsets(m_dim)
    cols_b = job.cols_pattern.valid_offsets(n_dim)
    rows_l = job.rows_pattern.to_list()
    cols_l = job.cols_pattern.to_list()
    out = np.empty((len(rows_b), len(cols_b), 32), dtype=np.uint8)
    for i, tr in enumerate(rows_b):
        a_idx = [tr + p for p in rows_l]
        for j, tc in enumerate(cols_b):
            b_idx = [tc + q for q in cols_l]
            jp = ref.compute_jackpot(an[a_idx], bnt[b_idx], job.r)
            out[i, j] = np.frombuffer(ref.jackpot_digest(jp, a_seed), dtype=np.uint8)
    return rows_b, cols_b, out


def _sweep(m: Metal, job: JobShape, an, bnt, a_seed: bytes, bound: bytes,
           m_dim: int, n_dim: int, debug: bool = False):
    rows_b = np.array(job.rows_pattern.valid_offsets(m_dim), dtype=np.uint32)
    cols_b = np.array(job.cols_pattern.valid_offsets(n_dim), dtype=np.uint32)
    n_tiles = len(rows_b) * len(cols_b)
    anb, bntb = m.from_numpy(an.astype(np.int8)), m.from_numpy(bnt.astype(np.int8))
    rb, cb = m.from_numpy(rows_b), m.from_numpy(cols_b)
    hits = m.alloc(HITS_BUF_BYTES)
    hits.array(np.uint32, (1 + 2 * HITS_CAPACITY,))[...] = 0
    dig = m.alloc(n_tiles * 32)
    bufs = [anb, bntb, rb, cb, hits, dig]
    if debug:
        nchunks = job.k // job.r
        cs = m.alloc(n_tiles * nchunks * job.h * job.w * 4)
        tr = m.alloc(n_tiles * nchunks * 16 * 4)
        m.pow_sweep_debug(anb, bntb, rb, len(rows_b), cb, len(cols_b), a_seed, bound,
                          hits, HITS_CAPACITY, dig, cs, tr)
        bufs += [cs, tr]
        return rows_b, cols_b, hits, dig, cs, tr, bufs
    m.pow_sweep(anb, bntb, rb, len(rows_b), cb, len(cols_b), a_seed, bound,
                hits, HITS_CAPACITY, dig)
    return rows_b, cols_b, hits, dig, None, None, bufs


def test_pow(m: Metal, shape_row, rng: np.random.Generator):
    job, m_dim, n_dim = _job(shape_row)
    m.compile(job)
    a_seed = rng.bytes(32)
    k = job.k

    operand_cases = {
        "random": lambda size: rng.integers(-127, 128, size=size, dtype=np.int64),
        "all +127": lambda size: np.full(size, 127, dtype=np.int64),
        "all −127": lambda size: np.full(size, -127, dtype=np.int64),
        "±127 alternating (max |cumulative|)": lambda size: np.where(
            (np.arange(size[1]) % 2 == 0)[None, :], 127, -127
        ) * np.ones((size[0], 1), dtype=np.int64),
        "all-zero": lambda size: np.zeros(size, dtype=np.int64),
        "mixed extremes": lambda size: rng.choice(
            np.array([-127, -126, -1, 0, 1, 126, 127]), size=size
        ),
    }

    for name, gen in operand_cases.items():
        an = gen((m_dim, k)).astype(np.int8)
        bnt = gen((n_dim, k)).astype(np.int8)
        if name == "all −127":  # mix signs so the product isn't constant-positive
            bnt = (gen((n_dim, k)) * -1).astype(np.int8)
        rows_b, cols_b, hits, dig, _, _, bufs = _sweep(
            m, job, an, bnt, a_seed, b"\xff" * 32, m_dim, n_dim
        )
        gpu = dig.array(np.uint8, (len(rows_b), len(cols_b), 32)).copy()
        _, _, want = _reference_digests(an.astype(np.int32), bnt.astype(np.int32),
                                        job, m_dim, n_dim, a_seed)
        n_tiles = len(rows_b) * len(cols_b)
        _check(f"pow[{job.h}×{job.w},k={k},r={job.r}] digests, {n_tiles} tiles, {name}",
               np.array_equal(gpu, want))
        count = int(hits.array(np.uint32, (1,))[0])
        _check(f"pow …every tile ≤ 0xFF…FF bound reports a hit ({count}/{n_tiles})",
               count == n_tiles)
        for b in bufs:
            b.release()

    # Per-R-boundary: the error class end-to-end testing cannot localise.
    an = rng.integers(-127, 128, size=(m_dim, k), dtype=np.int64).astype(np.int8)
    bnt = rng.integers(-127, 128, size=(n_dim, k), dtype=np.int64).astype(np.int8)
    rows_b, cols_b, hits, dig, cs, trb, bufs = _sweep(
        m, job, an, bnt, a_seed, b"\xff" * 32, m_dim, n_dim, debug=True
    )
    nchunks = k // job.r
    hw = job.h * job.w
    gpu_cs = cs.array(np.int32, (len(rows_b), len(cols_b), nchunks, hw)).copy()
    gpu_tr = trb.array(np.uint32, (len(rows_b), len(cols_b), nchunks, 16)).copy()
    rows_l, cols_l = job.rows_pattern.to_list(), job.cols_pattern.to_list()
    ok_cs = ok_tr = True
    sample = [(0, 0), (len(rows_b) // 2, len(cols_b) // 2), (len(rows_b) - 1, len(cols_b) - 1)]
    for (i, j) in sample:
        a_idx = [int(rows_b[i]) + p for p in rows_l]
        b_idx = [int(cols_b[j]) + q for q in cols_l]
        _, bounds = ref.compute_jackpot(
            an[a_idx].astype(np.int32), bnt[b_idx].astype(np.int32), job.r,
            collect_boundaries=True,
        )
        for t, (csum_want, tr_want) in enumerate(bounds):
            ok_cs &= bool(np.array_equal(gpu_cs[i, j, t], csum_want.flatten()))
            ok_tr &= bool(np.array_equal(gpu_tr[i, j, t],
                                         np.array(tr_want, dtype=np.uint32)))
    _check(f"pow …cumulative int32 tile matches at EVERY R-boundary "
           f"({len(sample)} tiles × {nchunks} boundaries)", ok_cs)
    _check("pow …transcript matches after every fold", ok_tr)
    for b in bufs:
        b.release()


def test_pow_v2(m: Metal, rng: np.random.Generator):
    """The blocked kernel must produce byte-identical digests to the general
    kernel's reference across every tile, plus identical hit sets.

    Note the shape: k=1024 at rank 128 is deliberately BELOW consensus's
    `k >= 16*rank`, so `reference.validate_shape` would refuse it as a mining
    shape — and does, for anything a user types. It is legitimate here because
    this stage compares the GPU against the NumPy reference and nothing else:
    the two must agree on identical inputs whatever the dimensions, and a
    small k keeps the exhaustive per-tile comparison quick. Nothing produced
    here is ever offered to a verifier. Stage 4 is where a real, admissible
    shape goes end-to-end.
    """
    k, r = 1024, 128
    m_dim, n_dim = 256, 256
    job = JobShape(k=k, r=r,
                   rows_pattern=ref.Pattern.from_list([0, 32]),
                   cols_pattern=ref.Pattern.from_list(list(range(64))))
    m.compile(job)
    a_seed = rng.bytes(32)
    for name, gen in {
        "random": lambda size: rng.integers(-127, 128, size=size, dtype=np.int64),
        "±127 alternating": lambda size: np.where(
            (np.arange(size[1]) % 2 == 0)[None, :], 127, -127
        ) * np.ones((size[0], 1), dtype=np.int64),
    }.items():
        an = gen((m_dim, k)).astype(np.int8)
        bnt = gen((n_dim, k)).astype(np.int8)
        anb, bntb = m.from_numpy(an), m.from_numpy(bnt)
        n_bands, n_cb = m_dim // 64, n_dim // 64
        n_tiles = n_bands * 32 * n_cb
        hits = m.alloc(HITS_BUF_BYTES)
        hits.array(np.uint32, (1,))[0] = 0
        dig = m.alloc(n_tiles * 32)
        m.pow_sweep2(anb, bntb, 0, n_bands, n_cb, a_seed, b"\xff" * 32, hits,
                     HITS_CAPACITY, dig)
        gpu = dig.array(np.uint8, (n_bands * 32, n_cb, 32)).copy()
        _, _, want = _reference_digests(an.astype(np.int32), bnt.astype(np.int32),
                                        job, m_dim, n_dim, a_seed)
        _check(f"pow_v2[2×64 blocked] digests, {n_tiles} tiles, {name}",
               np.array_equal(gpu, want))
        count = int(hits.array(np.uint32, (1,))[0])
        _check(f"pow_v2 …hit count at ≤0xFF…FF bound ({count}/{n_tiles})",
               count == n_tiles)
        for b in (anb, bntb, hits, dig):
            b.release()


def test_end_to_end(m: Metal, rng: np.random.Generator):
    """Full pipeline with GPU noise + GPU sweep; the win is crafted into a
    PlainProof and judged by upstream's Rust verifier — the consensus oracle."""
    import pearl_mining as pm

    k, r, rows, cols, m_dim, n_dim = SHAPES[0]
    job, _, _ = _job(SHAPES[0])
    m.compile(job)

    header_fields = dict(version=0x20000000, prev_block=rng.bytes(32),
                         merkle_root=rng.bytes(32), timestamp=1723200000,
                         nbits=0x207FFFFF)
    pm_header = pm.IncompleteBlockHeader(
        header_fields["version"], header_fields["prev_block"],
        header_fields["merkle_root"], header_fields["timestamp"], header_fields["nbits"])
    # The job key is BLAKE3(header ‖ config), so our config serialisation is a
    # consensus input: a wrong byte here commits the grid to the wrong key and
    # every share is refused with no diagnostic. Check it against upstream's
    # own serialiser rather than inferring it from the end-to-end verify.
    _check("config serialisation == upstream MiningConfiguration.to_bytes()",
           bytes(pm.MiningConfiguration(
               k, r, pm.MMAType.Int7xInt7ToInt32,
               pm.PeriodicPattern.from_list(rows),
               pm.PeriodicPattern.from_list(cols)).to_bytes())
           == ref.config_to_bytes(k, r, job.rows_pattern, job.cols_pattern))

    A = rng.integers(ref.SIGNAL_MIN, ref.SIGNAL_MAX + 1, size=(m_dim, k),
                     dtype=np.int64).astype(np.int8)
    Bt = rng.integers(ref.SIGNAL_MIN, ref.SIGNAL_MAX + 1, size=(n_dim, k),
                      dtype=np.int64).astype(np.int8)

    job_key = ref.compute_job_key(
        ref.header_to_bytes(**header_fields),
        ref.config_to_bytes(k, r, job.rows_pattern, job.cols_pattern))
    a_pad, bt_pad = ref.pad_to_chunk_boundary(A.tobytes()), ref.pad_to_chunk_boundary(Bt.tobytes())
    tree_a = pm.MerkleTree(data=a_pad, key=job_key)
    tree_bt = pm.MerkleTree(data=bt_pad, key=job_key)
    b_seed, a_seed = ref.compute_commitment(job_key, a_pad, bt_pad)

    # GPU noise end to end: tables, pairs, apply.
    ua, pa = m.alloc(m_dim * r), m.alloc(k * 8)
    ub, pb = m.alloc(n_dim * r), m.alloc(k * 8)
    m.noise_uniform(ref.SEED_LABEL_A, a_seed, ua, m_dim)
    m.noise_pairs(ref.SEED_LABEL_A, a_seed, pa)
    m.noise_uniform(ref.SEED_LABEL_B, b_seed, ub, n_dim)
    m.noise_pairs(ref.SEED_LABEL_B, b_seed, pb)
    ab, anb = m.from_numpy(A), m.alloc(m_dim * k)
    btb, bntb = m.from_numpy(Bt), m.alloc(n_dim * k)
    m.noise_apply(ab, ua, pa, anb, m_dim)
    m.noise_apply(btb, ub, pb, bntb, n_dim)
    an = anb.array(np.int8, (m_dim, k)).copy()
    bnt = bntb.array(np.int8, (n_dim, k)).copy()

    noise_a, noise_bt = ref.noise_for_indices(k, r, b_seed, a_seed, range(m_dim), range(n_dim))
    _check("e2e: GPU noised operands == reference",
           np.array_equal(an, (A.astype(np.int32) + noise_a).astype(np.int8))
           and np.array_equal(bnt, (Bt.astype(np.int32) + noise_bt).astype(np.int8)))

    # Sweep with an easy-but-not-trivial bound: median tile digest value, so
    # roughly half the tiles win — exercises the comparison in both directions.
    _, _, digs = _reference_digests(an.astype(np.int32), bnt.astype(np.int32),
                                    job, m_dim, n_dim, a_seed)
    values = sorted(int.from_bytes(digs[i, j].tobytes(), "little")
                    for i in range(digs.shape[0]) for j in range(digs.shape[1]))
    bound_int = values[len(values) // 2]
    bound = bound_int.to_bytes(32, "little")
    rows_b, cols_b, hits, dig, _, _, bufs = _sweep(m, job, an, bnt, a_seed, bound,
                                                   m_dim, n_dim)
    count = int(hits.array(np.uint32, (1,))[0])
    want_wins = sum(1 for v in values if v <= bound_int)
    _check(f"e2e: GPU hit count equals reference win count at median bound "
           f"({count} hits / {len(values)} tiles)", count == want_wins)

    pairs = hits.array(np.uint32, (1 + 2 * HITS_CAPACITY,))[1:1 + 2 * count].reshape(count, 2)
    tile_vals = {}
    for i, tr_b in enumerate(rows_b):
        for j, tc_b in enumerate(cols_b):
            tile_vals[(int(tr_b), int(tc_b))] = int.from_bytes(digs[i, j].tobytes(), "little")
    best = min(map(tuple, pairs.tolist()), key=lambda t: tile_vals[t])

    rows_list = job.rows_pattern.to_list()
    cols_list = job.cols_pattern.to_list()
    a_idx = [best[0] + p for p in rows_list]
    b_idx = [best[1] + q for q in cols_list]
    la = pm.MerkleTree.compute_leaf_indices_from_rows(a_idx, (m_dim, k))
    lb = pm.MerkleTree.compute_leaf_indices_from_rows(b_idx, (n_dim, k))
    proof = pm.PlainProof(
        m_dim, n_dim, k, r,
        pm.MatrixMerkleProof(tree_a.get_multileaf_proof(la), a_idx),
        pm.MatrixMerkleProof(tree_bt.get_multileaf_proof(lb), b_idx), None)

    # Verify at a share-difficulty-style override derived from the tile's own
    # value — an override-free verify would check block difficulty (theatre).
    factor = ref.difficulty_factor(job.h, job.w, k, r)
    need = -(-tile_vals[best] // factor)
    nb = ref.target_to_nbits(need)
    while ref.nbits_to_target(nb) * factor < tile_vals[best]:
        mant, size = (nb & 0xFFFFFF) + 1, nb >> 24
        if mant & 0x800000:
            mant, size = mant >> 8, size + 1
        nb = (size << 24) | mant
    ok, msg = pm.verify_plain_proof_v1(pm_header, proof, nbits_override=nb)
    _check("e2e: Metal-found win → PlainProof → upstream Rust verifier accepts "
           "at share-difficulty override", ok, msg)
    for b in bufs + [ua, pa, ub, pb, ab, anb, btb, bntb]:
        b.release()


def run(seed: int = 0) -> int:
    t0 = time.time()
    print("pearl-metal-miner self-test")
    print("Every check is an exact integer comparison; any mismatch fails the run.")
    rng = np.random.default_rng(seed)
    print("stage 0: payout wallet and address codec (host)")
    test_wallet()
    try:
        mtl = Metal()
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL] Metal context: {e}")
        return 1
    info = mtl.device_info()
    print(f"device: {info['name']}  (threadgroup mem {info['max_threadgroup_memory']} B, "
          f"max threads {info['max_threads_per_threadgroup']})")

    job0, _, _ = _job(SHAPES[0])
    mtl.compile(job0)

    print("stage 1: keyed BLAKE3")
    test_blake3(mtl, rng)
    print("stage 2: noise generation")
    test_noise(mtl, job0, rows=128, rng=rng)
    print("stage 3: the PoW sweep, two job shapes")
    for shape_row in SHAPES:
        test_pow(mtl, shape_row, rng)
    print("stage 3b: blocked fast-path kernel (pow_sweep_v2)")
    test_pow_v2(mtl, rng)
    print("stage 4: end-to-end against upstream's consensus verifier")
    test_end_to_end(mtl, rng)

    dt = time.time() - t0
    print()
    if CHECKS["fail"]:
        print(f"SELF-TEST FAIL — {CHECKS['fail']} of {CHECKS['pass'] + CHECKS['fail']} "
              f"checks failed ({dt:.1f}s). Do NOT mine with this build.")
        return 1
    print(f"SELF-TEST PASS — {CHECKS['pass']} checks, all exact ({dt:.1f}s).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
