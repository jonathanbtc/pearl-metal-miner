"""Host-side grid lifecycle: generate → commit → (on a hit) prove → verify.

Committed matrices are miner-chosen (Phase 0.5, E3): any int8 values in
[−64, +64] pass the verifier's range check. The commitment and PlainProof come
from `py-pearl-mining` (ISC), per ADR-0001 — the host path is upstream's own
bit-exact machinery, not a reimplementation.
"""

from __future__ import annotations

import numpy as np
import pearl_mining as pm

from . import reference as ref
from .metal_capi import JobShape


class Grid:
    """One committed pair (A, Bᵀ) bound to a job's header + config."""

    def __init__(self, shape: JobShape, m_dim: int, n_dim: int,
                 header_bytes: bytes, rng: np.random.Generator):
        self.shape = shape
        self.m_dim, self.n_dim = m_dim, n_dim
        self.A = rng.integers(ref.SIGNAL_MIN, ref.SIGNAL_MAX + 1,
                              size=(m_dim, shape.k), dtype=np.int64).astype(np.int8)
        self.Bt = rng.integers(ref.SIGNAL_MIN, ref.SIGNAL_MAX + 1,
                               size=(n_dim, shape.k), dtype=np.int64).astype(np.int8)
        config_bytes = ref.config_to_bytes(shape.k, shape.r,
                                           shape.rows_pattern, shape.cols_pattern)
        self.job_key = ref.compute_job_key(header_bytes, config_bytes)
        a_pad = ref.pad_to_chunk_boundary(self.A.tobytes())
        bt_pad = ref.pad_to_chunk_boundary(self.Bt.tobytes())
        self.tree_a = pm.MerkleTree(data=a_pad, key=self.job_key)
        self.tree_bt = pm.MerkleTree(data=bt_pad, key=self.job_key)
        self.b_seed, self.a_seed = ref.compute_commitment(self.job_key, a_pad, bt_pad)

    def craft_proof(self, base_r: int, base_c: int) -> pm.PlainProof:
        rows = [base_r + p for p in self.shape.rows_pattern.to_list()]
        cols = [base_c + q for q in self.shape.cols_pattern.to_list()]
        la = pm.MerkleTree.compute_leaf_indices_from_rows(rows, (self.m_dim, self.shape.k))
        lb = pm.MerkleTree.compute_leaf_indices_from_rows(cols, (self.n_dim, self.shape.k))
        return pm.PlainProof(
            self.m_dim, self.n_dim, self.shape.k, self.shape.r,
            pm.MatrixMerkleProof(self.tree_a.get_multileaf_proof(la), rows),
            pm.MatrixMerkleProof(self.tree_bt.get_multileaf_proof(lb), cols), None)


def share_nbits(pool_target: int) -> int:
    """Compact encoding of the pool's base target, floor-rounded, for
    verify_plain_proof's nbits_override. Floor makes the local check equal or
    STRICTER than the pool's — a share that passes locally passes remotely
    (up to the pool's own view of the job)."""
    return ref.target_to_nbits(pool_target)


def verify_share(header: pm.IncompleteBlockHeader, proof: pm.PlainProof,
                 pool_target: int) -> tuple[bool, str]:
    """Local verification AT SHARE DIFFICULTY — never without the override
    (Plan.md §0.2: without it the check is theatre)."""
    return pm.verify_plain_proof_v1(header, proof, nbits_override=share_nbits(pool_target))
