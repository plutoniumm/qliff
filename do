#!/usr/bin/env bash
# ./do develop | build | test | bench | deploy | lint | docs
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# PyO3 abi3 wheels are forward-compatible; build on Python newer than PyO3 knows.
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

# resolve the interpreter: AARONSON_PY -> active conda env -> python3 on PATH.
resolve_py() {
  if [ -n "${AARONSON_PY:-}" ]; then PY="$AARONSON_PY"
  elif [ -n "${CONDA_PREFIX:-}" ]; then PY="$CONDA_PREFIX/bin/python"
  else PY="$(command -v python3 || true)"
  fi
  [ -n "$PY" ] || { echo "no Python found; set AARONSON_PY or activate a conda env"; exit 1; }

  BIN="$(cd "$(dirname "$PY")" && pwd)"
  MATURIN="$BIN/maturin"
  export PATH="$BIN:$PATH"   # so maturin can find cargo from the same env
  [ -x "$MATURIN" ] || "$PY" -m pip install -q -U maturin
}

develop() {
  resolve_py;
  ( cd "$ROOT" && "$MATURIN" develop );
}
build() {
  resolve_py;
  ( cd "$ROOT" && "$MATURIN" build --release --sdist );
}

run_dir() {
  local dir="$1" mode="$2" rc=0
  for f in "$dir"/*.py; do
    [ -e "$f" ] || continue
    case "$f" in */MDR.py) continue;; esac
    echo "-- $(basename "$f")"

    if ! "$PY" "$f";
     then [ "$mode" = soft ] || rc=1;
    fi
  done

  return $rc
}

test_() {
  develop;
  run_dir "$ROOT/test" hard;
}

bench() {
  develop;
  "$PY" -m pip install -q stim pymatching || true; run_dir "$ROOT/base" soft;
}

deploy() {
  build
  "$PY" -m pip install -q twine
  "$BIN/twine" check "$ROOT"/target/wheels/*
  local tokfile="${TOKEN_FILE:-$ROOT/.token.env}"

  [ -f "$tokfile" ] || { echo "no PyPI token file at $tokfile"; exit 1; }
  "$BIN/twine" upload "$ROOT"/target/wheels/* -u __token__ -p "$(cat "$tokfile")"
}

lint() {
  resolve_py;
  if [ "${1:-}" = "--fix" ] || [ "${1:-}" = "fix" ]; then
    ( cd "$ROOT" && "$PY" -m view.lint --fix && "$PY" -m black -q python/aaronson test view );
  else
    ( cd "$ROOT" && "$PY" -m view.lint && "$PY" -m black --check -q python/aaronson test view );
  fi
  # eastwood as a secondary style check on the shipped library; view.lint above wins on conflict.
  if command -v eastwood >/dev/null 2>&1; then ( cd "$ROOT" && eastwood -lang python python/aaronson ); fi
}

docs() {
  resolve_py;
  case "${1:-build}" in
    dev)   ( cd "$ROOT/docs" && npm install && npm run docs:dev ) ;;
    build) ( cd "$ROOT/docs" && npm install && npm run docs:build ) ;;
    test)  MDR_OUT="$ROOT/docs/tests" test_ ;;
    *) echo "usage: ./do docs {dev|build|test}"; exit 1 ;;
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
  *) echo "usage: ./do {develop|build|test|bench|deploy|lint|docs}"; exit 1 ;;
esac
