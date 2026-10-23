"""Rust (PyO3) segmented prime-sieve backend (re-exports the compiled extension)."""

from .primes_rust import *  # noqa: F403  (public API is defined in primes_rust.pyi)
