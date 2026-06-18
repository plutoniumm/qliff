#!/usr/bin/env bash
# ./do develop | build | test | bench | deploy | lint | docs
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

  cp target/release/lib_core.dylib aaronson/_core.abi3.so
}

build() {
  has python cargo rustc
  ensure_build_deps
  cd "$ROOT"
  rm -rf build dist aaronson.egg-info
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

deploy() {
  build
  pip install -q twine
  twine check "$ROOT"/dist/*

  local tokval
  tokval="$(tok)"
  twine upload "$ROOT"/dist/* -u __token__ -p "$tokval"
}

lint() {
  has python
  cd "$ROOT"

  if [ "${1:-}" = "--fix" ] || [ "${1:-}" = "fix" ]; then
    python -m view.lint --fix
    python -m black -q aaronson test view
  else
    python -m view.lint
    python -m black --check -q aaronson test view
  fi

  if command -v eastwood >/dev/null 2>&1; then
    eastwood -lang python aaronson
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

case "${1:-}" in
  develop) develop ;;
  build)   build ;;
  test)    test_ ;;
  bench)   bench ;;
  deploy)  deploy ;;
  lint)    shift; lint "$@" ;;
  docs)    shift; docs "$@" ;;
  *)
    echo "usage: ./do {develop|build|test|bench|deploy|lint|docs}" >&2
    exit 1
    ;;
esac
