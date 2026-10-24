# primes — Rust vs Cython/C vs pure Python

A practical benchmark of three ways to generate all primes in a range `[low, high]`
with a **segmented Sieve of Eratosthenes** (odds-only, bit-packed), each exposed
to Python behind the **same API** and compared by one CLI.

| Backend     | Module        | Single-threaded | Multi-threaded                                          |
| ----------- | ------------- | --------------- | ------------------------------------------------------- |
| Rust + PyO3 | `primes_rust` | ✅              | `std::thread::scope`                                    |
| C + Cython  | `primes_c`    | ✅              | **OpenMP** and **pthreads** (pick via `backend=`)       |
| Pure Python | `primes_py`   | ✅              | `threading` (GIL / free-threaded) and `multiprocessing` |

## Shared API

```python
count_primes(low, high, *, threads=1) -> int
list_primes(low, high, *, threads=1) -> list[int]
iter_primes(low, high, *, chunk=1<<16) -> Iterator[int]
```

`primes_c` adds `backend="omp"|"pthread"`, `primes_py` adds `backend="thread"|"process"`
(both only consulted when `threads > 1`). Range is inclusive, values fit in `u64`.

## Build

Everything is managed from the root with [uv](https://docs.astral.sh/uv/):

```bash
uv sync     # builds primes_rust + editable primes_c & primes_py + pytest
```

By default this builds optimized (release) extensions. After editing a source
file, rebuild just that backend with `task build:release:rust` /
`task build:release:c` (or the `uv sync --reinstall-package …` command it wraps).

### Tasks

Common commands are wrapped in a [Taskfile](https://taskfile.dev/)
(`task --list` shows them all); the raw `uv`/`cargo` commands below still work.

```bash
task build              # alias of build:release — all backends optimized + pytest env
task build:release      # build primes_rust + primes_c optimized + pytest env
task build:debug        # same, but unoptimized with debug symbols
task build:release:rust # rebuild only primes_rust, optimized
task build:debug:rust   # rebuild only primes_rust, unoptimized w/ symbols
task build:release:c    # rebuild only primes_c, optimized
task build:debug:c      # rebuild only primes_c, unoptimized w/ symbols
task sync               # create/refresh all three envs (.venv, .venv-gil, .venv-ft)
task sync:dev           # refresh dev env (.venv)
task sync:gil           # build/refresh standard-GIL env (.venv-gil, 3.14)
task sync:ft            # build/refresh free-threaded env (.venv-ft, 3.14t)
task test               # alias of test:all — Python + Rust + C
task test:python        # Python cross-backend tests
task test:rust          # cargo test
task test:c             # C sieve unit tests
task test:c:asan        # C sieve unit tests under AddressSanitizer + UBSan (not in test:all)
task test:all           # Python + Rust + C
task bench -- --high 1_000_000 --mode count --repeat 5
task bench:gil -- ...   # bench on 3.14 (standard GIL)
task bench:ft -- ...    # bench on 3.14t (free-threaded)
task bench:both -- ...  # bench on both interpreters back-to-back
task wheels             # build distributable wheels for all backends into dist/
task fmt                # format Rust + Python (cargo fmt + ruff format)
task lint               # lint Rust + Python (cargo clippy + ruff check)
task ft                 # rebuild env on the free-threaded interpreter (3.14t)
task clean              # remove build artifacts
```

## Run

```bash
uv run pytest tests/                                            # correctness, all backends
uv run python bench/cli.py --high 100_000_000 --threads 8 --mode count --repeat 5
uv run python bench/cli.py --high 1_000_000 --mode list --repeat 5 --json
```

Each core sieve also self-checks standalone:
`uv run python -m primes_py.sieve`, `uv run python -m primes_py.parallel`,
`cargo test --manifest-path rust/Cargo.toml`, `task test:c`.

`c/test_sieve.c` includes `sieve.c` directly, so it covers the static helpers
(`isqrt_u64`, `base_primes`, `make_blocks`) and the backend/thread combinations
the Cython wrapper can't reach — it pins `backend=0` whenever `threads <= 1`.
`task test:c:asan` reruns the same suite under AddressSanitizer + UBSan, which
is where the `primes_fill` buffer contract and the parallel fill get checked for
overruns.

## Benchmark output

The CLI first validates that **every** backend/thread variant agrees on the
result (and that `list_primes(0, 1000)` is identical across backends); it exits
non-zero if any disagree. Only then does it time them. Example:

```
range [0, 10000000]  mode=count  threads=4  primes=664579  repeat=3
python=3.14.7  gil_enabled=True  cpus=8

variant                  median(s)      min(s)      max(s)     cv%    M scan/s   vs best
----------------------------------------------------------------------------------------
c-omp-4t                    0.0040      0.0040      0.0042     2.1%      2515.5     1.00x
rust-4t                     0.0049      0.0047      0.0053     5.3%      2055.1     1.22x
c-pthread-4t                0.0050      0.0049      0.0054     4.0%      2002.3     1.26x
c-1t                        0.0093      0.0092      0.0095     1.4%      1078.4     2.33x
rust-1t                     0.0167      0.0160      0.0173     3.1%       600.1     4.19x
py-1t                       0.0349      0.0336      0.0361     3.5%       286.2     8.79x
py-thread-4t                0.0430      0.0421      0.0445     2.4%       232.7    10.81x
py-process-4t               0.0872      0.0826      0.0910     3.8%       114.7    21.92x
```

**Header** — the run's parameters and environment:

- `range` / `mode` / `threads` / `repeat` — the arguments used.
- `primes` — the agreed-upon prime count in the range (the validated result).
- `python` — interpreter version; `gil_enabled` — whether the GIL is active
  (`False` on a `3.14t` free-threaded build); `cpus` — logical cores available.

**Rows** — one per variant, sorted fastest first. The variant name is
`<backend>[-<strategy>]-<N>t`, e.g. `c-omp-4t` is the C backend with OpenMP on
4 threads, `py-1t` is single-threaded pure Python. Columns:

- `median(s)` — median wall-clock time over `repeat` runs (the ranking key;
  robust to outliers).
- `min(s)` — fastest run (best case, least noise).
- `max(s)` — slowest run (worst case; the gap from `min` shows run-to-run noise).
- `cv%` — coefficient of variation (stdev ÷ median, as a percent): how noisy the
  runs were. Unitless, so it's comparable across fast and slow variants. A low
  `cv%` means the median is trustworthy; a high one means ranking gaps smaller
  than it are within noise.
- `M scan/s` — throughput in **millions of integers scanned per second**,
  `(high - low + 1) / median`. Comparable across ranges since it's normalized
  by range size, not prime count.
- `vs best` — median relative to the fastest variant (`1.00x` is the winner;
  `4.19x` means 4.19× slower).

Pass `--json` for the same data machine-readable (a `meta` object plus a
`results` array with `median_s`, `min_s`, `max_s`, `stdev_s`, `cv`,
`scanned_per_s`, and `primes_per_s` per variant) — note JSON carries raw
`stdev_s` (the table shows it as `cv%` = `cv` × 100) and `primes_per_s` (primes
found per second), which the table omits.

Numbers above are one Linux/GCC box; absolute times vary by machine, but the
ordering (native backends ≫ pure Python, and the GIL flattening
`py-thread` scaling unless free-threaded) is the point.

## Free-threaded Python (`3.14t`)

The `primes_py` `threading` backend shows **no CPU speedup** on a standard GIL
build (that's the intended contrast). To see real thread scaling, build and run
under a free-threaded interpreter:

```bash
task ft          # rebuild the default env on the free-threaded build
task sync:ft     # or build a dedicated .venv-ft (leaves .venv untouched)
task bench:ft -- --high 1_000_000 --mode count --repeat 5   # bench on .venv-ft
```

These point uv at the latest free-threaded CPython from `pyenv versions` (a
build whose name ends in `t`, e.g. `3.14.9t`) — install one with
`pyenv install 3.14t`. The CLI prints `gil_enabled=False` when running
free-threaded.

## Platform notes (C backend)

Developed and tested on **Linux/GCC**. The Cython `setup.py` sets
platform-conditional flags; other OSes build with caveats:

- **macOS** — pthreads is native; OpenMP needs `brew install libomp` (Apple Clang
  ships no OpenMP runtime).
- **Windows/MSVC** — no `<pthread.h>`, so only the **OpenMP** backend is built;
  requesting `backend="pthread"` transparently falls back.

No macOS/Windows CI is configured.
