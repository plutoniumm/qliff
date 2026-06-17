import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit
from aaronson.noise import AmplitudeDamping

_Z = np.array([[1, 0], [0, -1]], dtype=complex)
_X = np.array([[0, 1], [1, 0]], dtype=complex)


def _evolve(rho, p):
    e0 = np.array([[1, 0], [0, math.sqrt(1 - p)]], dtype=complex)
    e1 = np.array([[0, math.sqrt(p)], [0, 0]], dtype=complex)

    return e0 @ rho @ e0.conj().T + e1 @ rho @ e1.conj().T


def _weights(p):
    (qi, _), (qz, _), (qr, _) = AmplitudeDamping(p).branches([0])

    return qi, qz, qr


class AmplitudeTests(Question):
    def test_branch_weights(self):
        """
        Branch weights equal the analytic q_I, q_Z (negative), q_R = p.
        """
        for p in (0.01, 0.05, 0.1, 0.2, 0.3):
            qi, qz, qr = _weights(p)
            root = math.sqrt(1 - p)

            self.assertLess(abs(qi - (1 - p + root) / 2), 1e-12, msg=f"q_I at p={p}")

            self.assertLess(abs(qz - (1 - p - root) / 2), 1e-12, msg=f"q_Z at p={p}")

            self.assertLess(abs(qr - p), 1e-12, msg=f"q_R at p={p}")

            self.assertLess(qz, 0.0, msg=f"q_Z must be negative at p={p}")

    def test_branch_ops(self):
        """
        Branches are identity, Z, and reset-to-|0>, identity first.
        """
        branches = AmplitudeDamping(0.1).branches([0])
        ops = [o for _, o in branches]

        self.assertEqual(ops[0], [], msg="identity branch must be first and empty")

        self.assertEqual(ops[1], [("Z", (0,))], msg="second branch is Z")

        self.assertEqual(ops[2], [("R", (0,))], msg="third branch is reset")

    def test_overhead_and_negativity(self):
        """
        Fault weight q_Z + q_R is ~3p/4, full overhead ~1, negativity -> 1/3.
        """
        for p in (0.001, 0.0001):
            qi, qz, qr = _weights(p)
            root = math.sqrt(1 - p)
            fault = qz + qr
            eta = abs(qz) / fault
            gamma = qi + abs(qz) + qr
            closed = 1.0 + (root - (1 - p))

            self.assertLess(
                abs(fault - 3 * p / 4) / (3 * p / 4), 0.01, msg=f"fault ~3p/4 at p={p}"
            )

            self.assertLess(abs(eta - 1.0 / 3.0), 0.01, msg=f"negativity eta at p={p}")

            self.assertLess(
                abs(gamma - closed), 1e-12, msg=f"overhead closed form at p={p}"
            )

            self.assertLess(gamma, 1.0 + p, msg=f"overhead nearly 1 at p={p}")

    def test_decay_on_one(self):
        """
        Damping |1> gives <Z> ~ 2p-1, matching exact density-matrix evolution.
        """
        for p in (0.1, 0.2, 0.3):
            c = Circuit(1)
            c.append("X", [0])
            c.append("AMPLITUDE_DAMP", [0], p)
            est = c.estimate("Z", 40000, method="stratified", seed=5)
            rho = np.array([[0, 0], [0, 1]], dtype=complex)
            exact = float(np.real(np.trace(_evolve(rho, p) @ _Z)))

            self.assertLess(abs(exact - (2 * p - 1)), 1e-9, msg=f"exact <Z> at p={p}")

            self.assertLess(
                abs(est - exact), 0.03, msg=f"<Z> est {est:.3f} vs {exact:.3f}"
            )

    def test_coherence_on_plus(self):
        """
        Off-diagonal coherence on |+> decays by sqrt(1-p): <X> ~ sqrt(1-p).
        """
        for p in (0.1, 0.2, 0.4):
            c = Circuit(1)
            c.append("H", [0])
            c.append("AMPLITUDE_DAMP", [0], p)
            est = c.estimate("X", 40000, method="stratified", seed=6)
            rho = 0.5 * np.array([[1, 1], [1, 1]], dtype=complex)
            exact = float(np.real(np.trace(_evolve(rho, p) @ _X)))

            self.assertLess(
                abs(exact - math.sqrt(1 - p)), 1e-9, msg=f"exact <X> at p={p}"
            )

            self.assertLess(
                abs(est - exact), 0.03, msg=f"<X> est {est:.3f} vs {exact:.3f}"
            )


if __name__ == "__main__":
    runner = Exam("Amplitude", "Amplitude-damping channel vs exact", "amplitude.md")
    sys.exit(runner.run(load(AmplitudeTests)))
