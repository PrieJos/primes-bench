#!/usr/bin/env python
"""Benchmark & compare the prime-sieve backends (Rust / C+Cython / pure Python).

Usage examples::

    python bench/cli.py --low 0 --high 100_000_000 --threads 8 --mode count --repeat 5
    python bench/cli.py --mode list --high 1_000_000 --repeat 5 --json

Every backend exposes the same API, so the CLI validates that all variants agree
on the result before timing, then reports median/min time and throughput.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import statistics
import sys
import time
from collections.abc import Callable

Signature = int
Variant = tuple[str, Callable[[int, int, str], Signature]]


def _load_backends() -> dict[str, object]:
    found: dict[str, object] = {}
    for key, mod in (
        ("rust", "primes_rust"),
        ("c", "primes_c"),
        ("python", "primes_py"),
    ):
        try:
            found[key] = importlib.import_module(mod)
        except ImportError:
            print(f"warning: backend '{mod}' not importable, skipping", file=sys.stderr)
    return found


def _call(mod, lo, hi, mode, *, threads=1, backend=None) -> Signature:
    """Run one backend in one mode; return a count signature (used for validation)."""
    if mode == "iter":
        return sum(
            1 for _ in mod.iter_primes(lo, hi)
        )  # iter is single-threaded by nature
    fn = mod.count_primes if mode == "count" else mod.list_primes
    if backend is None:
        res = fn(lo, hi, threads=threads)
    else:
        res = fn(lo, hi, threads=threads, backend=backend)
    return res if mode == "count" else len(res)


def _build_variants(threads: int, b: dict[str, object]) -> list[Variant]:
    v: list[Variant] = []
    r, c, p = b.get("rust"), b.get("c"), b.get("python")
    if r:
        v.append(("rust-1t", lambda lo, hi, m: _call(r, lo, hi, m, threads=1)))
        if threads > 1:
            v.append(
                (
                    f"rust-{threads}t",
                    lambda lo, hi, m: _call(r, lo, hi, m, threads=threads),
                )
            )
    if c:
        v.append(("c-1t", lambda lo, hi, m: _call(c, lo, hi, m, threads=1)))
        if threads > 1:
            v.append(
                (
                    f"c-omp-{threads}t",
                    lambda lo, hi, m: _call(
                        c, lo, hi, m, threads=threads, backend="omp"
                    ),
                )
            )
            v.append(
                (
                    f"c-pthread-{threads}t",
                    lambda lo, hi, m: _call(
                        c, lo, hi, m, threads=threads, backend="pthread"
                    ),
                )
            )
    if p:
        v.append(("py-1t", lambda lo, hi, m: _call(p, lo, hi, m, threads=1)))
        if threads > 1:
            v.append(
                (
                    f"py-thread-{threads}t",
                    lambda lo, hi, m: _call(
                        p, lo, hi, m, threads=threads, backend="thread"
                    ),
                )
            )
            v.append(
                (
                    f"py-process-{threads}t",
                    lambda lo, hi, m: _call(
                        p, lo, hi, m, threads=threads, backend="process"
                    ),
                )
            )
    return v


def _validate(variants: list[Variant], low: int, high: int, mode: str, backends) -> int:
    """Assert every variant agrees; also exact-list check on a small range.

    Returns:
        The agreed-upon prime count across all variants.
    """
    sigs = {name: fn(low, high, mode) for name, fn in variants}
    ref_name, ref = next(iter(sigs.items()))
    bad = {n: s for n, s in sigs.items() if s != ref}
    if bad:
        print(f"VALIDATION FAILED: {ref_name}={ref} but {bad}", file=sys.stderr)
        sys.exit(1)
    lists = {k: m.list_primes(0, 1000) for k, m in backends.items()}
    first = next(iter(lists.values()))
    if any(v != first for v in lists.values()):
        print(
            "VALIDATION FAILED: list_primes(0,1000) disagree across backends",
            file=sys.stderr,
        )
        sys.exit(1)
    return ref


def _bench_one(fn, low, high, mode, repeat, warmup) -> list[float]:
    for _ in range(warmup):
        fn(low, high, mode)
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn(low, high, mode)
        times.append(time.perf_counter() - t0)
    return times


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--low", type=int, default=0)
    ap.add_argument("--high", type=int, default=10_000_000)
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--mode", choices=("count", "list", "iter"), default="count")
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    backends = _load_backends()
    if not backends:
        print("no backends available", file=sys.stderr)
        return 1
    variants = _build_variants(args.threads, backends)

    count = _validate(variants, args.low, args.high, args.mode, backends)
    scanned = args.high - args.low + 1

    rows = []
    for name, fn in variants:
        times = _bench_one(fn, args.low, args.high, args.mode, args.repeat, args.warmup)
        med = statistics.median(times)
        rows.append(
            {
                "variant": name,
                "median_s": med,
                "min_s": min(times),
                "scanned_per_s": scanned / med,
                "primes_per_s": count / med,
            }
        )
    rows.sort(key=lambda r: r["median_s"])

    gil = getattr(backends.get("python"), "gil_enabled", lambda: None)()
    meta = {
        "low": args.low,
        "high": args.high,
        "threads": args.threads,
        "mode": args.mode,
        "repeat": args.repeat,
        "primes": count,
        "scanned": scanned,
        "python": sys.version.split()[0],
        "gil_enabled": gil,
        "cpus": os.cpu_count(),
    }

    if args.json:
        print(json.dumps({"meta": meta, "results": rows}, indent=2))
        return 0

    print(
        f"range [{args.low}, {args.high}]  mode={args.mode}  threads={args.threads}  "
        f"primes={count}  repeat={args.repeat}"
    )
    print(f"python={meta['python']}  gil_enabled={gil}  cpus={meta['cpus']}")
    fastest = rows[0]["median_s"]
    print(
        f"\n{'variant':<22}{'median(s)':>12}{'min(s)':>12}"
        f"{'M scan/s':>12}{'vs best':>10}"
    )
    print("-" * 68)
    for r in rows:
        print(
            f"{r['variant']:<22}{r['median_s']:>12.4f}{r['min_s']:>12.4f}"
            f"{r['scanned_per_s'] / 1e6:>12.1f}{r['median_s'] / fastest:>9.2f}x"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
