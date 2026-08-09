"""Phase 0.5 — settle the specification against the oracle, by running it.

Each experiment prints a verdict line.  Exit code is non-zero on any failure.

  E1  Pattern & config serialisation matches pearl_mining byte-for-byte
  E2  Upstream mine() produces a proof verify_plain_proof_v1/v2 accept
  E3  OUR full pipeline (numpy) crafts a PlainProof upstream's verifier accepts
  E4  Flip-point: the verifier's accept/reject boundary lands exactly where our
      little-endian digest value says it must (pins digest + bound formula)
  E5  Our noise bytes match miner_base's torch NoiseGenerator (independent path)
  E6  Non-partition tile base is accepted by the verifier (search convention,
      not consensus) — documented, not built upon
"""

import sys
import time

sys.path.insert(0, ".")

import numpy as np
import blake3
import pearl_mining as pm

from pearl_metal_miner import reference as ref

FAILURES = []


def check(name: str, ok: bool, detail: str = ""):
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


# Small but production-shaped test job.
M, N, K, RANK = 128, 256, 1024, 64
ROWS = [0, 8, 64, 72]                       # h = 4
COLS = [0, 1, 8, 9, 32, 33, 40, 41]         # w = 8  → h*w = 32 (min legal)
H, W = len(ROWS), len(COLS)

rows_pat = ref.Pattern.from_list(ROWS)
cols_pat = ref.Pattern.from_list(COLS)

pm_rows = pm.PeriodicPattern.from_list(ROWS)
pm_cols = pm.PeriodicPattern.from_list(COLS)
pm_config = pm.MiningConfiguration(K, RANK, pm.MMAType.Int7xInt7ToInt32, pm_rows, pm_cols)

HEADER_FIELDS = dict(
    version=0x20000000,
    prev_block=bytes(range(32)),
    merkle_root=bytes(range(32, 64)),
    timestamp=0x66666666,
    nbits=0x207FFFFF,  # easiest legal target
)
pm_header = pm.IncompleteBlockHeader(
    HEADER_FIELDS["version"], HEADER_FIELDS["prev_block"], HEADER_FIELDS["merkle_root"],
    HEADER_FIELDS["timestamp"], HEADER_FIELDS["nbits"],
)

# ── E1: serialisation ────────────────────────────────────────────────────────
check("E1a rows_pattern.to_bytes", rows_pat.to_bytes() == bytes(pm_rows.to_bytes()))
check("E1b cols_pattern.to_bytes", cols_pat.to_bytes() == bytes(pm_cols.to_bytes()))
prod_cols = [0, 1] + [x for base in range(8, 256, 8) for x in (base, base + 1)]
check(
    "E1c production cols pattern (64 idx, period 256)",
    ref.Pattern.from_list(prod_cols).to_bytes() == bytes(pm.PeriodicPattern.from_list(prod_cols).to_bytes())
    and ref.Pattern.from_list(prod_cols).period() == 256,
)
my_config = ref.config_to_bytes(K, RANK, rows_pat, cols_pat)
check("E1d MiningConfiguration.to_bytes (52 B)", my_config == bytes(pm_config.to_bytes()))
my_header = ref.header_to_bytes(**HEADER_FIELDS)
check("E1e IncompleteBlockHeader.to_bytes (76 B)", my_header == bytes(pm_header.to_bytes()))
check(
    "E1f pattern round-trips & partition maths",
    rows_pat.to_list() == [int(x) for x in pm_rows.to_list()]
    and rows_pat.period() == pm_rows.period == 128
    and [o for o in range(K) if pm_rows.offset_is_valid(o)][:5] == rows_pat.valid_offsets(K)[:5],
)

# ── E2: upstream mine + verify ───────────────────────────────────────────────
t0 = time.time()
proof = pm.mine(M, N, K, pm_header, pm_config)
t_mine = time.time() - t0
ok1, msg1 = pm.verify_plain_proof_v1(pm_header, proof)
ok2, msg2 = pm.verify_plain_proof_v2(pm_header, proof)
check("E2a upstream mine() → verify_plain_proof_v1", ok1, f"{t_mine:.3f}s, {msg1}")
check("E2b same proof under v2 verifier", ok2, msg2)
check(
    "E2c proof shape: opened rows = pattern + base",
    len(proof.a.row_indices) == H and len(proof.bt.row_indices) == W
    and sorted(np.diff(proof.a.row_indices).tolist()) == sorted(np.diff(ROWS).tolist()),
    f"a rows {proof.a.row_indices} bt cols {proof.bt.row_indices}",
)

# ── E3: OUR pipeline end-to-end, accepted by upstream's verifier ─────────────
rng = np.random.default_rng(7)
A = rng.integers(ref.SIGNAL_MIN, ref.SIGNAL_MAX + 1, size=(M, K), dtype=np.int64).astype(np.int8)
B = rng.integers(ref.SIGNAL_MIN, ref.SIGNAL_MAX + 1, size=(K, N), dtype=np.int64).astype(np.int8)
Bt = np.ascontiguousarray(B.T)

job_key = ref.compute_job_key(my_header, my_config)
a_padded = ref.pad_to_chunk_boundary(A.tobytes())
bt_padded = ref.pad_to_chunk_boundary(Bt.tobytes())

tree_a = pm.MerkleTree(data=a_padded, key=job_key)
tree_bt = pm.MerkleTree(data=bt_padded, key=job_key)
check(
    "E3a Merkle root == keyed blake3 digest of padded bytes",
    bytes(tree_a.root) == blake3.blake3(a_padded, key=job_key).digest(),
)

b_seed, a_seed = ref.compute_commitment(job_key, a_padded, bt_padded)
check(
    "E3b commitment chain vs roots",
    a_seed == blake3.blake3(blake3.blake3(job_key + bytes(tree_bt.root)).digest() + bytes(tree_a.root)).digest(),
)

# noise for the entire (small) grid, then sweep every partition tile
pairs_a = ref.permutation_pairs(ref.SEED_LABEL_A, a_seed, K, RANK)
pairs_b = ref.permutation_pairs(ref.SEED_LABEL_B, b_seed, K, RANK)
noise_a = ref.noise_rows(ref.SEED_LABEL_A, a_seed, range(M), K, RANK, pairs_a)
noise_bt = ref.noise_rows(ref.SEED_LABEL_B, b_seed, range(N), K, RANK, pairs_b)
An = A.astype(np.int32) + noise_a.astype(np.int32)
Bnt = Bt.astype(np.int32) + noise_bt.astype(np.int32)
check(
    "E3c noised operand range ⊆ [-127, 127]",
    int(An.min()) >= -127 and int(An.max()) <= 127 and int(Bnt.min()) >= -127 and int(Bnt.max()) <= 127,
    f"A′∈[{An.min()},{An.max()}] B′ᵗ∈[{Bnt.min()},{Bnt.max()}]",
)

best = None
for tr in rows_pat.valid_offsets(M):
    a_idx = [tr + p for p in ROWS]
    for tc in cols_pat.valid_offsets(N):
        b_idx = [tc + q for q in COLS]
        jp = ref.compute_jackpot(An[a_idx], Bnt[b_idx], RANK)
        hv = ref.jackpot_value(ref.jackpot_digest(jp, a_seed))
        if best is None or hv < best[0]:
            best = (hv, tr, tc, a_idx, b_idx)
hv, tr, tc, a_idx, b_idx = best
n_tiles = len(rows_pat.valid_offsets(M)) * len(cols_pat.valid_offsets(N))
print(f"   swept {n_tiles} tiles; best digest value ≈ 2^{hv.bit_length() - 1} at base ({tr},{tc})")


def craft_plain_proof(a_indices, b_indices):
    la = pm.MerkleTree.compute_leaf_indices_from_rows(list(a_indices), (M, K))
    lb = pm.MerkleTree.compute_leaf_indices_from_rows(list(b_indices), (N, K))
    mp_a = pm.MatrixMerkleProof(tree_a.get_multileaf_proof(la), list(a_indices))
    mp_b = pm.MatrixMerkleProof(tree_bt.get_multileaf_proof(lb), list(b_indices))
    return pm.PlainProof(M, N, K, RANK, mp_a, mp_b, None)


ours = craft_plain_proof(a_idx, b_idx)
ok3, msg3 = pm.verify_plain_proof_v1(pm_header, ours)
check("E3d OUR crafted PlainProof accepted by upstream v1 verifier", ok3, msg3)
ok3b, _ = pm.verify_plain_proof_v2(pm_header, ours)
check("E3e …and by the v2 verifier", ok3b)

# ── E4: flip-point — pins digest bytes, endianness and the bound formula ─────
factor = ref.difficulty_factor(H, W, K, RANK)
need = -(-hv // factor)  # ceil(hv / factor): smallest target that accepts
nb = ref.target_to_nbits(need)
while ref.nbits_to_target(nb) * factor < hv:  # floor-rounding may undershoot
    mant, size = (nb & 0xFFFFFF) + 1, nb >> 24
    if mant & 0x800000:
        mant, size = mant >> 8, size + 1
    nb = (size << 24) | mant
acc_ok, _ = pm.verify_plain_proof_v1(pm_header, ours, nbits_override=nb)

rej = ref.target_to_nbits(need - 1)  # floor(<need) → bound strictly below hv
rej_ok, rej_msg = pm.verify_plain_proof_v1(pm_header, ours, nbits_override=rej)
check(
    "E4 accept/reject flips exactly at our computed digest value",
    acc_ok and not rej_ok,
    f"accept@{nb:#010x} reject@{rej:#010x} ({rej_msg.splitlines()[0][:60]})",
)

# ── E5: noise vs miner_base torch implementation (independent same-spec path) ─
try:
    import types

    stub = types.ModuleType("miner_utils")
    stub.get_logger = lambda name: __import__("logging").getLogger(name)
    sys.modules.setdefault("miner_utils", stub)
    sys.path.insert(0, "pearl/miner/miner-base/src")
    from miner_base.noise_generation import NoiseGenerator  # noqa: E402

    gen = NoiseGenerator(noise_rank=RANK, noise_range=ref.NOISE_RANGE)
    A_L, A_R, B_L, B_R = gen.generate_noise_metrices(a_seed, b_seed, M, K, N)
    torch_noise_a = (A_L.to_dense().numpy().astype(np.int32) @ A_R.numpy().astype(np.int32))
    torch_noise_bt = (B_R.numpy().astype(np.int32).T @ B_L.numpy().astype(np.int32).T)
    check("E5a noise_a == miner_base (torch)", np.array_equal(torch_noise_a, noise_a.astype(np.int32)))
    check("E5b noise_bt == miner_base (torch)", np.array_equal(torch_noise_bt, noise_bt.astype(np.int32)))
except Exception as e:  # noqa: BLE001
    check("E5 miner_base torch cross-check", False, f"{type(e).__name__}: {e}")

# ── E6: consensus REJECTS non-partition bases (list_to_pattern enforces
# offset_is_valid) — the partition IS the search space, by consensus ──────────
odd = craft_plain_proof([9 + p for p in ROWS], b_idx)  # base 9: NOT offset_is_valid
ok6, msg6 = pm.verify_plain_proof_v1(pm_header, odd)
check("E6 non-partition tile base rejected (partition is consensus)", not ok6, msg6.splitlines()[0][:70])

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    sys.exit(1)
print("Phase 0.5: every check green.")
