import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit
from aaronson.noise import ImportanceSampler, MonteCarlo, StratifiedSampler


def _dephasing(n, p):
    c = Circuit(n)
    for q in range(n):
        c.append("H", [q])
    for q in range(n):
        c.append("Z_ERROR", [q], p)

    return c


class StratifiedTests(Question):
    def test_unbiased_dephasing(self):
        """
        Stratified <X..X> matches the exact (1-2p)^n for independent dephasing.
        """
        n, p = 6, 0.1
        exact = (1.0 - 2.0 * p) ** n
        got = StratifiedSampler(_dephasing(n, p)).expect("X" * n, 3000, seed=0)

        self.assertLess(abs(got - exact), 0.01, msg=f"got {got:.4f} want {exact:.4f}")

    def test_beats_flat_variance(self):
        """
        Stratifying has lower estimator spread than flat sampling here, where
        the observable depends only on the fault count.
        """
        obs = "X" * 6
        circuit = _dephasing(6, 0.1)
        strat = [StratifiedSampler(circuit).expect(obs, 1500, seed=s) for s in range(8)]
        flat = [MonteCarlo(circuit).expect(obs, 1500, seed=s) for s in range(8)]

        self.assertLess(
            statistics.pstdev(strat),
            statistics.pstdev(flat),
            msg=f"stratified spread {statistics.pstdev(strat):.4f} not < flat {statistics.pstdev(flat):.4f}",
        )

    def test_matches_importance_coherent(self):
        """
        With a coherent RZ plus depolarizing, stratified agrees with the flat
        importance sampler (both unbiased).
        """
        c = Circuit(1)
        c.append("H", [0])
        c.append("RZ", [0], math.pi / 5)
        c.append("DEPOLARIZE1", [0], 0.05)
        strat = StratifiedSampler(c).expect("X", 20000, seed=1)
        flat = ImportanceSampler(c).expect("X", 20000, seed=2)

        self.assertLess(
            abs(strat - flat), 0.05, msg=f"strat {strat:.3f} vs flat {flat:.3f}"
        )


if __name__ == "__main__":
    runner = Exam("Stratified", "Stratified importance sampling", "stratified.md")
    sys.exit(runner.run(load(StratifiedTests)))
