"""Pure-Python prime sieve backend.

Shared API (matching the Rust and C backends)::

    count_primes(low, high, *, threads=1, backend="thread") -> int
    list_primes(low, high, *, threads=1, backend="thread") -> list[int]
    iter_primes(low, high, *, chunk=...) -> Iterator[int]

``threads=1`` uses the single-threaded core. ``threads>1`` uses ``backend``:
``"thread"`` (GIL-bound, or real scaling under free-threaded 3.14t) or
``"process"`` (multiprocessing). ``iter_primes`` is single-threaded by nature.
"""

from __future__ import annotations

from . import parallel, sieve
from .parallel import gil_enabled
from .sieve import iter_primes

__all__ = ["count_primes", "list_primes", "iter_primes", "gil_enabled", "BACKEND"]

BACKEND = "python"


def count_primes(
    low: int, high: int, *, threads: int = 1, backend: str = "thread"
) -> int:
    """Count the primes in the inclusive range ``[low, high]``.

    Args:
        low: Lower bound of the range (inclusive); must be ``>= 0``.
        high: Upper bound of the range (inclusive); must be ``>= low``.
        threads: Worker count. ``1`` runs the single-threaded core; ``>1``
            fans the range out across workers via ``backend``.
        backend: Parallel strategy when ``threads > 1``: ``"thread"`` or
            ``"process"``. Ignored when ``threads <= 1``.

    Returns:
        The number of primes in ``[low, high]``.

    Raises:
        ValueError: If ``low < 0`` or ``high < low``.
    """
    if threads <= 1:
        return sieve.count_primes(low, high)
    return parallel.count_primes(low, high, threads=threads, backend=backend)


def list_primes(
    low: int, high: int, *, threads: int = 1, backend: str = "thread"
) -> list[int]:
    """Return the sorted primes in the inclusive range ``[low, high]``.

    Args:
        low: Lower bound of the range (inclusive); must be ``>= 0``.
        high: Upper bound of the range (inclusive); must be ``>= low``.
        threads: Worker count. ``1`` runs the single-threaded core; ``>1``
            fans the range out across workers via ``backend``.
        backend: Parallel strategy when ``threads > 1``: ``"thread"`` or
            ``"process"``. Ignored when ``threads <= 1``.

    Returns:
        The primes in ``[low, high]``, in ascending order.

    Raises:
        ValueError: If ``low < 0`` or ``high < low``.
    """
    if threads <= 1:
        return sieve.list_primes(low, high)
    return parallel.list_primes(low, high, threads=threads, backend=backend)
