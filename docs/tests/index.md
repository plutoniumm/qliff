# Testing

qliff's tests run as an "exam" framework, adapted from
[plutoniumm/qudit](https://github.com/plutoniumm/qudit).

Each test file is a standalone script. It builds an `Exam` over a `Question`
subclass, runs it, and emits a **markdown report** next to the console pass/fail
summary.

Every report is a `Test | What it does | Result` table: one row per test, with a
✅ / ❌ / ⚠️ / ⏭️ result. Failures get full tracebacks in a `## Failures`
section below the table.

These reports publish straight into this site.

## Running the tests

```sh
./do test
```

Reports land in `test/_reports/` by default (gitignored). To surface them in
these docs, point the harness at `docs/tests/` with the `MDR_OUT` variable:

```sh
MDR_OUT="$(pwd)/docs/tests" ./do test
```

Each test file emits one markdown file into that directory:

| Test file | Report | Covers |
| --------- | ------ | ------ |
| `test/smoke.py` | `smoke.md` | Build + import smoke test |
| `test/tableau.py` | `tableau.md` | CHP tableau gate correctness |
| `test/measure.py` | `measure.md` | Measurement outcomes and statistics |

The VitePress sidebar picks up any `*.md` in `docs/tests/` automatically. A
fresh report shows up under **Testing** with no extra wiring.

The reports are gitignored; this `index.md` is the only checked-in file here.
Regenerate them whenever you want current results.

## Building the docs with reports

A one-liner to refresh the reports and build the static site:

```sh
MDR_OUT="$(pwd)/docs/tests" ./do test && (cd docs && npm run build)
```
