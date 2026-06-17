import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit
from aaronson.noise import ImportanceSampler, MonteCarlo

_H = np.array([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2)
_PAULIS = {
    "X": np.array([[0, 1], [1, 0]], dtype=complex),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "Z": np.array([[1, 0], [0, -1]], dtype=complex),
}


def _rz(t):
    return np.array([[np.exp(-0.5j * t), 0], [0, np.exp(0.5j * t)]], dtype=complex)


def _rx(t):
    c = math.cos(t / 2)
    s = math.sin(t / 2)

    return np.array([[c, -1j * s], [-1j * s, c]], dtype=complex)


def _exact(unitaries, obs):
    psi = np.array([1, 0], dtype=complex)
    for u in unitaries:
        psi = u @ psi

    return float(np.real(psi.conj() @ _PAULIS[obs] @ psi))


class CoherentTests(Question):
    def test_rz_on_plus_matches_exact(self):
        """
        Importance sampling of RZ(theta) on |+> reproduces exact <X> and <Y>.
        """
        for theta in (0.0, math.pi / 6, math.pi / 4, math.pi / 2, math.pi):
            c = Circuit(1)
            c.append("H", [0])
            c.append("RZ", [0], theta)
            sampler = ImportanceSampler(c)
            for obs in ("X", "Y"):
                got = sampler.expect(obs, 20000, seed=7)
                want = _exact([_H, _rz(theta)], obs)

                self.assertLess(
                    abs(got - want),
                    0.06,
                    msg=f"RZ({theta:.2f}) <{obs}>: got {got:.3f} want {want:.3f}",
                )

    def test_rx_on_zero_matches_exact(self):
        """
        Importance sampling of RX(theta) on |0> reproduces exact <Z> and <Y>.
        """
        for theta in (math.pi / 6, math.pi / 3, math.pi / 2):
            c = Circuit(1)
            c.append("RX", [0], theta)
            sampler = ImportanceSampler(c)
            for obs in ("Z", "Y"):
                got = sampler.expect(obs, 20000, seed=11)
                want = _exact([_rx(theta)], obs)

                self.assertLess(
                    abs(got - want),
                    0.06,
                    msg=f"RX({theta:.2f}) <{obs}>: got {got:.3f} want {want:.3f}",
                )

    def test_monte_carlo_rejects_coherent(self):
        """
        MonteCarlo refuses a non-Pauli (coherent) channel.
        """
        c = Circuit(1)
        c.append("RZ", [0], 0.3)
        c.append("M", [0])

        with self.assertRaises(ValueError):
            MonteCarlo(c).sample(8)

    def test_clifford_rotation_is_exact(self):
        """
        RZ(pi/2) is the Clifford S (gamma = 1), so <Y> on |+> is exactly 1.
        """
        c = Circuit(1)
        c.append("H", [0])
        c.append("RZ", [0], math.pi / 2)
        got = ImportanceSampler(c).expect("Y", 2000, seed=1)

        self.assertLess(
            abs(got - 1.0), 1e-9, msg=f"RZ(pi/2) <Y> should be 1, got {got}"
        )


if __name__ == "__main__":
    runner = Exam(
        "Coherent", "Coherent-noise importance sampling vs exact", "coherent.md"
    )
    sys.exit(runner.run(load(CoherentTests)))
