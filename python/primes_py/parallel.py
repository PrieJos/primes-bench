"""Multi-threaded / multi-process variants of the pure-Python sieve.

Three real-parallelism stories share one code path (:func:`_run`):

* ``threading`` under a standard GIL build  -> no CPU speedup (deliberate baseline).
* ``threading`` under a free-threaded build (``python3.14t``) -> real scaling.
* ``multiprocessing`` -> real scaling on any build, at the cost of pickling results.

The range is split into contiguous blocks (one per worker); block results combine
in order, so the concatenated prime list stays sorted.
"""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from . import sieve


def gil_enabled() -> bool:
    """Report whether the running interpreter holds the GIL.

    Returns:
        ``True`` on a standard build; ``False`` on a free-threaded
        (``3.14t``) interpreter.
    """
    check = getattr(sys, "_is_gil_enabled", None)
    return check() if check is not None else True


def _split(low: int, high: int, n: int) -> list[tuple[int, int]]:
    """Split a range into contiguous worker blocks.

    Args:
        low: Lower bound of the range (inclusive).
        high: Upper bound of the range (inclusive).
        n: Desired number of blocks.

    Returns:
        Up to ``n`` contiguous inclusive ``(lo, hi)`` blocks covering
        ``[low, high]``, sized as evenly as possible.
    """
    if n <= 1 or high < low:
        return [(low, high)]
    total = high - low + 1
    base, rem = divmod(total, n)
    blocks: list[tuple[int, int]] = []
    start = low
    for k in range(n):
        size = base + (1 if k < rem else 0)
        if size == 0:
            continue
        blocks.append((start, start + size - 1))
        start += size
    return blocks


# Module-level workers so ProcessPoolExecutor can pickle them.
def _count_block(b: tuple[int, int]) -> int:
    """Count primes in one ``(lo, hi)`` block (picklable pool worker)."""
    return sieve.count_primes(b[0], b[1])


def _list_block(b: tuple[int, int]) -> list[int]:
    """List primes in one ``(lo, hi)`` block (picklable pool worker)."""
    return sieve.list_primes(b[0], b[1])


def _run(low, high, threads, backend, worker, combine):
    """Fan a range out across workers and combine their results.

    Args:
        low: Lower bound of the range (inclusive).
        high: Upper bound of the range (inclusive).
        threads: Number of workers.
        backend: ``"process"`` for a process pool; anything else uses threads.
        worker: Per-block callable (e.g. :func:`_count_block`).
        combine: Reducer applied to the ordered list of block results.

    Returns:
        The combined result; block order is preserved so lists stay sorted.
    """
    blocks = _split(low, high, threads)
    if len(blocks) == 1:
        return combine([worker(blocks[0])])
    executor = ProcessPoolExecutor if backend == "process" else ThreadPoolExecutor
    with executor(max_workers=threads) as ex:
        return combine(list(ex.map(worker, blocks)))


def count_primes(low: int, high: int, *, threads: int, backend: str = "thread") -> int:
    """Count primes in ``[low, high]`` across ``threads`` workers.

    Args:
        low: Lower bound of the range (inclusive).
        high: Upper bound of the range (inclusive).
        threads: Number of workers to fan out across.
        backend: ``"thread"`` (default) or ``"process"``.

    Returns:
        The number of primes in ``[low, high]``.
    """
    return _run(low, high, threads, backend, _count_block, sum)


def list_primes(
    low: int, high: int, *, threads: int, backend: str = "thread"
) -> list[int]:
    """Return the sorted primes in ``[low, high]`` across ``threads`` workers.

    Args:
        low: Lower bound of the range (inclusive).
        high: Upper bound of the range (inclusive).
        threads: Number of workers to fan out across.
        backend: ``"thread"`` (default) or ``"process"``.

    Returns:
        The primes in ``[low, high]``, in ascending order.
    """
    return _run(
        low,
        high,
        threads,
        backend,
        _list_block,
        lambda parts: [p for part in parts for p in part],
    )


def demo() -> None:
    """Run the module's parallel self-checks against the serial core.

    Raises:
        AssertionError: If a parallel result disagrees with the serial sieve.
    """
    for backend in ("thread", "process"):
        assert count_primes(0, 1_000_000, threads=4, backend=backend) == 78498
        assert list_primes(0, 30, threads=3, backend=backend) == [
            2,
            3,
            5,
            7,
            11,
            13,
            17,
            19,
            23,
            29,
        ]
        assert count_primes(0, 100, threads=8, backend=backend) == sieve.count_primes(
            0, 100
        )
    print(f"primes_py.parallel: all self-checks passed (gil_enabled={gil_enabled()})")


if __name__ == "__main__":
    demo()
