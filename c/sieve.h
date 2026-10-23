#ifndef PRIMES_SIEVE_H
#define PRIMES_SIEVE_H

#include <stdint.h>
#include <stddef.h>

/* backend: 0 = single-threaded, 1 = OpenMP, 2 = pthreads.
 * When the requested backend is unavailable at build time it degrades:
 * pthreads -> OpenMP -> single-threaded. `threads` is ignored for backend 0. */

/* Count primes in the inclusive range [low, high]. */
uint64_t primes_count(uint64_t low, uint64_t high, int threads, int backend);

/* Write primes in [low, high] into caller-allocated `out`
 * (size >= primes_count(low, high, ...)). Returns the number written. */
size_t primes_fill(uint64_t low, uint64_t high, int threads, int backend, uint64_t *out);

#endif /* PRIMES_SIEVE_H */
