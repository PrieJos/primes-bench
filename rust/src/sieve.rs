//! Segmented Sieve of Eratosthenes: odds-only, bit-packed segments.
//!
//! A segment covers an inclusive odd range `[seg_lo, seg_hi]`; bit `j` maps to
//! the value `seg_lo + 2*j` and is *set* when that value is composite.

use std::thread;

/// Odd candidates per segment (so a segment spans `2 * SEGMENT_BITS` integers).
const SEGMENT_BITS: u64 = 1 << 18;

/// Odd primes `p` with `3 <= p <= limit` via a simple odds-only sieve.
fn base_primes(limit: u64) -> Vec<u64> {
    if limit < 3 {
        return Vec::new();
    }
    let n = ((limit - 3) / 2 + 1) as usize; // index i -> value 2*i + 3
    let mut composite = vec![false; n];
    let mut i = 0usize;
    loop {
        let p = 2 * i as u64 + 3;
        if p * p > limit {
            break;
        }
        if !composite[i] {
            let mut k = ((p * p - 3) / 2) as usize;
            while k < n {
                composite[k] = true;
                k += p as usize;
            }
        }
        i += 1;
    }
    (0..n)
        .filter(|&j| !composite[j])
        .map(|j| 2 * j as u64 + 3)
        .collect()
}

/// A bit-packed composite flag array for one segment's odd candidates.
struct BitSieve {
    words: Vec<u64>,
    nbits: usize,
}

impl BitSieve {
    fn new(nbits: usize) -> Self {
        Self {
            words: vec![0u64; nbits.div_ceil(64)],
            nbits,
        }
    }

    #[inline]
    fn set(&mut self, i: usize) {
        self.words[i >> 6] |= 1u64 << (i & 63);
    }

    /// Count of unset bits in `[0, nbits)` — i.e. primes in the segment.
    fn count_zeros(&self) -> u64 {
        let set: u64 = self.words.iter().map(|w| w.count_ones() as u64).sum();
        self.nbits as u64 - set
    }
}

/// Mark composites for odd candidates in `[seg_lo, seg_hi]` (both odd).
fn sieve_segment(seg_lo: u64, seg_hi: u64, bases: &[u64]) -> BitSieve {
    let nbits = ((seg_hi - seg_lo) / 2 + 1) as usize;
    let mut bs = BitSieve::new(nbits);
    for &p in bases {
        if p * p > seg_hi {
            break;
        }
        let mut start = p * p;
        if start < seg_lo {
            let rem = seg_lo % p;
            start = if rem == 0 { seg_lo } else { seg_lo + (p - rem) };
            if start % 2 == 0 {
                start += p; // p is odd, so this lands on an odd multiple
            }
        }
        let mut idx = ((start - seg_lo) / 2) as usize;
        let step = p as usize; // values step 2p -> index steps p
        while idx < nbits {
            bs.set(idx);
            idx += step;
        }
    }
    bs
}

/// Yield odd-aligned `(seg_lo, seg_hi)` windows covering `[max(low,3), high]`.
fn for_each_segment(low: u64, high: u64, mut f: impl FnMut(u64, u64, &[u64]), bases: &[u64]) {
    let lo = low.max(3);
    if lo > high {
        return;
    }
    let mut seg_lo = if lo % 2 == 1 { lo } else { lo + 1 };
    let span = 2 * SEGMENT_BITS;
    while seg_lo <= high {
        let mut seg_hi = (seg_lo + span - 2).min(high);
        if seg_hi.is_multiple_of(2) {
            seg_hi -= 1;
        }
        if seg_hi < seg_lo {
            break;
        }
        f(seg_lo, seg_hi, bases);
        seg_lo = seg_hi + 2;
    }
}

/// Count primes in `[max(low,3), high]` (odds only; excludes 2).
fn count_odds(low: u64, high: u64, bases: &[u64]) -> u64 {
    let mut total = 0u64;
    for_each_segment(
        low,
        high,
        |lo, hi, b| total += sieve_segment(lo, hi, b).count_zeros(),
        bases,
    );
    total
}

/// Append primes in `[max(low,3), high]` (odds only) to `out`.
fn list_odds(low: u64, high: u64, bases: &[u64], out: &mut Vec<u64>) {
    for_each_segment(
        low,
        high,
        |lo, hi, b| {
            let bs = sieve_segment(lo, hi, b);
            for j in 0..bs.nbits {
                if (bs.words[j >> 6] >> (j & 63)) & 1 == 0 {
                    out.push(lo + 2 * j as u64);
                }
            }
        },
        bases,
    );
}

/// Primes in a single odd segment `[seg_lo, seg_hi]` — used by the Python iterator.
pub fn segment_primes(seg_lo: u64, seg_hi: u64, bases: &[u64]) -> Vec<u64> {
    let bs = sieve_segment(seg_lo, seg_hi, bases);
    let mut out = Vec::new();
    for j in 0..bs.nbits {
        if (bs.words[j >> 6] >> (j & 63)) & 1 == 0 {
            out.push(seg_lo + 2 * j as u64);
        }
    }
    out
}

pub fn base_primes_for(high: u64) -> Vec<u64> {
    base_primes(high.isqrt())
}

/// First odd segment start for a range, and the per-segment integer span.
pub fn first_seg_lo(low: u64) -> u64 {
    let lo = low.max(3);
    if lo % 2 == 1 { lo } else { lo + 1 }
}

fn split(low: u64, high: u64, n: usize) -> Vec<(u64, u64)> {
    if n <= 1 || high < low {
        return vec![(low, high)];
    }
    let total = high - low + 1;
    let base = total / n as u64;
    let rem = total % n as u64;
    let mut blocks = Vec::new();
    let mut start = low;
    for k in 0..n as u64 {
        let size = base + if k < rem { 1 } else { 0 };
        if size == 0 {
            continue;
        }
        blocks.push((start, start + size - 1));
        start += size;
    }
    blocks
}

/// Count primes in inclusive `[low, high]`, using `threads` workers when > 1.
pub fn count(low: u64, high: u64, threads: usize) -> u64 {
    let two = if low <= 2 && 2 <= high { 1 } else { 0 };
    if high < 3 {
        return two;
    }
    let bases = base_primes(high.isqrt());
    if threads <= 1 {
        return two + count_odds(low, high, &bases);
    }
    let blocks = split(low, high, threads);
    let bases = &bases;
    let odds: u64 = thread::scope(|s| {
        let handles: Vec<_> = blocks
            .iter()
            .map(|&(a, b)| s.spawn(move || count_odds(a, b, bases)))
            .collect();
        handles.into_iter().map(|h| h.join().unwrap()).sum()
    });
    two + odds
}

/// List primes in inclusive `[low, high]`, using `threads` workers when > 1.
pub fn list(low: u64, high: u64, threads: usize) -> Vec<u64> {
    let mut out = Vec::new();
    if low <= 2 && 2 <= high {
        out.push(2);
    }
    if high < 3 {
        return out;
    }
    let bases = base_primes(high.isqrt());
    if threads <= 1 {
        list_odds(low, high, &bases, &mut out);
        return out;
    }
    let blocks = split(low, high, threads);
    let bases = &bases;
    let parts: Vec<Vec<u64>> = thread::scope(|s| {
        let handles: Vec<_> = blocks
            .iter()
            .map(|&(a, b)| {
                s.spawn(move || {
                    let mut v = Vec::new();
                    list_odds(a, b, bases, &mut v);
                    v
                })
            })
            .collect();
        handles.into_iter().map(|h| h.join().unwrap()).collect()
    });
    for part in parts {
        out.extend(part); // blocks are contiguous & ascending -> stays sorted
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_values() {
        assert_eq!(count(0, 10, 1), 4);
        assert_eq!(list(0, 10, 1), vec![2, 3, 5, 7]);
        assert_eq!(list(0, 1, 1), Vec::<u64>::new());
        assert_eq!(list(2, 2, 1), vec![2]);
        assert_eq!(list(14, 17, 1), vec![17]);
        assert_eq!(count(0, 1_000_000, 1), 78498);
        assert_eq!(count(0, 10_000_000, 1), 664_579);
    }

    #[test]
    fn parallel_matches_serial() {
        for &(lo, hi) in &[(0u64, 1_000_000u64), (500_000, 2_000_000), (0, 100)] {
            assert_eq!(count(lo, hi, 4), count(lo, hi, 1));
            assert_eq!(list(lo, hi, 4), list(lo, hi, 1));
        }
    }
}
