"""ctypes bindings for libpearlmetal.dylib, with a NumPy-friendly wrapper.

Buffers are Metal shared-storage (unified memory): `Buf.array(...)` views the
same bytes the GPU reads and writes — copies are memory writes, not transfers.
"""

from __future__ import annotations

import ctypes as C
import os
from dataclasses import dataclass

import numpy as np

from . import reference as ref

_DYLIB = os.path.join(os.path.dirname(__file__), "..", "build", "libpearlmetal.dylib")

# The hits buffer the sweep kernels write: one u32 count, then up to
# HITS_CAPACITY (u32 base_r, u32 base_c) pairs. The GPU-side count may exceed
# the capacity (it counts every win); only the first HITS_CAPACITY are stored.
HITS_CAPACITY = 4096
HITS_BUF_BYTES = 4 + 8 * HITS_CAPACITY


class ShapeStruct(C.Structure):
    _fields_ = [
        ("k", C.c_uint32),
        ("r", C.c_uint32),
        ("h", C.c_uint32),
        ("w", C.c_uint32),
        ("rows", C.c_uint32 * 6),
        ("cols", C.c_uint32 * 6),
    ]


@dataclass(frozen=True)
class JobShape:
    k: int
    r: int
    rows_pattern: ref.Pattern
    cols_pattern: ref.Pattern

    @property
    def h(self) -> int:
        return self.rows_pattern.size()

    @property
    def w(self) -> int:
        return self.cols_pattern.size()

    def to_struct(self) -> ShapeStruct:
        s = ShapeStruct()
        s.k, s.r, s.h, s.w = self.k, self.r, self.h, self.w
        for i, (stride, length) in enumerate(self.rows_pattern.shape):
            s.rows[2 * i], s.rows[2 * i + 1] = stride, length
        for i, (stride, length) in enumerate(self.cols_pattern.shape):
            s.cols[2 * i], s.cols[2 * i + 1] = stride, length
        return s


class MetalError(RuntimeError):
    pass


class Buf:
    def __init__(self, lib, handle, nbytes: int):
        self._lib = lib
        self._h = handle
        self.nbytes = nbytes

    def array(self, dtype, shape) -> np.ndarray:
        ptr = self._lib.pm_contents(self._h)
        n = int(np.prod(shape)) * np.dtype(dtype).itemsize
        assert n <= self.nbytes, f"view of {n} B exceeds buffer of {self.nbytes} B"
        raw = (C.c_ubyte * n).from_address(ptr)
        return np.frombuffer(raw, dtype=dtype).reshape(shape)

    def release(self):
        if self._h:
            self._lib.pm_release(self._h)
            self._h = None


class Metal:
    """One Metal device context with a compiled job shape."""

    def __init__(self, dylib_path: str = _DYLIB):
        lib = C.CDLL(os.path.abspath(dylib_path))
        lib.pm_create.restype = C.c_void_p
        lib.pm_create.argtypes = [C.c_char_p, C.c_size_t]
        lib.pm_destroy.argtypes = [C.c_void_p]
        lib.pm_device_info.argtypes = [
            C.c_void_p, C.c_char_p, C.c_size_t,
            C.POINTER(C.c_uint64), C.POINTER(C.c_uint64),
        ]
        lib.pm_compile.argtypes = [C.c_void_p, C.POINTER(ShapeStruct), C.c_char_p, C.c_size_t]
        lib.pm_alloc.restype = C.c_void_p
        lib.pm_alloc.argtypes = [C.c_void_p, C.c_size_t]
        lib.pm_contents.restype = C.c_void_p
        lib.pm_contents.argtypes = [C.c_void_p]
        lib.pm_release.argtypes = [C.c_void_p]
        lib.pm_blake3_64.argtypes = [C.c_void_p] * 4 + [C.c_uint32, C.c_char_p, C.c_size_t]
        lib.pm_noise_uniform.argtypes = [
            C.c_void_p, C.c_char_p, C.c_char_p, C.c_void_p, C.c_uint32, C.c_char_p, C.c_size_t,
        ]
        lib.pm_noise_pairs.argtypes = [
            C.c_void_p, C.c_char_p, C.c_char_p, C.c_void_p, C.c_char_p, C.c_size_t,
        ]
        lib.pm_noise_apply.argtypes = [C.c_void_p] * 5 + [C.c_uint32, C.c_char_p, C.c_size_t]
        lib.pm_pow_sweep.argtypes = [
            C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p,
            C.c_uint32, C.c_char_p, C.c_char_p, C.c_void_p, C.c_uint32, C.c_void_p,
            C.c_char_p, C.c_size_t,
        ]
        lib.pm_pow_sweep2.argtypes = [
            C.c_void_p, C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32,
            C.c_char_p, C.c_char_p, C.c_void_p, C.c_uint32, C.c_void_p,
            C.c_char_p, C.c_size_t,
        ]
        lib.pm_pow_sweep_debug.argtypes = [
            C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p,
            C.c_uint32, C.c_char_p, C.c_char_p, C.c_void_p, C.c_uint32, C.c_void_p,
            C.c_void_p, C.c_void_p, C.c_char_p, C.c_size_t,
        ]
        self._lib = lib
        self._err = C.create_string_buffer(1024)
        self._ctx = lib.pm_create(self._err, 1024)
        if not self._ctx:
            raise MetalError(self._err.value.decode())
        self.shape: JobShape | None = None

    def _check(self, rc: int):
        if rc != 0:
            raise MetalError(self._err.value.decode())

    def device_info(self) -> dict:
        name = C.create_string_buffer(256)
        tg = C.c_uint64()
        th = C.c_uint64()
        self._lib.pm_device_info(self._ctx, name, 256, C.byref(tg), C.byref(th))
        return {
            "name": name.value.decode(),
            "max_threadgroup_memory": tg.value,
            "max_threads_per_threadgroup": th.value,
        }

    def compile(self, shape: JobShape):
        s = shape.to_struct()
        self._check(self._lib.pm_compile(self._ctx, C.byref(s), self._err, 1024))
        self.shape = shape

    def alloc(self, nbytes: int) -> Buf:
        h = self._lib.pm_alloc(self._ctx, nbytes)
        if not h:
            raise MetalError(f"pm_alloc({nbytes}) failed")
        return Buf(self._lib, h, nbytes)

    def from_numpy(self, arr: np.ndarray) -> Buf:
        buf = self.alloc(arr.nbytes)
        buf.array(arr.dtype, arr.shape)[...] = arr
        return buf

    def blake3_64(self, msgs: Buf, keys: Buf, out: Buf, count: int):
        self._check(
            self._lib.pm_blake3_64(self._ctx, msgs._h, keys._h, out._h, count, self._err, 1024)
        )

    def noise_uniform(self, seed: bytes, key: bytes, out: Buf, rows: int):
        self._check(
            self._lib.pm_noise_uniform(self._ctx, seed, key, out._h, rows, self._err, 1024)
        )

    def noise_pairs(self, seed: bytes, key: bytes, out: Buf):
        self._check(self._lib.pm_noise_pairs(self._ctx, seed, key, out._h, self._err, 1024))

    def noise_apply(self, base: Buf, table: Buf, pairs: Buf, out: Buf, rows: int):
        self._check(
            self._lib.pm_noise_apply(
                self._ctx, base._h, table._h, pairs._h, out._h, rows, self._err, 1024
            )
        )

    def pow_sweep(self, an: Buf, bnt: Buf, row_bases: Buf, n_rb: int, col_bases: Buf,
                  n_cb: int, a_seed: bytes, bound: bytes, hits: Buf, hits_cap: int,
                  digests_out: Buf | None = None):
        self._check(
            self._lib.pm_pow_sweep(
                self._ctx, an._h, bnt._h, row_bases._h, n_rb, col_bases._h, n_cb,
                a_seed, bound, hits._h, hits_cap,
                digests_out._h if digests_out else None, self._err, 1024,
            )
        )

    def pow_sweep2(self, an: Buf, bnt: Buf, band_lo: int, n_bands: int,
                   n_col_bases: int, a_seed: bytes, bound: bytes, hits: Buf,
                   hits_cap: int, digests_out: Buf | None = None):
        self._check(
            self._lib.pm_pow_sweep2(
                self._ctx, an._h, bnt._h, band_lo, n_bands, n_col_bases,
                a_seed, bound, hits._h, hits_cap,
                digests_out._h if digests_out else None, self._err, 1024,
            )
        )

    def pow_sweep_debug(self, an: Buf, bnt: Buf, row_bases: Buf, n_rb: int, col_bases: Buf,
                        n_cb: int, a_seed: bytes, bound: bytes, hits: Buf, hits_cap: int,
                        digests_out: Buf, csums_out: Buf, transcripts_out: Buf):
        self._check(
            self._lib.pm_pow_sweep_debug(
                self._ctx, an._h, bnt._h, row_bases._h, n_rb, col_bases._h, n_cb,
                a_seed, bound, hits._h, hits_cap, digests_out._h, csums_out._h,
                transcripts_out._h, self._err, 1024,
            )
        )
