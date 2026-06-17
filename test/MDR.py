"""
I effectively copy pasted this from qudit.

Usage (bottom of a test file)::
    if __name__ == "__main__":
        import sys
        sys.exit(Exam("Gates", "Single-qubit Clifford gates", "gates.md")
                 .run(load(MyQuestion)))
"""

from __future__ import annotations

import os
import time
import traceback
import unittest

OUT_DIR = os.environ.get(
    "MDR_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_reports")
)

# Load all test_* methods from a TestCase subclass into a runnable suite.
load = unittest.defaultTestLoader.loadTestsFromTestCase


class Question(unittest.TestCase):
    """Base test case with stabilizer-domain assertion helpers."""

    def assertExpectation(self, got, want, atol=1e-9, msg=None):
        """Assert an expectation value matches within an absolute tolerance."""
        self.assertLessEqual(
            abs(float(got) - float(want)),
            atol,
            msg or f"expectation {got} != {want} (atol={atol})",
        )

    def samplesClose(self, samples, expected, atol=0.03, msg=None):
        """Empirical frequencies of ``samples`` match ``expected`` within ``atol``.

        ``samples`` is an iterable of outcomes (tuples/ints); ``expected`` maps an
        outcome key to its probability.
        """
        from collections import Counter

        samples = [tuple(s) if hasattr(s, "__iter__") else (s,) for s in samples]
        n = len(samples)
        self.assertGreater(n, 0, "no samples")
        freq = Counter(samples)
        for key, p in expected.items():
            k = tuple(key) if hasattr(key, "__iter__") else (key,)
            emp = freq.get(k, 0) / n
            self.assertLessEqual(
                abs(emp - p),
                atol,
                msg or f"P{k}={emp:.3f} != {p:.3f} (atol={atol}, n={n})",
            )

    def assertDeterministic(self, sim, qubit, expected, msg=None):
        """Measuring ``qubit`` on a copy of ``sim`` is deterministic and == expected."""
        s = sim.copy()
        out = int(s.M(qubit))
        self.assertEqual(out, int(expected), msg or f"M({qubit})={out} != {expected}")

    def tableauEqual(self, a, b, msg=None):
        """Two simulators describe the same stabilizer state (canonical form)."""
        self.assertEqual(
            a.canonical_stabilizers(),
            b.canonical_stabilizers(),
            msg or "stabilizer groups differ",
        )


class _Reporter(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.records = []  # (method, doc, status, detail)

    @staticmethod
    def _doc(test):
        return (test._testMethodDoc or "").strip()

    @staticmethod
    def _exc(err):
        return "".join(traceback.format_exception_only(err[0], err[1])).strip()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append((test._testMethodName, self._doc(test), "pass", ""))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append(
            (test._testMethodName, self._doc(test), "fail", self._exc(err))
        )

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append(
            (test._testMethodName, self._doc(test), "error", self._exc(err))
        )

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append((test._testMethodName, self._doc(test), "skip", reason))


class Exam:
    """A named group of questions that runs to a markdown report + console summary."""

    def __init__(self, name, desc, file):
        self.name = name
        self.desc = desc
        os.makedirs(OUT_DIR, exist_ok=True)
        self.file = os.path.join(OUT_DIR, file)

    def run(self, suite) -> int:
        result = _Reporter()
        t0 = time.perf_counter()
        suite(result)
        dt = time.perf_counter() - t0
        self._write(result, dt)

        npass = sum(1 for r in result.records if r[2] == "pass")
        ntot = len(result.records)
        ok = result.wasSuccessful()
        print(
            f"{'PASS' if ok else 'FAIL'}  {self.name}: {npass}/{ntot} in {dt * 1000:.0f}ms"
            f"  -> {os.path.relpath(self.file)}"
        )
        if not ok:
            for nm, _doc, st, detail in result.records:
                if st in ("fail", "error"):
                    print(f"      {st.upper()} {nm}: {detail}")
        return 0 if ok else 1

    def _write(self, result, dt):
        emoji = {
            "pass": "[pass]",
            "fail": "[FAIL]",
            "error": "[ERROR]",
            "skip": "[skip]",
        }
        npass = sum(1 for r in result.records if r[2] == "pass")
        lines = [
            f"# {self.name}",
            "",
            self.desc,
            "",
            f"**{npass}/{len(result.records)} passed** in {dt * 1000:.0f}ms",
            "",
        ]
        for nm, doc, st, detail in result.records:
            lines.append(f"### {emoji.get(st, '?')} `{nm}`")
            if doc:
                lines += ["", doc]
            if detail:
                lines += ["", "```", detail, "```"]
            lines.append("")
        with open(self.file, "w") as f:
            f.write("\n".join(lines))
