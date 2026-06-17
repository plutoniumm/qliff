import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit
from aaronson.noise import MonteCarlo


def _bitflip_circuit(p):
    c = Circuit(1)
    c.append("X_ERROR", [0], p)
    c.append("M", [0])

    return c


class NoiseTests(Question):
    def test_x_error_certain(self):
        """
        X_ERROR(1.0) flips |0> to |1> on every shot.
        """
        recs = MonteCarlo(_bitflip_circuit(1.0)).sample(64, seed=0)

        self.assertTrue(all(r == [1] for r in recs), msg="X_ERROR(1) must always flip")

    def test_zero_probability(self):
        """
        p=0 noise leaves |0> measured as 0.
        """
        recs = MonteCarlo(_bitflip_circuit(0.0)).sample(64, seed=1)

        self.assertTrue(all(r == [0] for r in recs), msg="p=0 must do nothing")

    def test_bitflip_rate(self):
        """
        BitFlip(p) flips |0> with empirical frequency about p.
        """
        recs = MonteCarlo(_bitflip_circuit(0.25)).sample(5000, seed=2)
        ones = sum(r[0] for r in recs) / len(recs)

        self.assertLess(abs(ones - 0.25), 0.03, msg=f"flip rate {ones} != 0.25")

    def test_full_depolarize_randomizes(self):
        """
        Depolarize1(0.75) on |0> gives a Z outcome that is ~50:50.

        I and Z keep the 0 outcome, X and Y flip it, so P(1) = 0.5.
        """
        c = Circuit(1)
        c.append("DEPOLARIZE1", [0], 0.75)
        c.append("M", [0])
        recs = MonteCarlo(c).sample(5000, seed=3)
        ones = sum(r[0] for r in recs) / len(recs)

        self.assertLess(abs(ones - 0.5), 0.04, msg=f"depolarized {ones} != 0.5")

    def test_expect_decays(self):
        """
        Dephasing drives <X> from +1 toward 0 as p grows.
        """
        c = Circuit(1)
        c.append("H", [0])
        c.append("Z_ERROR", [0], 0.5)
        est = MonteCarlo(c).expect("X", 5000, seed=4)

        self.assertLess(abs(est), 0.05, msg=f"<X> should decay to ~0, got {est}")


if __name__ == "__main__":
    runner = Exam("Noise", "Pauli-noise Monte-Carlo sampling", "noise.md")
    sys.exit(runner.run(load(NoiseTests)))
