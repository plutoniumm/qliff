# Releasing qliff

qliff ships as **cp311-abi3** binary wheels (PyO3 Rust core, PEP 384 stable ABI)
plus an sdist. One wheel per OS×arch covers **every Python ≥ 3.11**. Everything is
built **locally** and pushed straight to PyPI — no CI, no GitHub involved.

```sh
conda activate aaronson
./do deploy          # build every backend in parallel, then twine-upload to PyPI
./do wheels          # same build, but stop before upload (inspect wheelhouse/)
```

## What gets built

| OS                 | x86_64                     | arm64 / aarch64           |
| ------------------ | -------------------------- | ------------------------- |
| macOS              | ✅ cross-compiled           | ✅ native                  |
| Linux (manylinux_2_28) | ✅ emulated (qemu)      | ✅ native (container)      |
| Windows            | ❌ — install from the sdist | ❌ — install from the sdist |

Plus the **sdist** (`setup.py sdist`), which bundles `Cargo.toml`, `Cargo.lock`,
`src/*.rs`, and the built Svelte SPA (`qliff/server/static/`). Windows users (or
anyone without a matching wheel) install from it — that needs a Rust toolchain on
their machine, which `pip` invokes through `setuptools-rust`.

**Windows wheels cannot be built on macOS** (no MSVC / `delvewheel`, and PyO3
cross-compiles to Windows unreliably). That's the one gap of the all-local
approach; if you ever need Windows wheels, build them on a Windows box.

## How it works (`./do deploy`)

- **macOS** wheels build directly with the active Python via `setup.py
  bdist_wheel` (arm64 native; x86_64 cross-compiled with `CARGO_BUILD_TARGET=
  x86_64-apple-darwin`). cibuildwheel isn't used on macOS because it requires a
  python.org *framework* Python that isn't installed.
- **Linux** wheels build inside `manylinux_2_28` containers via
  [cibuildwheel] + **colima**. Rust is installed inside the container
  (`CIBW_BEFORE_ALL_LINUX`); aarch64 is native to the arm Mac, x86_64 runs under
  qemu emulation (slower). musllinux is skipped locally by default (see
  `CIBW_SKIP` in `do`) — drop the skip to build it too.
- The **abi3 tag** comes from `setup.py`'s `options={"bdist_wheel":
  {"py_limited_api": "cp311"}}`, so a wheel built under any Python (this env is
  3.14) is still tagged `cp311-abi3`.
- Every Linux wheel is smoke-tested in-container (`ci/smoke.py`: import qliff,
  load the native core, run a Bell-pair stabilizer sim; numpy only).
- All builds run **in parallel** into `wheelhouse/`; logs land in
  `wheelhouse/_logs/`. `./do deploy` then runs `twine check` + `twine upload
  --skip-existing` using the token in `.vscode/token.env`.

## One-time machine setup

`./do` bootstraps most of this automatically (`ensure_rust`, `ensure_cibw`,
`ensure_container`), but for reference, the host needs:

- A **Rust toolchain** (`rustup default stable`) + the `x86_64-apple-darwin`
  target (auto-added).
- **cibuildwheel** in the conda env (auto-installed).
- A **native arm64 colima/lima** for the Linux containers. NB: Homebrew here is
  the Intel prefix (`/usr/local`), whose x86_64 colima/lima refuse to run under
  Rosetta — so native arm64 binaries live in `~/.local` and `/usr/local/bin/{colima,limactl}`
  are symlinks to them. `./do deploy` starts colima on demand.
- **node/npm** (for the SPA build) and the PyPI token at `.vscode/token.env`.

## Caveats

- **x86_64 Linux is emulated** on Apple Silicon (qemu) — that wheel is the slow
  one in the parallel build. aarch64 Linux and both macOS wheels are fast.
- musllinux is **not** built locally by default (slow under emulation).
- The `.vscode/token.env` PyPI token is sensitive — keep it out of git.

[cibuildwheel]: https://cibuildwheel.pypa.io/
