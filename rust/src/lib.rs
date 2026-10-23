//! Python bindings (PyO3) for the segmented prime sieve.
//!
//! Exposes `count_primes`, `list_primes`, and a chunked `iter_primes`, matching
//! the pure-Python and C/Cython backends. CPU-bound work runs with the GIL
//! released via [`Python::allow_threads`].

mod sieve;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const BACKEND: &str = "rust";

fn check_range(low: u64, high: u64) -> PyResult<()> {
    if high < low {
        return Err(PyValueError::new_err("high must be >= low"));
    }
    Ok(())
}

#[pyfunction]
#[pyo3(signature = (low, high, *, threads=1))]
fn count_primes(py: Python<'_>, low: u64, high: u64, threads: usize) -> PyResult<u64> {
    check_range(low, high)?;
    Ok(py.detach(|| sieve::count(low, high, threads.max(1))))
}

#[pyfunction]
#[pyo3(signature = (low, high, *, threads=1))]
fn list_primes(py: Python<'_>, low: u64, high: u64, threads: usize) -> PyResult<Vec<u64>> {
    check_range(low, high)?;
    Ok(py.detach(|| sieve::list(low, high, threads.max(1))))
}

/// Lazy iterator yielding primes in order, computing one segment at a time
/// (GIL released during each segment's compute).
#[pyclass]
struct PrimeIter {
    high: u64,
    bases: Vec<u64>,
    seg_lo: u64,
    span: u64,
    buf: Vec<u64>,
    pos: usize,
}

#[pymethods]
impl PrimeIter {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(mut slf: PyRefMut<'_, Self>, py: Python<'_>) -> Option<u64> {
        loop {
            if slf.pos < slf.buf.len() {
                let v = slf.buf[slf.pos];
                slf.pos += 1;
                return Some(v);
            }
            if slf.seg_lo > slf.high {
                return None;
            }
            let seg_lo = slf.seg_lo;
            let mut seg_hi = seg_lo.saturating_add(slf.span - 2).min(slf.high);
            if seg_hi.is_multiple_of(2) {
                seg_hi -= 1;
            }
            let next = {
                let bases: &[u64] = &slf.bases;
                py.detach(|| sieve::segment_primes(seg_lo, seg_hi, bases))
            };
            slf.buf = next;
            slf.pos = 0;
            slf.seg_lo = seg_hi + 2;
        }
    }
}

#[pyfunction]
#[pyo3(signature = (low, high, *, chunk=1usize<<16))]
fn iter_primes(low: u64, high: u64, chunk: usize) -> PyResult<PrimeIter> {
    check_range(low, high)?;
    let mut buf = Vec::new();
    if low <= 2 && 2 <= high {
        buf.push(2);
    }
    let bases = sieve::base_primes_for(high);
    let span = (2 * chunk.max(1) as u64).max(2);
    Ok(PrimeIter {
        high,
        bases,
        seg_lo: sieve::first_seg_lo(low),
        span,
        buf,
        pos: 0,
    })
}

#[pymodule]
fn primes_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("BACKEND", BACKEND)?;
    m.add_function(wrap_pyfunction!(count_primes, m)?)?;
    m.add_function(wrap_pyfunction!(list_primes, m)?)?;
    m.add_function(wrap_pyfunction!(iter_primes, m)?)?;
    Ok(())
}
