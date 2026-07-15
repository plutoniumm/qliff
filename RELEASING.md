# Releasing qliff

qliff ships as **cp311-abi3** binary wheels (PyO3 Rust core, PEP 384 stable ABI)
plus an sdist. One wheel per OS×arch covers **every Python ≥ 3.11**. Everything is
built **locally** and pushed straight to PyPI — no CI, no GitHub involved.
`./do deploy` is PyPI only; the docs site deploys separately (see the last section).

```sh
conda activate aaronson
./do build           # build every backend in parallel (wheelhouse/ + dist/)
./do deploy          # twine check + upload what `build` produced (no rebuild)
```

## What gets built

| OS                 | x86_64                     | arm64 / aarch64           |
| ------------------ | -------------------------- | ------------------------- |
| macOS              | ✅ cross-compiled           | ✅ native                  |
| Linux (manylinux_2_28) | ✅ emulated (qemu)      | ✅ native (container)      |
| Windows            | ✅ cross-compiled (cargo-xwin) | ✅ cross-compiled (cargo-xwin) |

Plus the **sdist** (`setup.py sdist`), which bundles `Cargo.toml`, `Cargo.lock`,
`src/*.rs`, and the built Svelte SPA (`qliff/server/static/`). Anyone without a
matching wheel (musllinux, BSD, ...) installs from it — that needs a Rust
toolchain on their machine, which `pip` invokes through `setuptools-rust`.

## How it works (`./do build`)

- **macOS** wheels build directly with the active Python via `setup.py
  bdist_wheel` (arm64 native; x86_64 cross-compiled with `CARGO_BUILD_TARGET=
  x86_64-apple-darwin`). cibuildwheel isn't used on macOS because it requires a
  python.org *framework* Python that isn't installed.
- **Linux** wheels build inside `manylinux_2_28` containers via
  [cibuildwheel] + **colima**. Rust is installed inside the container
  (`CIBW_BEFORE_ALL_LINUX`); aarch64 is native to the arm Mac, x86_64 runs under
  qemu emulation (slower). musllinux is skipped locally by default (see
  `CIBW_SKIP` in `do`) — drop the skip to build it too.
- **Windows** wheels are cross-compiled with [cargo-xwin]: `xwin` downloads the
  MSVC CRT + Windows SDK into a local cache (Microsoft's license applies to that
  download — the "war crime"), lld links, and pyo3's `generate-import-lib`
  feature synthesizes the `python3.dll` import library so no Windows Python is
  needed. setuptools-rust is pointed at the `ci/cargo-xwin.sh` CARGO shim, and
  `_PYTHON_HOST_PLATFORM=win-amd64|win-arm64` forges the wheel tags.
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
- **Windows wheels are never executed here** (macOS can't run PE binaries):
  linking succeeding + abi3 + the smoke passing on every other platform is the
  guarantee. If in doubt, `pip install` the wheel on a real Windows box and run
  `ci/smoke.py`.
- The `.vscode/token.env` PyPI token is sensitive — keep it out of git.

## Docs → GitHub Pages

The docs site also deploys **locally**, straight from the built VitePress dist —
`./do deploy` has nothing to do with it:

```sh
cd docs
npm run build        # vitepress build (prod base /qliff/, writes .nojekyll)
npm run deploy       # pushes .vitepress/dist to the gh-pages branch
```

`npm run deploy` uses `gh-pages -d .vitepress/dist -t` (`-t` publishes dotfiles
so `.nojekyll` survives; without it GitHub's Jekyll pass drops the `_tut` asset
paths). One-time repo setting: **Settings → Pages → Deploy from a branch →
`gh-pages`**. The site lands at <https://plutoniumm.github.io/qliff/>.

[cargo-xwin]: https://github.com/rust-cross/cargo-xwin
[cibuildwheel]: https://cibuildwheel.pypa.io/
