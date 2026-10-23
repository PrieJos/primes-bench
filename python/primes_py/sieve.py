"""Pure-Python segmented Sieve of Eratosthenes (single-threaded core).

Odds-only, one ``bytearray`` entry per odd candidate (``0`` = prime,
``1`` = composite).

ponytail: byte-per-odd, not bit-packed. Per-bit masking in pure Python costs
more time than the memory it saves; the Rust and C ports do the real
bit-packing. Upgrade here only if memory, not speed, ever becomes the limit.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

# Numbers covered per segment. ~256 KiB of bytearray (size/2 bytes), roughly
# cache-friendly while keeping Python-level loop overhead amortised.
SEGMENT_SIZE = 1 << 19


def _base_primes(limit: int) -> list[int]:
    """Compute the odd base primes used to sieve each segment.

    Args:
        limit: Upper bound; typically ``isqrt(high)`` of the target range.

    Returns:
        The odd primes ``p`` with ``3 <= p <= limit``, via a simple odds-only
        Sieve of Eratosthenes.
    """
    if limit < 3:
        return []
    n = (limit - 3) // 2 + 1  # index i -> value 2*i + 3
    sieve = bytearray(n)
    i = 0
    while True:
        p = 2 * i + 3
        if p * p > limit:
            break
        if not sieve[i]:
            start = (p * p - 3) // 2  # index of p*p
            sieve[start::p] = b"\x01" * len(range(start, n, p))
        i += 1
    return [2 * j + 3 for j in range(n) if not sieve[j]]


def _sieve_segment(seg_lo: int, seg_hi: int, bases: list[int]) -> bytearray:
    """Sieve the odd candidates in a single segment.

    Args:
        seg_lo: First (odd) value of the segment.
        seg_hi: Last (odd) value of the segment.
        bases: Odd base primes from :func:`_base_primes`.

    Returns:
        A ``bytearray`` where index ``j`` maps to value ``seg_lo + 2*j`` and
        holds ``0`` if that value is prime, ``1`` if composite.
    """
    size = (seg_hi - seg_lo) // 2 + 1
    seg = bytearray(size)
    for p in bases:
        if p * p > seg_hi:
            break
        start = p * p
        if start < seg_lo:
            start = seg_lo + (-seg_lo % p)  # first multiple of p >= seg_lo
            if start % 2 == 0:
                start += p  # p is odd, so this lands on an odd multiple
        idx = (start - seg_lo) // 2
        # values step by 2p to stay odd, so the index steps by p
        seg[idx::p] = b"\x01" * len(range(idx, size, p))
    return seg


def _segments(low: int, high: int, chunk: int) -> Iterator[tuple[int, int]]:
    """Partition a range into odd-aligned segment windows.

    Args:
        low: Lower bound of the target range (inclusive).
        high: Upper bound of the target range (inclusive).
        chunk: Odd candidates per window (window spans ``2 * chunk`` integers).

    Yields:
        Odd-aligned ``(seg_lo, seg_hi)`` pairs covering ``[max(low, 3), high]``.
    """
    lo = max(low, 3)
    if lo > high:
        return
    seg_lo = lo if lo % 2 else lo + 1
    span = 2 * chunk  # number of integers per window
    while seg_lo <= high:
        seg_hi = min(seg_lo + span - 2, high)
        if seg_hi % 2 == 0:
            seg_hi -= 1  # keep the window's last candidate odd
        if seg_hi < seg_lo:
            break
        yield seg_lo, seg_hi
        seg_lo = seg_hi + 2


def _validate(low: int, high: int) -> None:
    """Validate a range request.

    Args:
        low: Lower bound of the range (inclusive).
        high: Upper bound of the range (inclusive).

    Raises:
        ValueError: If ``low < 0`` or ``high < low``.
    """
    if low < 0:
        raise ValueError("low must be >= 0")
    if high < low:
        raise ValueError("high must be >= low")


def count_primes(low: int, high: int, *, chunk: int = SEGMENT_SIZE) -> int:
    """Count the primes in the inclusive range ``[low, high]``.

    Args:
        low: Lower bound of the range (inclusive); must be ``>= 0``.
        high: Upper bound of the range (inclusive); must be ``>= low``.
        chunk: Odd candidates per sieve segment.

    Returns:
        The number of primes in ``[low, high]``.

    Raises:
        ValueError: If ``low < 0`` or ``high < low``.
    """
    _validate(low, high)
    total = 1 if low <= 2 <= high else 0
    bases = _base_primes(math.isqrt(high)) if high >= 9 else []
    for seg_lo, seg_hi in _segments(low, high, chunk):
        seg = _sieve_segment(seg_lo, seg_hi, bases)
        total += len(seg) - sum(seg)  # entries are 0/1, so primes = size - composites
    return total


def list_primes(low: int, high: int, *, chunk: int = SEGMENT_SIZE) -> list[int]:
    """Return the sorted primes in the inclusive range ``[low, high]``.

    Args:
        low: Lower bound of the range (inclusive); must be ``>= 0``.
        high: Upper bound of the range (inclusive); must be ``>= low``.
        chunk: Odd candidates per sieve segment.

    Returns:
        The primes in ``[low, high]``, in ascending order.

    Raises:
        ValueError: If ``low < 0`` or ``high < low``.
    """
    _validate(low, high)
    out: list[int] = [2] if low <= 2 <= high else []
    bases = _base_primes(math.isqrt(high)) if high >= 9 else []
    for seg_lo, seg_hi in _segments(low, high, chunk):
        seg = _sieve_segment(seg_lo, seg_hi, bases)
        out.extend(seg_lo + 2 * j for j, v in enumerate(seg) if not v)
    return out


def iter_primes(low: int, high: int, *, chunk: int = SEGMENT_SIZE) -> Iterator[int]:
    """Lazily yield the primes in the inclusive range ``[low, high]``.

    Args:
        low: Lower bound of the range (inclusive); must be ``>= 0``.
        high: Upper bound of the range (inclusive); must be ``>= low``.
        chunk: Odd candidates per sieve segment.

    Yields:
        The primes in ``[low, high]``, in ascending order.

    Raises:
        ValueError: If ``low < 0`` or ``high < low``.
    """
    _validate(low, high)
    if low <= 2 <= high:
        yield 2
    bases = _base_primes(math.isqrt(high)) if high >= 9 else []
    for seg_lo, seg_hi in _segments(low, high, chunk):
        seg = _sieve_segment(seg_lo, seg_hi, bases)
        for j, v in enumerate(seg):
            if not v:
                yield seg_lo + 2 * j


def demo() -> None:
    """Run the module's self-checks.

    Invoke with ``python -m primes_py.sieve``.

    Raises:
        AssertionError: If any sieve result disagrees with its known value.
    """
    assert count_primes(0, 10) == 4, count_primes(0, 10)  # 2,3,5,7
    assert list_primes(0, 10) == [2, 3, 5, 7]
    assert list_primes(0, 1) == []
    assert list_primes(2, 2) == [2]
    assert list_primes(0, 2) == [2]
    assert list_primes(14, 17) == [17]
    assert count_primes(10, 20) == 4  # 11,13,17,19
    assert count_primes(0, 1_000_000) == 78498  # pi(1e6)
    assert count_primes(0, 10_000_000) == 620_000 + 44_579  # pi(1e7)=664579
    assert list(iter_primes(0, 30)) == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    assert count_primes(999_983, 999_983) == 1  # 999983 is prime
    assert count_primes(999_982, 999_982) == 0
    print("primes_py.sieve: all self-checks passed")


if __name__ == "__main__":
    demo()
