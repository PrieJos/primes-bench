# Debugging in VS Code

Each backend is debugged with the tool that fits its language. Debugging a
**native** backend (C or Rust) means stopping *inside* a shared library loaded by
Python, so it needs a **debug build** first — release builds are optimized and
stripped, so breakpoints get skipped and variables show `<optimized out>`.

Launch configs live in [.vscode/launch.json](../.vscode/launch.json), build tasks
in [.vscode/tasks.json](../.vscode/tasks.json). Pick one in **Run and Debug** (`Ctrl+Shift+D`).

## Extensions

| Backend | Extension |
| ------- | --------- |
| Python  | Python Debugger (`ms-python.debugpy`) |
| C / Cython / Rust (native) | C/C++ (`ms-vscode.cpptools`) + `gdb` on `PATH` |
| Rust sources | rust-analyzer (`rust-lang.rust-analyzer`) |

## Python (`primes_py`)

Select **Python Debugger: pytest** (prompts for a test, e.g.
`tests/test_correctness.py::test_x`) or **Python Debugger: bench CLI**, set a
breakpoint in `python/primes_py/*.py`, press `F5`.

Caveats: with `backend="process"` the sieve runs in child processes, which the
debugger won't stop in — use `threads=1` or `backend="thread"` when stepping.

## C and Rust, called from Python

1. Build with symbols and no optimization:

   ```bash
   task build:debug        # both, or build:debug:c / build:debug:rust
   ```

   (or run the **build: debug extensions** task). Run `task build:release` again
   before benchmarking — debug builds are slow and skew timings.

2. Set breakpoints in `c/sieve.c`, `c/primes_c.pyx`/generated `primes_c.c`, or
   `rust/src/*.rs`.
3. Run **Native (gdb): pytest -> C/Rust** and enter a test. gdb launches
   `.venv/bin/python`; breakpoints show as unbound until the extension `.so` loads,
   then bind (`set breakpoint pending on` is preconfigured).

The call stack walks through all layers: Python → Cython wrapper / PyO3 glue →
the sieve. Cython stops in the generated `primes_c.c`, not the `.pyx`.

The same config works for the free-threaded or GIL envs by changing `program` to
`.venv-ft/bin/python` / `.venv-gil/bin/python` (after `task sync:ft` / `sync:gil`;
those envs need their own debug rebuild).

## C unit tests (no Python)

Select **C unit tests (gdb)**. Its pre-launch task compiles
[c/test_sieve.c](../c/test_sieve.c) with `-O0 -g` and the debugger starts it. This
is the fastest loop for `sieve.c` internals (`base_primes`, `make_blocks`, both
thread backends), since it needs no extension rebuild.

For memory errors, use `task test:c:asan` instead; it prints the faulting
line without a debugger.

## Rust unit tests (no Python)

Open `rust/src/sieve.rs` and click the **Debug** CodeLens above a `#[test]`
(provided by rust-analyzer). No launch config is needed.

## Troubleshooting

- **Breakpoint never hits / grayed out** — you're on a release build; run
  `task build:debug`. Confirm with `uv run python -c "import primes_c; print(primes_c.__file__)"`.
- **`<optimized out>`** — same cause.
- **Rust debug info path warnings** — harmless; the Rust task sets
  `-C debuginfo=2 -C strip=none`.
- **Breaking at thread start** — gdb prints `New Thread` noise for OpenMP/pthread/
  `std::thread` workers; use the *Threads* section of the call stack panel to switch.
- **macOS** — use CodeLLDB (`vadimcn.vscode-lldb`) with `"type": "lldb"` instead of gdb.
