/* Unit tests for the C segmented sieve — the counterpart to `cargo test` on the
 * Rust side and `python -m primes_py.sieve` on the Python side.
 *
 * Includes sieve.c (not sieve.h) so the static helpers are in scope. Build and
 * run with `task test:c`, or under sanitizers with `task test:c:asan`.
 * Silence on stdout and exit 0 means pass. */

#include "sieve.c"

#include <assert.h>
#include <stdio.h>

#define LEN(a) (sizeof(a) / sizeof((a)[0]))

static const uint64_t MAX_ROOT = 0xFFFFFFFFULL;

/* Backends to sweep: 0 = serial, 1 = OpenMP, 2 = pthreads. Unavailable ones
 * degrade inside the sieve, so every entry is safe to call unconditionally. */
static const int BACKENDS[] = {0, 1, 2};
static const int THREADS[] = {1, 2, 4, 7};

/* Collect primes in [low, high] into a fresh buffer with a canary word past the
 * end. Asserts primes_fill agrees with primes_count and respects the buffer
 * contract from sieve.h. Caller frees. */
static uint64_t *collect(uint64_t low, uint64_t high, int threads, int backend, size_t *n)
{
  uint64_t count = primes_count(low, high, threads, backend);
  uint64_t *buf = (uint64_t *)malloc(((size_t)count + 1) * sizeof(uint64_t));

  assert(buf);
  buf[count] = 0xDEADBEEFCAFEF00DULL;

  size_t got = primes_fill(low, high, threads, backend, buf);

  assert(got == (size_t)count);
  assert(buf[count] == 0xDEADBEEFCAFEF00DULL); /* no write past primes_count */

  *n = got;

  return buf;
}

/* pi(10^k) — same table the Rust and Python suites assert against. */
static void test_known_counts(void)
{
  const struct
  {
    uint64_t limit, expected;
  } cases[] = {
      {10, 4},
      {100, 25},
      {1000, 168},
      {1000000, 78498},
      {10000000, 664579},
  };

  for (size_t i = 0; i < LEN(cases); i++)
    assert(primes_count(0, cases[i].limit, 1, 0) == cases[i].expected);
}

/* Same edge ranges as tests/test_correctness.py, checked at the C level. */
static void test_edge_ranges(void)
{
  const uint64_t ranges[][2] = {
      {0, 0},
      {0, 1},
      {0, 2},
      {2, 2},
      {1, 1},
      {14, 17},
      {0, 30},
      {999983, 999983},
      {999982, 999982},
      {100, 100},
  };

  for (size_t i = 0; i < LEN(ranges); i++)
  {
    uint64_t lo = ranges[i][0], hi = ranges[i][1];
    size_t n = 0;
    uint64_t *got = collect(lo, hi, 1, 0, &n);

    for (size_t j = 0; j < n; j++)
    {
      assert(got[j] >= lo && got[j] <= hi);
      assert(j == 0 || got[j] > got[j - 1]); /* strictly increasing */
    }
    free(got);
  }

  /* Spot-check the values, not just the shape. */
  size_t n = 0;
  uint64_t *got = collect(0, 30, 1, 0, &n);
  const uint64_t want[] = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29};

  assert(n == LEN(want));
  for (size_t j = 0; j < n; j++)
    assert(got[j] == want[j]);
  free(got);
}

/* Every backend/thread combination must match the serial result. The Cython
 * wrapper forces backend 0 whenever threads <= 1, so the single-threaded
 * OpenMP/pthread paths are only reachable from here. */
static void test_backend_parity(void)
{
  const uint64_t ranges[][2] = {
      {0, 1000000},
      {500000, 2000000},
      {0, 100},
  };

  for (size_t i = 0; i < LEN(ranges); i++)
  {
    uint64_t lo = ranges[i][0], hi = ranges[i][1];
    size_t want_n = 0;
    uint64_t *want = collect(lo, hi, 1, 0, &want_n);

    for (size_t b = 0; b < LEN(BACKENDS); b++)
    {
      for (size_t t = 0; t < LEN(THREADS); t++)
      {
        size_t got_n = 0;
        uint64_t *got = collect(lo, hi, THREADS[t], BACKENDS[b], &got_n);

        assert(got_n == want_n);
        for (size_t j = 0; j < got_n; j++)
          assert(got[j] == want[j]);
        free(got);
      }
    }
    free(want);
  }
}

/* high < low: the Cython wrapper rejects it, the C layer must stay quiet. */
static void test_degenerate_range(void)
{
  uint64_t buf[4] = {0};

  for (size_t b = 0; b < LEN(BACKENDS); b++)
  {
    for (size_t t = 0; t < LEN(THREADS); t++)
    {
      assert(primes_count(10, 5, THREADS[t], BACKENDS[b]) == 0);
      assert(primes_fill(10, 5, THREADS[t], BACKENDS[b], buf) == 0);
    }
  }
}

static void test_isqrt(void)
{
  const struct
  {
    uint64_t n, expected;
  } cases[] = {
      {0, 0},
      {1, 1},
      {2, 1},
      {3, 1},
      {4, 2},
      {8, 2},
      {9, 3},
      {1000000000000ULL, 1000000},
      {MAX_ROOT * MAX_ROOT - 1, MAX_ROOT - 1},
      {MAX_ROOT * MAX_ROOT, MAX_ROOT},
      /* Above here (x+1)*(x+1) overflows; the clamp must hold and terminate. */
      {MAX_ROOT * MAX_ROOT + 1, MAX_ROOT},
      {UINT64_MAX, MAX_ROOT},
  };

  for (size_t i = 0; i < LEN(cases); i++)
    assert(isqrt_u64(cases[i].n) == cases[i].expected);
}

static void test_base_primes(void)
{
  size_t n = 0;
  uint64_t *got = base_primes(50, &n);
  const uint64_t want[] = {3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47};

  assert(n == LEN(want));
  for (size_t i = 0; i < n; i++)
    assert(got[i] == want[i]);
  free(got);

  /* No odd primes below 3 — must report an empty set, not garbage. */
  for (uint64_t limit = 0; limit < 3; limit++)
  {
    n = 12345;
    got = base_primes(limit, &n);
    assert(n == 0);
    free(got);
  }
}

/* Blocks must tile [low, high] exactly: contiguous, non-overlapping, no gaps. */
static void test_make_blocks(void)
{
  const struct
  {
    uint64_t low, high;
    int n;
  } cases[] = {
      {0, 99, 1},
      {0, 99, 4},
      {0, 99, 7},
      {10, 12, 8}, /* more blocks requested than values available */
      {5, 5, 4},
      {0, 0, 1},
  };

  uint64_t lo[16], hi[16];

  for (size_t i = 0; i < LEN(cases); i++)
  {
    int nb = make_blocks(cases[i].low, cases[i].high, cases[i].n, lo, hi);

    assert(nb >= 1 && nb <= cases[i].n);
    assert(lo[0] == cases[i].low);
    assert(hi[nb - 1] == cases[i].high);

    uint64_t total = 0;

    for (int k = 0; k < nb; k++)
    {
      assert(lo[k] <= hi[k]);
      if (k > 0)
        assert(lo[k] == hi[k - 1] + 1); /* contiguous, no overlap */
      total += hi[k] - lo[k] + 1;
    }
    assert(total == cases[i].high - cases[i].low + 1);
  }

  /* high < low: a single empty block, reported as-is. */
  int nb = make_blocks(10, 5, 4, lo, hi);

  assert(nb == 1 && lo[0] == 10 && hi[0] == 5);
}

int main(void)
{
  test_known_counts();
  test_edge_ranges();
  test_backend_parity();
  test_degenerate_range();
  test_isqrt();
  test_base_primes();
  test_make_blocks();

  printf("c/test_sieve: all tests passed\n");

  return 0;
}
