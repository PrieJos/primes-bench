"""Cross-implementation correctness: every built backend must agree, and match
known prime-counting values and edge cases.

Backends that aren't built are skipped, so this runs in partial environments.
"""

import contextlib
import importlib

import pytest

BACKENDS = {}
for key, mod in (("rust", "primes_rust"), ("c", "primes_c"), ("python", "primes_py")):
    with contextlib.suppress(ImportError):
        BACKENDS[key] = importlib.import_module(mod)

if not BACKENDS:
    pytest.skip("no prime backends built", allow_module_level=True)

ALL = list(BACKENDS.items())
# pi(10^k): primes below/at 10^k
KNOWN = {10: 4, 100: 25, 1000: 168, 1_000_000: 78498, 10_000_000: 664579}
EDGE_RANGES = [
    (0, 0),
    (0, 1),
    (0, 2),
    (2, 2),
    (1, 1),
    (14, 17),
    (0, 30),
    (999_983, 999_983),
    (999_982, 999_982),
    (100, 100),
]


def _multi_kwargs(key):
    """Multi-threaded call kwargs valid for each backend."""
    if key == "c":
        return [{"threads": 4, "backend": "omp"}, {"threads": 4, "backend": "pthread"}]
    if key == "python":
        return [
            {"threads": 4, "backend": "thread"},
            {"threads": 4, "backend": "process"},
        ]
    return [{"threads": 4}]


@pytest.mark.parametrize("key,mod", ALL)
@pytest.mark.parametrize("limit,expected", KNOWN.items())
def test_known_counts(key, mod, limit, expected):
    assert mod.count_primes(0, limit) == expected


@pytest.mark.parametrize("key,mod", ALL)
@pytest.mark.parametrize("lo,hi", EDGE_RANGES)
def test_count_matches_list(key, mod, lo, hi):
    primes = mod.list_primes(lo, hi)
    assert mod.count_primes(lo, hi) == len(primes)
    assert primes == sorted(primes)
    assert all(lo <= p <= hi for p in primes)


@pytest.mark.parametrize("key,mod", ALL)
@pytest.mark.parametrize("lo,hi", EDGE_RANGES + [(0, 200_000), (500_000, 700_000)])
def test_iter_matches_list(key, mod, lo, hi):
    assert list(mod.iter_primes(lo, hi)) == mod.list_primes(lo, hi)


@pytest.mark.parametrize("key,mod", ALL)
def test_multithreaded_matches_serial(key, mod):
    for lo, hi in [(0, 1_000_000), (500_000, 2_000_000), (0, 100)]:
        serial_c = mod.count_primes(lo, hi)
        serial_l = mod.list_primes(lo, hi)
        for kw in _multi_kwargs(key):
            assert mod.count_primes(lo, hi, **kw) == serial_c, (key, kw)
            assert mod.list_primes(lo, hi, **kw) == serial_l, (key, kw)


def test_all_backends_agree():
    for lo, hi in [(0, 1_000_000), (123_456, 2_345_678)]:
        counts = {k: m.count_primes(lo, hi) for k, m in BACKENDS.items()}
        assert len(set(counts.values())) == 1, counts
        lists = {k: m.list_primes(lo, hi) for k, m in BACKENDS.items()}
        ref = next(iter(lists.values()))
        assert all(v == ref for v in lists.values())


@pytest.mark.parametrize("key,mod", ALL)
def test_invalid_range_raises(key, mod):
    with pytest.raises((ValueError, OverflowError)):
        mod.count_primes(10, 5)
