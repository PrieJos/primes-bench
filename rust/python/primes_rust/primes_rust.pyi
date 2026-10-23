"""Type stubs for the Rust (PyO3) segmented prime-sieve backend."""

from collections.abc import Iterator

BACKEND: str

def count_primes(low: int, high: int, *, threads: int = ...) -> int:
    """Count the primes in the inclusive range ``[low, high]``.

    Args:
        low: Lower bound of the range (inclusive); must be ``>= 0``.
        high: Upper bound of the range (inclusive); must be ``>= low``.
        threads: Number of worker threads; ``1`` runs single-threaded.

    Returns:
        The number of primes in ``[low, high]``.
    """

def list_primes(low: int, high: int, *, threads: int = ...) -> list[int]:
    """Return the sorted primes in the inclusive range ``[low, high]``.

    Args:
        low: Lower bound of the range (inclusive); must be ``>= 0``.
        high: Upper bound of the range (inclusive); must be ``>= low``.
        threads: Number of worker threads; ``1`` runs single-threaded.

    Returns:
        The primes in ``[low, high]``, in ascending order.
    """

def iter_primes(low: int, high: int, *, chunk: int = ...) -> Iterator[int]:
    """Lazily yield the primes in the inclusive range ``[low, high]``.

    Args:
        low: Lower bound of the range (inclusive); must be ``>= 0``.
        high: Upper bound of the range (inclusive); must be ``>= low``.
        chunk: Candidates per internal sieve segment.

    Yields:
        The primes in ``[low, high]``, in ascending order.
    """
