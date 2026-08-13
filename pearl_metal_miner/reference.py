"""NumPy reference implementation of Pearl's proof-of-useful-work.

Written from the ISC upstream sources in `pearl-research-labs/pearl` (see
PINNED_PEARL_COMMIT.txt), primarily:

  zk-pow/src/circuit/pearl_noise.rs        noise generation
  zk-pow/src/circuit/chip/jackpot/helper.rs  the jackpot fold (consensus)
  zk-pow/src/ffi/mine.rs                   the reference miner
  zk-pow/src/api/proof_utils.rs            serialisation, patterns, nbits
  zk-pow/src/api/sanity_checks.rs          difficulty bounds

This module is the comparator for the Metal kernels: every GPU stage is
differentially tested against these functions, and these functions are
themselves pinned to upstream by `selftest.py`, which crafts a PlainProof from
this pipeline and has upstream's Rust verifier accept it.

Nothing here tolerates approximation: a single differing integer produces a
silently rejected share.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import blake3
import numpy as np

# ── Consensus constants ──────────────────────────────────────────────────────
# zk-pow/src/circuit/pearl_program.rs
JACKPOT_SIZE = 16  # transcript slots (u32)
LROT_PER_TILE = 13  # rotate-left amount per fold
TILE_D = 16  # rank must divide by this
TILE_H = 2  # pattern sizes must divide by this

# zk-pow/src/circuit/pearl_noise.rs — fixed, NOT configurable
NOISE_RANGE = 128
IDXS_PER_COL = 2
UNIFORM_NOISE_RANGE = NOISE_RANGE // IDXS_PER_COL  # 64
ZERO_POINT_TRANSLATION = UNIFORM_NOISE_RANGE // 2  # 32
RANGE_MASK = UNIFORM_NOISE_RANGE - 1  # 0x3F

SEED_LABEL_A = b"A_tensor" + b"\x00" * 24
SEED_LABEL_B = b"B_tensor" + b"\x00" * 24

BLAKE3_DIGEST_SIZE = 32
CHUNK_LEN = 1024  # BLAKE3 chunk == Merkle leaf size

# zk-pow/src/api/sanity_checks.rs
PENALTY_BASE_RANK = 128

# zk-pow/src/circuit/chip/blake3/program.rs — bytes per dword; the dot-product
# length must be a multiple of it.
DWORD_SIZE = 8

# zk-pow/src/ffi/mine.rs — committed matrix element range, inclusive.
# The verifier enforces exactly this range on opened strips (IRANGE7P1).
SIGNAL_MIN = -64
SIGNAL_MAX = 64


# ── Keyed BLAKE3 primitives (all single 64-byte-block messages) ──────────────

def noise_block_digest(index: int, seed32: bytes, key32: bytes, prepend_slot: int) -> bytes:
    """pearl_noise.rs::get_random_hash — keyed BLAKE3 of a 64-byte message:
    eight i32 slots (slot `prepend_slot` holds 1+index, little-endian) then the
    32-byte seed label."""
    msg = bytearray(64)
    msg[prepend_slot * 4 : prepend_slot * 4 + 4] = struct.pack("<i", 1 + index)
    msg[32:64] = seed32
    return blake3.blake3(bytes(msg), key=key32).digest()


def jackpot_digest(jackpot: np.ndarray, pow_key: bytes) -> bytes:
    """proof_utils.rs::compute_jackpot_hash — keyed BLAKE3 of the 16 u32
    transcript words serialised little-endian (64 bytes)."""
    assert jackpot.dtype == np.uint32 and jackpot.shape == (JACKPOT_SIZE,)
    return blake3.blake3(jackpot.astype("<u4").tobytes(), key=pow_key).digest()


# ── Noise generation ─────────────────────────────────────────────────────────

def uniform_noise_rows(seed32: bytes, key32: bytes, row_indices, rank: int) -> np.ndarray:
    """pearl_noise.rs::generate_uniform_random_matrix.

    Row `i` of the full matrix occupies byte offsets [i*rank, (i+1)*rank) of a
    keyed digest stream; byte -> (byte & 0x3F) - 32. Returns int8 [len(rows), rank].
    """
    out = np.empty((len(row_indices), rank), dtype=np.int8)
    for r, row_idx in enumerate(row_indices):
        start = row_idx * rank
        first_block = start // BLAKE3_DIGEST_SIZE
        last_block = -(-(start + rank) // BLAKE3_DIGEST_SIZE)  # ceil div
        stream = b"".join(
            noise_block_digest(b, seed32, key32, 0) for b in range(first_block, last_block)
        )
        lo = start - first_block * BLAKE3_DIGEST_SIZE
        row_bytes = np.frombuffer(stream, dtype=np.uint8)[lo : lo + rank]
        out[r] = (row_bytes & RANGE_MASK).astype(np.int16) - ZERO_POINT_TRANSLATION
    return out


def permutation_pairs(seed32: bytes, key32: bytes, k: int, rank: int) -> np.ndarray:
    """pearl_noise.rs::generate_permutation_matrix.

    For each k-position: draw u32 (little-endian) from the keyed digest stream
    (8 per digest); first = u & (rank-1); second = first ^ (1 + mulhi(rank-1, u)).
    Returns uint32 [k, 2] of (+1 index, -1 index).
    """
    n_digests = -(-k // 8)
    stream = b"".join(noise_block_digest(i, seed32, key32, 1) for i in range(n_digests))
    words = np.frombuffer(stream, dtype="<u4")[:k].astype(np.uint64)
    first = (words & np.uint64(rank - 1)).astype(np.uint32)
    mulhi = ((np.uint64(rank - 1) * words) >> np.uint64(32)).astype(np.uint32)
    second = first ^ (np.uint32(1) + mulhi)
    return np.stack([first, second], axis=1)


def noise_rows(
    uniform_seed32: bytes,
    noise_seed: bytes,
    row_indices,
    k: int,
    rank: int,
    pairs: np.ndarray | None = None,
) -> np.ndarray:
    """Noise values for the given rows of A (or columns of B via Bᵀ rows):
    noise[r, l] = EAL[r, first(l)] - EAL[r, second(l)].  int8 [rows, k]."""
    if pairs is None:
        pairs = permutation_pairs(uniform_seed32, noise_seed, k, rank)
    eal = uniform_noise_rows(uniform_seed32, noise_seed, row_indices, rank)
    diff = eal[:, pairs[:, 0]].astype(np.int16) - eal[:, pairs[:, 1]].astype(np.int16)
    return diff.astype(np.int8)  # range [-63, 63], lossless


def noise_for_indices(k: int, rank: int, b_noise_seed: bytes, a_noise_seed: bytes,
                      a_row_indices, b_col_indices) -> tuple[np.ndarray, np.ndarray]:
    """pearl_noise.rs::compute_noise_for_indices — (noise_a rows, noise_bt rows)."""
    noise_a = noise_rows(SEED_LABEL_A, a_noise_seed, a_row_indices, k, rank)
    noise_bt = noise_rows(SEED_LABEL_B, b_noise_seed, b_col_indices, k, rank)
    return noise_a, noise_bt


# ── The jackpot fold (consensus hot loop) ────────────────────────────────────

def rotl32(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def compute_jackpot(an: np.ndarray, bnt: np.ndarray, rank: int,
                    collect_boundaries: bool = False):
    """jackpot/helper.rs::compute_jackpot.

    an:  int32 [h, k]  noised A rows       (A + noise, NOT clamped)
    bnt: int32 [w, k]  noised Bᵀ rows

    Folds the XOR of the *cumulative* int32 tile into transcript slot
    (chunk_index % 16) with rotate-left 13, at every full rank-chunk.
    Returns uint32 [16]; with collect_boundaries=True also returns the
    cumulative tile and transcript after every fold (for differential tests).
    """
    k = an.shape[1]
    csum = np.zeros((an.shape[0], bnt.shape[0]), dtype=np.int64)
    jackpot = [0] * JACKPOT_SIZE
    boundaries = []
    n_chunks = k // rank
    for t in range(n_chunks):
        lo, hi = t * rank, (t + 1) * rank
        csum += an[:, lo:hi].astype(np.int64) @ bnt[:, lo:hi].astype(np.int64).T
        tile_u32 = (csum & 0xFFFFFFFF).astype(np.uint32)  # int32 two's complement view
        xored = int(np.bitwise_xor.reduce(tile_u32, axis=None))
        slot = t % JACKPOT_SIZE
        jackpot[slot] = rotl32(jackpot[slot], LROT_PER_TILE) ^ xored
        if collect_boundaries:
            boundaries.append((tile_u32.view(np.int32).copy(), list(jackpot)))
    out = np.array(jackpot, dtype=np.uint32)
    if collect_boundaries:
        return out, boundaries
    return out


# ── Periodic patterns ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Pattern:
    """proof_utils.rs::PeriodicPattern — a 3-level arithmetic progression."""

    shape: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]

    @classmethod
    def from_list(cls, pattern: list[int]) -> "Pattern":
        # ValueError, not assert: this is user input (--rows/--cols), and
        # `python -O` would strip an assert and let a malformed pattern through.
        if not (pattern and pattern[0] == 0 and all(
                a < b for a, b in zip(pattern, pattern[1:]))):
            raise ValueError("pattern must be sorted, deduplicated, and start "
                             f"at 0 (got {pattern})")
        p = list(pattern)
        shape_vec: list[tuple[int, int]] = []
        while len(p) > 1:
            for period in range(1, len(p)):
                if len(p) % period == 0:
                    s = p[period]
                    if all(p[i] + s == p[i + period] for i in range(len(p) - period)):
                        shape_vec.append((s, len(p) // period))
                        p = p[:period]
                        break
            else:
                raise ValueError("pattern is not periodic")
        shape_vec.reverse()
        period = shape_vec[-1][0] * shape_vec[-1][1] if shape_vec else 1
        while len(shape_vec) < 3:
            shape_vec.append((period, 1))
        return cls(tuple(shape_vec))  # type: ignore[arg-type]

    def to_list(self) -> list[int]:
        res = [0]
        for stride, length in self.shape:
            res = [r + i * stride for i in range(length) for r in res]
        return res

    def to_bytes(self) -> bytes:
        data = bytearray(6)
        min_stride = 1
        for i, (stride, length) in enumerate(self.shape):
            factor = stride // min_stride
            data[2 * i] = factor - 1
            data[2 * i + 1] = length - 1
            min_stride = stride * length
        return bytes(data)

    def offset_is_valid(self, offset: int) -> bool:
        for stride, length in reversed(self.shape):
            offset %= stride * length
            if offset >= stride:
                return False
        return True

    def period(self) -> int:
        stride, length = self.shape[-1]
        return stride * length

    def size(self) -> int:
        return self.shape[0][1] * self.shape[1][1] * self.shape[2][1]

    def max(self) -> int:
        return max(self.to_list())

    def valid_offsets(self, dim: int) -> list[int]:
        """ffi/mine.rs::threads_partition — the tile bases the reference miner
        sweeps. Tiles at these bases partition [0, dim)."""
        if dim <= 0 or dim % self.period() != 0:
            raise ValueError(f"dimension {dim} must be a positive multiple of "
                             f"the pattern period {self.period()}")
        return [o for o in range(dim) if self.offset_is_valid(o)]


# ── Job serialisation and commitment ─────────────────────────────────────────

def header_to_bytes(version: int, prev_block: bytes, merkle_root: bytes,
                    timestamp: int, nbits: int) -> bytes:
    """proof_utils.rs::IncompleteBlockHeader::to_bytes — 76 bytes; the two hash
    fields are byte-reversed on the wire."""
    return (
        struct.pack("<I", version)
        + prev_block[::-1]
        + merkle_root[::-1]
        + struct.pack("<I", timestamp)
        + struct.pack("<I", nbits)
    )


def config_to_bytes(k: int, rank: int, rows_pattern: Pattern, cols_pattern: Pattern,
                    moe_e: int = 0, moe_top_k: int = 0) -> bytes:
    """proof_utils.rs::MiningConfiguration::to_bytes — 52 bytes.
    mma_type is always 0 (Int7xInt7ToInt32)."""
    trailer = struct.pack("<HH", moe_e, moe_top_k) + b"\x00" * 28
    return (
        struct.pack("<IHH", k, rank, 0)
        + rows_pattern.to_bytes()
        + cols_pattern.to_bytes()
        + trailer
    )


def pad_to_chunk_boundary(data: bytes) -> bytes:
    if len(data) % CHUNK_LEN == 0 and len(data) > 0:
        return data
    pad = (-len(data)) % CHUNK_LEN
    return data + b"\x00" * pad


def compute_job_key(header_bytes: bytes, config_bytes: bytes) -> bytes:
    """ffi/mine.rs::compute_job_key — UNkeyed BLAKE3 of header ‖ config (128 B)."""
    return blake3.blake3(header_bytes + config_bytes).digest()


def compute_commitment(job_key: bytes, a_row_major_padded: bytes,
                       bt_row_major_padded: bytes) -> tuple[bytes, bytes]:
    """ffi/mine.rs::compute_commitment_hash — (b_noise_seed, a_noise_seed).

    hash_a/hash_b are keyed BLAKE3 of the chunk-padded matrix bytes; they equal
    the pearl-blake3 Merkle roots by construction.
    a_noise_seed is the pow key.
    """
    hash_a = blake3.blake3(a_row_major_padded, key=job_key).digest()
    hash_b = blake3.blake3(bt_row_major_padded, key=job_key).digest()
    b_noise_seed = blake3.blake3(job_key + hash_b).digest()
    a_noise_seed = blake3.blake3(b_noise_seed + hash_a).digest()
    return b_noise_seed, a_noise_seed


# ── Difficulty ───────────────────────────────────────────────────────────────

def nbits_to_target(nbits: int) -> int:
    """proof_utils.rs::nbits_to_difficulty — Bitcoin compact encoding."""
    exponent = nbits >> 24
    mantissa = nbits & 0x00FFFFFF
    if mantissa == 0 or exponent == 0 or mantissa & 0x00800000:
        return 0
    if exponent <= 3:
        return mantissa >> (8 * (3 - exponent))
    return mantissa << (8 * (exponent - 3))


def target_to_nbits(target: int) -> int:
    """Largest-mantissa compact encoding with value <= target (floor)."""
    if target <= 0:
        return 0
    size = (target.bit_length() + 7) // 8
    if size <= 3:
        mantissa = target << (8 * (3 - size))
    else:
        mantissa = target >> (8 * (size - 3))
    if mantissa & 0x00800000:
        mantissa >>= 8
        size += 1
    return (size << 24) | mantissa


def dot_product_length(k: int, rank: int) -> int:
    return k - k % rank


def difficulty_factor(h: int, w: int, k: int, rank: int) -> int:
    """sanity_checks.rs::difficulty_adjustment_factor — the UNPENALIZED factor
    the plain-proof verifier uses: bound = target * h * w * dot_product_length."""
    return h * w * dot_product_length(k, rank)


def penalized_factor(h: int, w: int, k: int, rank: int) -> int:
    """sanity_checks.rs::penalized_adjustment_factor — the rank-penalty variant
    (equal to the above at rank 128; halves the bound at rank 256, etc.)."""
    return h * w * (dot_product_length(k, rank) // rank) * PENALTY_BASE_RANK


def jackpot_value(digest: bytes) -> int:
    """The digest as the integer compared against the bound: LITTLE-endian."""
    return int.from_bytes(digest, "little")


# ── Job-shape admissibility ──────────────────────────────────────────────────

def validate_shape(m: int, n: int, k: int, rank: int,
                   rows_pattern: Pattern, cols_pattern: Pattern) -> None:
    """sanity_checks.rs::public_params_sanity_check, restated for the shape a
    user can set from the command line. Raises ValueError naming the rule.

    This is the silent failure mode at its most reachable: consensus refuses
    any proof outside these bounds, and noise generation only works at all for
    power-of-two ranks (`u & (rank-1)` is a mask), so a single mistyped
    `--rank` sweeps the GPU for days and can never produce a share the chain
    would take — with nothing on screen to say so. Checked once, at startup.
    """
    h, w = rows_pattern.size(), cols_pattern.size()
    if rank < 32 or rank > 1024 or (rank & (rank - 1)) != 0:
        raise ValueError(f"--rank must be a power of two from 32 to 1024 "
                         f"(got {rank}); the default 128 is the only one "
                         f"without a difficulty penalty")
    if k % 64 or k < 1024 or k > 1 << 16:
        raise ValueError(f"--k must be a multiple of 64 between 1024 and 65536 "
                         f"(got {k})")
    if k < 16 * rank:
        raise ValueError(f"--k must be at least 16×rank = {16 * rank} at "
                         f"--rank {rank} (got {k})")
    if k > 4 * rank * rank:
        raise ValueError(f"--k must be at most 4×rank² = {4 * rank * rank} at "
                         f"--rank {rank} (got {k})")
    if h % TILE_H or w % TILE_H:
        raise ValueError(f"--rows and --cols must each list a multiple of "
                         f"{TILE_H} offsets (got {h} rows, {w} cols)")
    if not 32 <= h * w <= 256:
        raise ValueError(f"the hash tile must hold 32 to 256 elements; "
                         f"--rows × --cols is {h}×{w} = {h * w}")
    dpl = dot_product_length(k, rank)
    if dpl % DWORD_SIZE:
        raise ValueError(f"k − k%rank must be a multiple of {DWORD_SIZE} "
                         f"(got {dpl} at --k {k} --rank {rank})")
    if m <= 0 or n <= 0 or m > 1 << 24 or n > 1 << 24:
        raise ValueError(f"--m and --n must be between 1 and {1 << 24} "
                         f"(got m={m}, n={n})")
    if (h + w) * dpl > 1 << 22:
        raise ValueError(f"the opened strips would be {(h + w) * dpl} bytes; "
                         f"consensus allows at most {1 << 22}")
    if m % rows_pattern.period():
        raise ValueError(f"--m must be a multiple of the --rows pattern period "
                         f"{rows_pattern.period()} (got {m})")
    if n % cols_pattern.period():
        raise ValueError(f"--n must be a multiple of the --cols pattern period "
                         f"{cols_pattern.period()} (got {n})")
