"""Build the Cython `primes_c` extension with platform-conditional flags.

Linux-first. macOS and Windows build with caveats (see README):
- macOS: OpenMP needs `brew install libomp`; pthreads is native.
- Windows/MSVC: no `<pthread.h>` -> only the OpenMP backend is available.
"""

import os
import sys

from Cython.Build import cythonize  # type: ignore[import-not-found]
from setuptools import Extension, setup  # type: ignore[import-untyped]

compile_args: list[str] = []
link_args: list[str] = []
define_macros: list[tuple[str, str]] = []

# Debug builds (PRIMES_DEBUG=1): no optimization + symbols, to mirror the Rust
# debug profile. Default is the optimized release build.
debug = bool(os.environ.get("PRIMES_DEBUG"))

if sys.platform == "win32":
    compile_args += (["/Od", "/Zi"] if debug else ["/O2"]) + ["/openmp"]
    # pthreads unavailable under MSVC -> PRIMES_HAVE_PTHREAD left undefined.
else:
    compile_args += (["-O0", "-g"] if debug else ["-O3"]) + ["-std=c11", "-pthread"]
    link_args += ["-pthread", "-lm"]
    define_macros.append(("PRIMES_HAVE_PTHREAD", "1"))
    if sys.platform == "darwin":
        # Apple Clang ships no OpenMP runtime; requires Homebrew libomp.
        compile_args += ["-Xpreprocessor", "-fopenmp"]
        link_args += ["-lomp"]
    else:
        compile_args += ["-march=native", "-fopenmp"]
        link_args += ["-fopenmp"]

ext = Extension(
    "primes_c.primes_c",
    sources=["primes_c.pyx", "sieve.c"],
    extra_compile_args=compile_args,
    extra_link_args=link_args,
    define_macros=define_macros,
)

setup(
    name="primes-c",
    version="0.1.0",
    packages=["primes_c"],
    package_dir={"": "python"},
    ext_modules=cythonize([ext], language_level="3"),
    package_data={"primes_c": ["py.typed", "*.pyi"]},
    include_package_data=True,
)
