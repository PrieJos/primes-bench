"""C/Cython segmented prime-sieve backend (re-exports the compiled extension)."""

from .primes_c import *  # noqa: F403  (public API is defined in primes_c.pyi)
