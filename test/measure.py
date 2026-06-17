import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Simulator


class MeasureTests(Question):
    def test_zero_deterministic(self):
        """
        Measuring |000> gives 0 on every qubit.
        """
        self.assertEqual(
            Simulator(3).M(0, 1, 2), [0, 0, 0], msg="|000> must measure all zero"
        )

    def test_x_gives_one(self):
        """
        X|0> measures 1.
        """
        self.assertEqual(Simulator(1).X(0).M(0), 1, msg="X|0> must measure 1")

    def test_repeatable(self):
        """
        Measuring the same qubit twice agrees.
        """
        s = Simulator(1).H(0)

        self.assertEqual(s.M(0), s.M(0), msg="repeated measurement must agree")

    def test_bell_correlation(self):
        """
        Bell-pair outcomes are perfectly correlated.
        """
        for seed in range(200):
            s = Simulator(2, seed=seed).H(0).CX(0, 1)

            self.assertEqual(s.M(0), s.M(1), msg="Bell outcomes must correlate")

    def test_plus_statistics(self):
        """

        |+> measures 0/1 about 50:50.
        """
        outs = [Simulator(1, seed=i).H(0).M(0) for i in range(4000)]

        self.samplesClose(
            outs,
            {
                0: 0.5,
                1: 0.5,
            },
            atol=0.04,
            msg="|+> should measure 0/1 evenly",
        )

    def test_ghz_statistics(self):
        """
        GHZ_3 collapses only to 000 or 111, about 50:50.
        """
        c = Counter()
        n = 3000
        for i in range(n):
            s = Simulator(3, seed=i).H(0).CX(0, 1).CX(0, 2)
            c[tuple(s.M(0, 1, 2))] += 1

        self.assertEqual(
            set(c) - {(0, 0, 0), (1, 1, 1)},
            set(),
            msg="GHZ must collapse only to 000 or 111",
        )

        self.assertLess(
            abs(c[(0, 0, 0)] / n - 0.5), 0.05, msg="000 share should be near 50%"
        )

    def test_record(self):
        """
        Measurements append to the record in order.
        """
        s = Simulator(2).X(0)
        s.M(0)
        s.M(1)

        self.assertEqual(
            s.measure_record, [1, 0], msg="record must reflect measurement order"
        )


if __name__ == "__main__":
    sys.exit(
        Exam("Measure", "Measurement outcomes and statistics", "measure.md").run(
            load(MeasureTests)
        )
    )
