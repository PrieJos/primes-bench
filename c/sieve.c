/* Segmented Sieve of Eratosthenes in C: odds-only, bit-packed segments.
 *
 * Bit j in a segment maps to value seg_lo + 2*j and is set when composite.
 * Multi-threading splits [low, high] into contiguous blocks; materialize uses a
 * two-pass count -> prefix-sum offsets -> parallel disjoint fill (no locking). */

#include "sieve.h"

#include <stdlib.h>
#include <string.h>
#include <math.h>

#ifdef _OPENMP
#include <omp.h>
#endif
#ifdef PRIMES_HAVE_PTHREAD
#include <pthread.h>
#endif

#define SEGMENT_BITS ((uint64_t)1 << 18)

static uint64_t isqrt_u64(uint64_t n)
{
  if (n == 0)
    return 0;

  uint64_t x = (uint64_t)sqrtl((long double)n);

  /* Clamp to the largest root that fits: x*x and (x+1)*(x+1) wrap mod 2^64
   * above this, which makes both comparisons below meaningless (and the
   * increment loop non-terminating for n near UINT64_MAX). */
  if (x > 0xFFFFFFFFULL)
    x = 0xFFFFFFFFULL;

  while (x > 0 && x * x > n)
    x--;

  while (x < 0xFFFFFFFFULL && (x + 1) * (x + 1) <= n)
    x++;

  return x;
}

/* Odd primes p with 3 <= p <= limit. Caller frees the result. */
static uint64_t *base_primes(uint64_t limit, size_t *out_count)
{
  if (limit < 3)
  {
    *out_count = 0;
    return NULL;
  }

  size_t n = (size_t)((limit - 3) / 2 + 1); /* index i -> value 2i+3 */
  unsigned char *comp = (unsigned char *)calloc(n, 1);

  if (!comp)
  {
    *out_count = 0;
    return NULL;
  }

  for (size_t i = 0;; i++)
  {
    uint64_t p = 2 * (uint64_t)i + 3;

    if (p * p > limit)
      break;

    if (!comp[i])
    {
      for (size_t k = (size_t)((p * p - 3) / 2); k < n; k += (size_t)p)
        comp[k] = 1;
    }
  }

  size_t c = 0;

  for (size_t j = 0; j < n; j++)
    if (!comp[j])
      c++;

  uint64_t *out = (uint64_t *)malloc(c * sizeof(uint64_t));
  size_t w = 0;

  for (size_t j = 0; j < n; j++)
    if (!comp[j])
      out[w++] = 2 * (uint64_t)j + 3;

  free(comp);
  *out_count = c;

  return out;
}

/* Sieve odd candidates in [seg_lo, seg_hi] (both odd) into `words`. Returns nbits. */
static size_t sieve_segment(
    uint64_t seg_lo,
    uint64_t seg_hi,
    const uint64_t *bases,
    size_t nbase,
    uint64_t *words)
{
  size_t nbits = (size_t)((seg_hi - seg_lo) / 2 + 1);
  size_t nwords = (nbits + 63) / 64;

  memset(words, 0, nwords * sizeof(uint64_t));

  for (size_t bi = 0; bi < nbase; bi++)
  {
    uint64_t p = bases[bi];

    if (p * p > seg_hi)
      break;

    uint64_t start = p * p;

    if (start < seg_lo)
    {
      uint64_t rem = seg_lo % p;

      start = rem ? seg_lo + (p - rem) : seg_lo;
      if ((start & 1) == 0)
        start += p; /* p is odd -> lands on odd multiple */
    }

    size_t idx = (size_t)((start - seg_lo) / 2);

    for (; idx < nbits; idx += (size_t)p)
      words[idx >> 6] |= (uint64_t)1 << (idx & 63);
  }

  return nbits;
}

/* Count primes in [max(low,3), high] (odds only; excludes 2). */
static uint64_t count_odds(
    uint64_t low,
    uint64_t high,
    const uint64_t *bases,
    size_t nbase)
{
  uint64_t lo = low < 3 ? 3 : low;
  if (lo > high)
    return 0;

  uint64_t seg_lo = (lo & 1) ? lo : lo + 1;
  uint64_t span = 2 * SEGMENT_BITS;
  uint64_t *words = (uint64_t *)malloc(((SEGMENT_BITS + 63) / 64) * sizeof(uint64_t));
  uint64_t total = 0;

  while (seg_lo <= high)
  {
    uint64_t seg_hi = seg_lo + span - 2;

    if (seg_hi > high)
      seg_hi = high;
    if ((seg_hi & 1) == 0)
      seg_hi--;
    if (seg_hi < seg_lo)
      break;

    size_t nbits = sieve_segment(seg_lo, seg_hi, bases, nbase, words);
    size_t nwords = (nbits + 63) / 64;
    uint64_t setbits = 0;

    for (size_t w = 0; w < nwords; w++)
      setbits += (uint64_t)__builtin_popcountll(words[w]);
    total += (uint64_t)nbits - setbits;
    seg_lo = seg_hi + 2;
  }

  free(words);

  return total;
}

/* Fill primes in [max(low,3), high] (odds only) into `out`. Returns count. */
static size_t fill_odds(
    uint64_t low,
    uint64_t high,
    const uint64_t *bases,
    size_t nbase,
    uint64_t *out)
{
  uint64_t lo = low < 3 ? 3 : low;

  if (lo > high)
    return 0;

  uint64_t seg_lo = (lo & 1) ? lo : lo + 1;
  uint64_t span = 2 * SEGMENT_BITS;
  uint64_t *words = (uint64_t *)malloc(((SEGMENT_BITS + 63) / 64) * sizeof(uint64_t));
  size_t w = 0;

  while (seg_lo <= high)
  {
    uint64_t seg_hi = seg_lo + span - 2;

    if (seg_hi > high)
      seg_hi = high;

    if ((seg_hi & 1) == 0)
      seg_hi--;

    if (seg_hi < seg_lo)
      break;

    size_t nbits = sieve_segment(seg_lo, seg_hi, bases, nbase, words);

    for (size_t j = 0; j < nbits; j++)
    {
      if (((words[j >> 6] >> (j & 63)) & 1) == 0)
        out[w++] = seg_lo + 2 * (uint64_t)j;
    }
    seg_lo = seg_hi + 2;
  }

  free(words);

  return w;
}

/* Split [low, high] into up to `n` contiguous inclusive blocks. Returns count. */
static int make_blocks(uint64_t low, uint64_t high, int n, uint64_t *lo, uint64_t *hi)
{
  if (n < 1)
    n = 1;

  if (high < low)
  {
    lo[0] = low;
    hi[0] = high;
    return 1;
  }

  uint64_t total = high - low + 1;
  uint64_t base = total / (uint64_t)n;
  uint64_t rem = total % (uint64_t)n;
  int nb = 0;
  uint64_t start = low;

  for (int k = 0; k < n; k++)
  {
    uint64_t size = base + ((uint64_t)k < rem ? 1 : 0);

    if (size == 0)
      continue;

    lo[nb] = start;
    hi[nb] = start + size - 1;
    start += size;
    nb++;
  }

  return nb;
}

/* ---- effective backend after availability degradation ---- */
static int effective_backend(int backend)
{
#ifndef PRIMES_HAVE_PTHREAD
  if (backend == 2)
    backend = 1;
#endif
#ifndef _OPENMP
  if (backend == 1)
    backend = 0;
#endif
  return backend;
}

#ifdef PRIMES_HAVE_PTHREAD
typedef struct
{
  uint64_t lo, hi;
  const uint64_t *bases;
  size_t nbase;
  uint64_t count;
  uint64_t *out;
} task_t;

static void *count_worker(void *arg)
{
  task_t *t = (task_t *)arg;
  t->count = count_odds(t->lo, t->hi, t->bases, t->nbase);
  return NULL;
}
static void *fill_worker(void *arg)
{
  task_t *t = (task_t *)arg;
  fill_odds(t->lo, t->hi, t->bases, t->nbase, t->out);
  return NULL;
}
#endif

static uint64_t count_odds_mt(uint64_t low, uint64_t high, int threads, int backend,
                              const uint64_t *bases, size_t nbase)
{
  if (threads < 1)
    threads = 1;

  uint64_t *lo = (uint64_t *)malloc((size_t)threads * sizeof(uint64_t));
  uint64_t *hi = (uint64_t *)malloc((size_t)threads * sizeof(uint64_t));
  int nb = make_blocks(low, high, threads, lo, hi);
  uint64_t total = 0;

  if (backend == 1)
  {
#ifdef _OPENMP
#pragma omp parallel for num_threads(threads) schedule(dynamic) reduction(+ : total)
    for (int k = 0; k < nb; k++)
      total += count_odds(lo[k], hi[k], bases, nbase);
#endif
  }
  else if (backend == 2)
  {
#ifdef PRIMES_HAVE_PTHREAD
    pthread_t *th = (pthread_t *)malloc((size_t)nb * sizeof(pthread_t));
    task_t *tk = (task_t *)malloc((size_t)nb * sizeof(task_t));
    for (int k = 0; k < nb; k++)
    {
      tk[k].lo = lo[k];
      tk[k].hi = hi[k];
      tk[k].bases = bases;
      tk[k].nbase = nbase;
      pthread_create(&th[k], NULL, count_worker, &tk[k]);
    }
    for (int k = 0; k < nb; k++)
    {
      pthread_join(th[k], NULL);
      total += tk[k].count;
    }
    free(th);
    free(tk);
#endif
  }
  else
  {
    for (int k = 0; k < nb; k++)
      total += count_odds(lo[k], hi[k], bases, nbase);
  }

  free(lo);
  free(hi);

  return total;
}

uint64_t primes_count(uint64_t low, uint64_t high, int threads, int backend)
{
  uint64_t two = (low <= 2 && 2 <= high) ? 1 : 0;

  if (high < 3)
    return two;

  backend = effective_backend(backend);
  if (threads <= 1 || backend == 0)
    backend = 0;

  size_t nbase = 0;
  uint64_t *bases = base_primes(isqrt_u64(high), &nbase);
  uint64_t odds = (backend == 0)
                      ? count_odds(low, high, bases, nbase)
                      : count_odds_mt(low, high, threads, backend, bases, nbase);

  free(bases);
  return two + odds;
}

size_t primes_fill(uint64_t low, uint64_t high, int threads, int backend, uint64_t *out)
{
  size_t w = 0;

  if (low <= 2 && 2 <= high)
    out[w++] = 2;

  if (high < 3)
    return w;

  backend = effective_backend(backend);
  if (threads <= 1 || backend == 0)
    backend = 0;

  size_t nbase = 0;
  uint64_t *bases = base_primes(isqrt_u64(high), &nbase);

  if (backend == 0)
  {
    w += fill_odds(low, high, bases, nbase, out + w);
    free(bases);
    return w;
  }

  /* Two-pass: count per block -> prefix offsets -> parallel disjoint fill. */
  uint64_t *lo = (uint64_t *)malloc((size_t)threads * sizeof(uint64_t));
  uint64_t *hi = (uint64_t *)malloc((size_t)threads * sizeof(uint64_t));
  int nb = make_blocks(low, high, threads, lo, hi);
  uint64_t *cnt = (uint64_t *)malloc((size_t)nb * sizeof(uint64_t));
  uint64_t *off = (uint64_t *)malloc((size_t)nb * sizeof(uint64_t));

  if (backend == 1)
  {
#ifdef _OPENMP
#pragma omp parallel for num_threads(threads) schedule(dynamic)
    for (int k = 0; k < nb; k++)
      cnt[k] = count_odds(lo[k], hi[k], bases, nbase);

    uint64_t acc = w;

    for (int k = 0; k < nb; k++)
    {
      off[k] = acc;
      acc += cnt[k];
    }

#pragma omp parallel for num_threads(threads) schedule(dynamic)
    for (int k = 0; k < nb; k++)
      fill_odds(lo[k], hi[k], bases, nbase, out + off[k]);
    w = acc;
#endif
  }
  else
  { /* backend == 2, pthreads */
#ifdef PRIMES_HAVE_PTHREAD
    pthread_t *th = (pthread_t *)malloc((size_t)nb * sizeof(pthread_t));
    task_t *tk = (task_t *)malloc((size_t)nb * sizeof(task_t));

    for (int k = 0; k < nb; k++)
    {
      tk[k].lo = lo[k];
      tk[k].hi = hi[k];
      tk[k].bases = bases;
      tk[k].nbase = nbase;
      pthread_create(&th[k], NULL, count_worker, &tk[k]);
    }

    for (int k = 0; k < nb; k++)
      pthread_join(th[k], NULL);

    uint64_t acc = w;

    for (int k = 0; k < nb; k++)
    {
      off[k] = acc;
      acc += tk[k].count;
      tk[k].out = out + off[k];
    }

    for (int k = 0; k < nb; k++)
      pthread_create(&th[k], NULL, fill_worker, &tk[k]);

    for (int k = 0; k < nb; k++)
      pthread_join(th[k], NULL);

    w = acc;
    free(th);
    free(tk);
#endif
  }

  free(lo);
  free(hi);
  free(cnt);
  free(off);
  free(bases);

  return w;
}
