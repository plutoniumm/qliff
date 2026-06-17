# Testing

aaronson's test suite is an "exam" framework (adapted from
[plutoniumm/qudit](https://github.com/plutoniumm/qudit)): each test file is a
standalone script that builds an `Exam` over a `Question` subclass, runs it, and
emits a **markdown report** alongside the usual console pass/fail summary.

Those reports can be published straight into this site.

## Running the tests

```sh
./do test
```

By default reports are written to `test/_reports/` (gitignored). To surface them
in these docs instead, point the harness at the docs `tests/` directory via the
`MDR_OUT` environment variable:

```sh
MDR_OUT="$(pwd)/docs/tests" ./do test
```

Each test file emits one markdown file into that directory:

| Test file | Report | Covers |
| --------- | ------ | ------ |
| `test/smoke.py` | `smoke.md` | Build + import smoke test |
| `test/tableau.py` | `tableau.md` | CHP tableau gate correctness |
| `test/measure.py` | `measure.md` | Measurement outcomes and statistics |

The VitePress sidebar discovers any `*.md` in `docs/tests/` automatically, so a
freshly generated report shows up under **Testing** with no further wiring. The
reports are gitignored (this `index.md` is the only checked-in file here), so
regenerate them whenever you want the latest results.

## Building the docs with reports

A one-liner to refresh the reports and build the static site:

```sh
MDR_OUT="$(pwd)/docs/tests" ./do test && (cd docs && npm run docs:build)
```

If you have added a `docs` subcommand to `./do`, this becomes:

```sh
MDR_OUT="$(pwd)/docs/tests" ./do test && ./do docs build
```
