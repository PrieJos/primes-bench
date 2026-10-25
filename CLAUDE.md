# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A benchmark of one algorithm — an odds-only, bit-packed **segmented Sieve of Eratosthenes** — implemented three times (Rust/PyO3 in `rust/`, C/Cython in `c/`, pure Python in `python/`) behind an identical Python API, compared by `bench/cli.py`. The root `pyproject.toml` is a uv workspace-style dev env (`package = false`) that installs the three backends as editable path deps.

Shared API (keep all backends in sync when changing it, including the `.pyi` stubs in `rust/python/primes_rust/` and `c/python/primes_c/`):

```python
count_primes(low, high, *, threads=1) -> int
list_primes(low, high, *, threads=1) -> list[int]
iter_primes(low, high, *, chunk=1<<16) -> Iterator[int]
```

`primes_c` adds `backend="omp"|"pthread"`; `primes_py` adds `backend="thread"|"process"` (only used when `threads > 1`). Ranges are inclusive and fit in `u64`.

## Commands

Tasks live in `Taskfile.yml` (`task --list`); builds go through `uv sync`.

```bash
uv sync                          # build everything (release) + dev tools
task build:release:rust|c        # rebuild one backend after editing its sources
task build:debug[:rust|:c]       # unoptimized + symbols (for debuggers; see docs/debugging.md)
task test                        # Python + Rust + C
uv run pytest tests/ -k <expr>   # single Python test
cargo test --manifest-path rust/Cargo.toml <name>   # single Rust test
task test:c | test:c:asan        # C unit tests (plain / ASan+UBSan)
task fmt | task lint             # cargo fmt/clippy + ruff format/check
uv run mypy                      # configured for python/primes_py and bench only
task bench -- --high 100_000_000 --threads 8 --mode count --repeat 5   # add --json
task sync | bench:gil | bench:ft | bench:both   # extra envs: .venv-gil (3.14), .venv-ft (3.14t free-threaded)
```

Editing Rust or C/Cython source does **not** take effect until you rebuild that backend (editable installs still compile native code). Extensions are ABI-specific, so each env (`.venv`, `.venv-gil`, `.venv-ft`) has its own compiled `.so`.

## Architecture notes

- **Tests**: `tests/test_correctness.py` imports whichever backends are built (skips missing ones) and cross-checks them against known π(10^k) values and edge ranges. `bench/cli.py` also validates that all variants agree before timing and exits non-zero otherwise.
- **C**: `c/sieve.c` is the core; `c/primes_c.pyx` is the Cython wrapper. `c/test_sieve.c` `#include`s `sieve.c` directly so it can test static helpers and thread/backend combos the wrapper can't reach (it pins `backend=0` when `threads <= 1`). `PRIMES_DEBUG=1` switches optimization flags in `c/setup.py`.
- **Rust**: `rust/src/sieve.rs` is the pure sieve (multithreading via `std::thread::scope`); `rust/src/lib.rs` is the PyO3 layer, releasing the GIL with `py.detach`. Debug-build rustc flags are passed through `MATURIN_PEP517_ARGS`.
- **Python**: `python/primes_py/sieve.py` (single-threaded) and `parallel.py` (threading/multiprocessing).
- Python requirement is `>=3.14`; the free-threaded build is located via `pyenv` in the Taskfile (`FT_PYTHON`).
- Ruff config: line length 88, rules `E,F,I,UP,B,SIM`.
