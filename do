#!/usr/bin/env bash
# ./do develop | build | test | bench | deploy | lint | docs | studio | serve | dev | tex | wheels
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

# fail early if a required tool is missing (the conda env is expected to be active).
has() {
  for c in "$@"; do
    if ! command -v "$c" >/dev/null 2>&1; then
      echo "missing required tool: $c" >&2
      exit 1
    fi
  done
}

# install the setup.py build toolchain (setuptools-rust) if it is missing.
ensure_build_deps() {
  if ! python -c "import setuptools_rust" >/dev/null 2>&1; then
    pip install -q -U setuptools setuptools-rust wheel
  fi
}

# read the PyPI token.
tok() {
  local file="./.vscode/token.env"

  if [ ! -f "$file" ]; then
    echo "token file not found: $file" >&2
    exit 1
  fi

  cat "$file"
}

# run every *.py in a dir (skips MDR.py, obviously); soft mode never fails the build.
run_dir() {
  local dir="$1"
  local mode="$2"
  local rc=0

  for f in "$dir"/*.py; do
    [ -e "$f" ] || continue

    case "$f" in
      */MDR.py) continue ;;
    esac

    echo "-- $(basename "$f")"
    if ! python "$f"; then
      [ "$mode" = soft ] || rc=1
    fi
  done

  return $rc
}

# compile core
develop() {
  has python cargo rustc
  ensure_build_deps
  cd "$ROOT"
  python setup.py build_ext --inplace
}

# compile the core in RELEASE (optimized), for benchmarking.
# develop/build_ext produce DEBUG builds (~10-90x slower) -- never bench those.
# -Ctarget-cpu=native tunes to THIS machine (SIMD, scheduling); kept out of
# Cargo.toml so the PyPI wheel stays portable. lto/codegen-units/opt-level=3
# come from [profile.release] in Cargo.toml.
build_release() {
  has python cargo rustc
  cd "$ROOT"

  cargo rustc --release --lib --manifest-path Cargo.toml \
    --features pyo3/extension-module --crate-type cdylib -- \
    -Ctarget-cpu=native \
    -Clink-arg=-undefined \
    -Clink-arg=dynamic_lookup \
    -Clink-arg=-Wl,-install_name,@rpath/_core.abi3.so

  cp target/release/lib_core.dylib qliff/_core.abi3.so
}

build() {
  has python cargo rustc
  ensure_build_deps
  cd "$ROOT"
  studio  # the wheel ships the built SPA (qliff/server/static)
  rm -rf build dist qliff.egg-info
  python setup.py sdist bdist_wheel
}

test_() {
  develop
  run_dir "$ROOT/test" hard
}

bench() {
  build_release
  pip install -q stim pymatching || true
  run_dir "$ROOT/base" soft
}

# --- cross-platform wheels (built locally, shipped straight to PyPI) --------
# `deploy` builds cp311-abi3 wheels for macOS (arm64 + x86_64) AND Linux
# (x86_64 + aarch64) right here, then twine-uploads them. No GitHub. macOS
# wheels build directly with this Python (cibuildwheel needs a python.org
# framework build that isn't installed); Linux wheels build in manylinux
# containers via cibuildwheel + colima. One abi3 wheel per platform covers every
# Python >= 3.11 (tag set by setup.py's bdist_wheel options). Windows wheels
# CANNOT be produced on macOS -- those users install the sdist. No pyproject.toml.

ensure_cibw() {
  python -c "import cibuildwheel" >/dev/null 2>&1 || pip install -q -U cibuildwheel
}

# give rustup a default toolchain + the x86_64 macOS cross target (idempotent).
ensure_rust() {
  has rustup
  rustup show active-toolchain >/dev/null 2>&1 || rustup default stable
  rustup target list --installed 2>/dev/null | grep -q '^x86_64-apple-darwin$' \
    || rustup target add x86_64-apple-darwin
}

# bring the local container engine (colima) up if it isn't; needed for the Linux
# wheels. Returns non-zero when no engine is available.
ensure_container() {
  docker info >/dev/null 2>&1 && return 0
  command -v colima >/dev/null 2>&1 || return 1
  echo ">> starting colima (Linux container engine) ..." >&2
  colima start --cpu 4 --memory 8 --vm-type vz >&2 || return 1
  docker info >/dev/null 2>&1
}

# cibuildwheel config for the Linux wheels (all via CIBW_*; no pyproject.toml).
# Local builds skip musllinux (slow under x86 emulation) by default.
cibw_env() {
  export CIBW_BUILD="cp311-*"
  export CIBW_SKIP="*-musllinux* *-win32 *_i686 pp*"
  export CIBW_TEST_REQUIRES="numpy"
  export CIBW_TEST_SOURCES="ci/smoke.py"
  export CIBW_TEST_COMMAND="python ci/smoke.py"
  export CIBW_MANYLINUX_X86_64_IMAGE="manylinux_2_28"
  export CIBW_MANYLINUX_AARCH64_IMAGE="manylinux_2_28"
  # the manylinux containers ship no Rust; install it before each build.
  export CIBW_BEFORE_ALL_LINUX="curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable"
  export CIBW_ENVIRONMENT_LINUX='PATH="$HOME/.cargo/bin:$PATH" PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1'
}

# build the two macOS wheels directly with this Python. arm64 is native; x86_64
# is a cross-compile (CARGO_BUILD_TARGET + ARCHFLAGS + the host-platform tag
# override). Sequential -- both passes share the build/ tree.
build_macos_wheels() {
  export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
  export MACOSX_DEPLOYMENT_TARGET=11.0

  rm -rf build
  _PYTHON_HOST_PLATFORM=macosx-11.0-arm64 \
    python setup.py bdist_wheel -d wheelhouse

  rm -rf build
  ARCHFLAGS="-arch x86_64" CARGO_BUILD_TARGET=x86_64-apple-darwin \
    _PYTHON_HOST_PLATFORM=macosx-11.0-x86_64 \
    python setup.py bdist_wheel -d wheelhouse
}

# build every buildable backend IN PARALLEL into wheelhouse/, + an sdist into
# dist/. macOS always; Linux (x86_64, aarch64) when the container engine is up.
# Does NOT upload.
build_local_wheels() {
  has python cargo
  ensure_rust
  ensure_build_deps
  studio                       # SPA -> qliff/server/static (shipped in each wheel)
  cd "$ROOT"

  rm -rf wheelhouse dist build
  mkdir -p wheelhouse/_logs

  local pids=() names=() rc=0 i

  echo ">> building macOS wheels (arm64 + x86_64) ..." >&2
  build_macos_wheels >wheelhouse/_logs/macos.log 2>&1 &
  pids+=($!); names+=(macos)

  if ensure_container; then
    ensure_cibw
    cibw_env
    echo ">> building linux-aarch64 (native container) ..." >&2
    cibuildwheel --platform linux --archs aarch64 --output-dir wheelhouse \
      >wheelhouse/_logs/linux-aarch64.log 2>&1 &
    pids+=($!); names+=(linux-aarch64)

    echo ">> building linux-x86_64 (emulated, slower) ..." >&2
    cibuildwheel --platform linux --archs x86_64 --output-dir wheelhouse \
      >wheelhouse/_logs/linux-x86_64.log 2>&1 &
    pids+=($!); names+=(linux-x86_64)
  else
    echo "!! no container engine (colima) -- skipping Linux wheels" >&2
  fi

  i=0
  for p in "${pids[@]}"; do
    if ! wait "$p"; then
      echo "!! ${names[$i]} build FAILED -- tail of wheelhouse/_logs/${names[$i]}.log:" >&2
      tail -25 "wheelhouse/_logs/${names[$i]}.log" >&2
      rc=1
    fi
    i=$((i + 1))
  done

  [ "$rc" -eq 0 ] || { echo "wheel build failed" >&2; exit 1; }

  python setup.py sdist        # rust source + Cargo.lock + SPA ride along via MANIFEST
  echo ">> built wheels:" >&2
  ls -1 wheelhouse/*.whl >&2
}

deploy() {
  build_local_wheels
  pip install -q twine
  twine check wheelhouse/*.whl dist/*.tar.gz

  local tokval
  tokval="$(tok)"
  twine upload --skip-existing wheelhouse/*.whl dist/*.tar.gz -u __token__ -p "$tokval"
}

lint() {
  has python
  cd "$ROOT"

  if [ "${1:-}" = "--fix" ] || [ "${1:-}" = "fix" ]; then
    python -m view.lint --fix
    python -m black -q qliff test view
    return
  fi

  # view.lint always flags the protected test/MDR.py (its docstrings feed the MDR
  # report tables and must not be reformatted). Show its output but fail only on
  # findings elsewhere, so the remaining linters still run.
  local vl
  vl="$(python -m view.lint || true)"
  printf '%s\n' "$vl"
  if printf '%s\n' "$vl" | grep -vF 'test/MDR.py' | grep -qE '\.py:[0-9]+:'; then
    echo "view.lint: findings outside test/MDR.py" >&2
    exit 1
  fi

  python -m black --check -q qliff test view

  if command -v eastwood >/dev/null 2>&1; then
    eastwood src                                # rust core
    eastwood -lang python $(find qliff -name '*.py')  # python (skips built server/static/)
    if [ -d studio/src ]; then
      eastwood studio/src                       # studio frontend (ts + svelte)
    fi
  fi

  # svelte type-check, when the studio toolchain is installed.
  if [ -d studio/node_modules ]; then
    (cd studio && npx --no-install svelte-check --tsconfig ./tsconfig.json)
  fi
}

docs() {
  cd "$ROOT/docs"

  case "${1:-build}" in
    dev)
      has npm
      npm run dev
      ;;
    build)
      has npm
      npm run build
      ;;
    test)
      MDR_OUT="$ROOT/docs/tests" test_
      ;;
    *)
      echo "usage: ./do docs {dev|build|test}" >&2
      exit 1
      ;;
  esac
}

# build the Studio frontend into qliff/server/static (shipped in the wheel).
# After building, run the headless puppeteer smoke test (boots the SPA in a real
# Chromium, drives the Builder) to catch white-screen reactive loops -- skipped
# when puppeteer isn't installed (e.g. CI wheel builds) so it never blocks them.
studio() {
  has npm
  cd "$ROOT/studio"
  [ -d node_modules ] || npm install
  npm run build
  if [ -d node_modules/puppeteer ]; then
    node test/smoke.mjs
  else
    echo ">> studio smoke skipped (puppeteer not installed)" >&2
  fi
}

# launch the Studio web server (the `qliff-server` command) from the source tree.
# extra args pass through (e.g. ./do serve --port 9000 --no-browser).
serve() {
  has python
  cd "$ROOT"
  python -m qliff "$@"
}

# the full dev stack in one command: the qliff API server (background, default
# port) + the Vite dev server with HMR (foreground). Vite proxies /api to the
# API server, so the browser only ever talks to one origin (http://127.0.0.1:5174).
# Ctrl-C stops both.
dev() {
  has python npm
  cd "$ROOT/studio"
  [ -d node_modules ] || npm install
  python -m qliff --no-browser &
  local api_pid=$!
  trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM
  npm run dev
}

# compile a LaTeX/beamer file with tectonic. Args are passed straight through, so
# any path works (incl. files in subdirs; tectonic resolves figs/ relative to the
# file and writes the pdf next to it) and you can append tectonic flags.
tex() {
  has tectonic
  if [ "$#" -eq 0 ]; then
    echo "usage: ./do tex <file.tex> [tectonic args]" >&2
    exit 1
  fi
  tectonic "$@"
}

# build the cross-platform wheels locally (macOS + Linux) WITHOUT uploading --
# the same build as `deploy`, just stopping before twine. Wheels land in
# wheelhouse/, the sdist in dist/. Use it to inspect/test before `./do deploy`.
# (Linux wheels need a running container engine: `colima start`.)
wheels() {
  build_local_wheels
  echo ">> wheels in $ROOT/wheelhouse (not uploaded). sdist in $ROOT/dist." >&2
}

case "${1:-}" in
  develop) develop ;;
  build)   build ;;
  test)    test_ ;;
  bench)   bench ;;
  deploy)  deploy ;;
  lint)    shift; lint "$@" ;;
  docs)    shift; docs "$@" ;;
  studio)  studio ;;
  serve)   shift; serve "$@" ;;
  dev)     dev ;;
  tex)     shift; tex "$@" ;;
  wheels)  shift; wheels "$@" ;;
  *)
    echo "usage: ./do {develop|build|test|bench|deploy|lint|docs|studio|serve|dev|tex|wheels}" >&2
    exit 1
    ;;
esac
