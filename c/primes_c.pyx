# cython: language_level=3, boundscheck=False, wraparound=False, freethreading_compatible=True
"""Cython wrapper over the C segmented sieve.

Shared API (matching the Rust and pure-Python backends)::

    count_primes(low, high, *, threads=1, backend="omp") -> int
    list_primes(low, high, *, threads=1, backend="omp") -> list[int]
    iter_primes(low, high, *, chunk=...) -> generator

`backend` selects the multi-threaded path ("omp" or "pthread"); it is ignored
when threads <= 1. The C core degrades gracefully if a backend is unavailable.
"""

from libc.stdint cimport uint64_t
from libc.stdlib cimport malloc, free

cdef extern from "sieve.h":
    uint64_t primes_count(uint64_t low, uint64_t high, int threads, int backend) nogil
    size_t primes_fill(uint64_t low, uint64_t high, int threads, int backend, uint64_t *out) nogil

BACKEND = "c"


cdef int _backend_code(backend):
    if backend == "omp":
        return 1
    if backend == "pthread":
        return 2
    raise ValueError("backend must be 'omp' or 'pthread'")


cdef _check(low, high):
    if low < 0:
        raise ValueError("low must be >= 0")
    if high < low:
        raise ValueError("high must be >= low")


def count_primes(low, high, *, threads=1, backend="omp"):
    _check(low, high)
    cdef uint64_t lo = low, hi = high
    cdef int t = threads if threads > 1 else 1
    cdef int bc = _backend_code(backend) if threads > 1 else 0
    cdef uint64_t r
    with nogil:
        r = primes_count(lo, hi, t, bc)
    return r


def list_primes(low, high, *, threads=1, backend="omp"):
    _check(low, high)
    cdef uint64_t lo = low, hi = high
    cdef int t = threads if threads > 1 else 1
    cdef int bc = _backend_code(backend) if threads > 1 else 0
    cdef uint64_t n, got, i
    cdef uint64_t *buf
    with nogil:
        n = primes_count(lo, hi, t, bc)
    if n == 0:
        return []
    buf = <uint64_t *> malloc(n * sizeof(uint64_t))
    if buf == NULL:
        raise MemoryError()
    try:
        with nogil:
            got = primes_fill(lo, hi, t, bc, buf)
        result = [0] * got
        for i in range(got):
            result[i] = buf[i]
        return result
    finally:
        free(buf)


def iter_primes(low, high, *, chunk=1 << 16):
    _check(low, high)
    cdef uint64_t lo = low, hi = high
    cdef uint64_t span = 2 * (<uint64_t> chunk if chunk > 0 else 1)
    cdef uint64_t seg_lo, seg_hi, n, i, start
    cdef uint64_t *buf

    if lo <= 2 <= hi:
        yield 2
    start = lo if lo > 3 else 3
    if start > hi:
        return
    seg_lo = start if (start & 1) else start + 1
    while seg_lo <= hi:
        seg_hi = seg_lo + span - 2
        if seg_hi > hi:
            seg_hi = hi
        if (seg_hi & 1) == 0:
            seg_hi -= 1
        if seg_hi < seg_lo:
            break
        with nogil:
            n = primes_count(seg_lo, seg_hi, 1, 0)
        if n > 0:
            buf = <uint64_t *> malloc(n * sizeof(uint64_t))
            if buf == NULL:
                raise MemoryError()
            try:
                with nogil:
                    primes_fill(seg_lo, seg_hi, 1, 0, buf)
                for i in range(n):
                    yield buf[i]
            finally:
                free(buf)
        seg_lo = seg_hi + 2
