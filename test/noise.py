import math
import os
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit
from aaronson.noise import AmplitudeDamping, Sampler

_H = np.array([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2)
_PAULIS = {
    "X": np.array([[0, 1], [1, 0]], dtype=complex),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "Z": np.array([[1, 0], [0, -1]], dtype=complex),
}
_Z = np.array([[1, 0], [0, -1]], dtype=complex)
_X = np.array([[0, 1], [1, 0]], dtype=complex)


def _bitflip_circuit(p):
    c = Circuit(1)
    c.append("X_ERROR", [0], p)
    c.append("M", [0])

    return c


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


def _evolve(rho, p):
    e0 = np.array([[1, 0], [0, math.sqrt(1 - p)]], dtype=complex)
    e1 = np.array([[0, math.sqrt(p)], [0, 0]], dtype=complex)

    return e0 @ rho @ e0.conj().T + e1 @ rho @ e1.conj().T


def _weights(p):
    (qi, _), (qz, _), (qr, _) = AmplitudeDamping(p).branches([0])

    return qi, qz, qr


def _dephasing(n, p):
    c = Circuit(n)
    for q in range(n):
        c.append("H", [q])
    for q in range(n):
        c.append("Z_ERROR", [q], p)

    return c


class NoiseTests(Question):
    def test_x_error_certain(self):
        """
        X_ERROR(1.0) flips |0> to |1> on every shot.
        """
        recs = Sampler(_bitflip_circuit(1.0)).sample(64, seed=0)

        self.assertTrue(all(r == [1] for r in recs), msg="X_ERROR(1) must always flip")

    def test_zero_probability(self):
        """
        p=0 noise leaves |0> measured as 0.
        """
        recs = Sampler(_bitflip_circuit(0.0)).sample(64, seed=1)

        self.assertTrue(all(r == [0] for r in recs), msg="p=0 must do nothing")

    def test_bitflip_rate(self):
        """
        BitFlip(p) flips |0> with empirical frequency about p.
        """
        recs = Sampler(_bitflip_circuit(0.25)).sample(5000, seed=2)
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
        recs = Sampler(c).sample(5000, seed=3)
        ones = sum(r[0] for r in recs) / len(recs)

        self.assertLess(abs(ones - 0.5), 0.04, msg=f"depolarized {ones} != 0.5")

    def test_expect_decays(self):
        """
        Dephasing drives <X> from +1 toward 0 as p grows.
        """
        c = Circuit(1)
        c.append("H", [0])
        c.append("Z_ERROR", [0], 0.5)
        est = Sampler(c).expect("X", 5000, seed=4)

        self.assertLess(abs(est), 0.05, msg=f"<X> should decay to ~0, got {est}")


class CoherentTests(Question):
    def test_rz_on_plus_matches_exact(self):
        """
        Importance sampling of RZ(theta) on |+> reproduces exact <X> and <Y>.
        """
        for theta in (0.0, math.pi / 6, math.pi / 4, math.pi / 2, math.pi):
            c = Circuit(1)
            c.append("H", [0])
            c.append("RZ", [0], theta)
            sampler = Sampler(c)
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
            sampler = Sampler(c)
            for obs in ("Z", "Y"):
                got = sampler.expect(obs, 20000, seed=11)
                want = _exact([_rx(theta)], obs)

                self.assertLess(
                    abs(got - want),
                    0.06,
                    msg=f"RX({theta:.2f}) <{obs}>: got {got:.3f} want {want:.3f}",
                )

    def test_sample_rejects_coherent(self):
        """
        Record sampling refuses a non-Pauli (coherent) channel.
        """
        c = Circuit(1)
        c.append("RZ", [0], 0.3)
        c.append("M", [0])

        with self.assertRaises(ValueError):
            Sampler(c).sample(8)

    def test_clifford_rotation_is_exact(self):
        """
        RZ(pi/2) is the Clifford S (gamma = 1), so <Y> on |+> is exactly 1.
        """
        c = Circuit(1)
        c.append("H", [0])
        c.append("RZ", [0], math.pi / 2)
        got = Sampler(c).expect("Y", 2000, seed=1)

        self.assertLess(
            abs(got - 1.0), 1e-9, msg=f"RZ(pi/2) <Y> should be 1, got {got}"
        )


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
            est = c.estimate("Z", 40000, stratify=True, seed=5)
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
            est = c.estimate("X", 40000, stratify=True, seed=6)
            rho = 0.5 * np.array([[1, 1], [1, 1]], dtype=complex)
            exact = float(np.real(np.trace(_evolve(rho, p) @ _X)))

            self.assertLess(
                abs(exact - math.sqrt(1 - p)), 1e-9, msg=f"exact <X> at p={p}"
            )

            self.assertLess(
                abs(est - exact), 0.03, msg=f"<X> est {est:.3f} vs {exact:.3f}"
            )


class StratifiedTests(Question):
    def test_unbiased_dephasing(self):
        """
        Stratified <X..X> matches the exact (1-2p)^n for independent dephasing.
        """
        n, p = 6, 0.1
        exact = (1.0 - 2.0 * p) ** n
        got = Sampler(_dephasing(n, p)).expect("X" * n, 3000, seed=0, stratify=True)

        self.assertLess(abs(got - exact), 0.01, msg=f"got {got:.4f} want {exact:.4f}")

    def test_beats_flat_variance(self):
        """
        Stratifying has lower estimator spread than flat sampling here, where
        the observable depends only on the fault count.
        """
        obs = "X" * 6
        circuit = _dephasing(6, 0.1)
        strat = [
            Sampler(circuit).expect(obs, 1500, seed=s, stratify=True) for s in range(8)
        ]
        flat = [Sampler(circuit).expect(obs, 1500, seed=s) for s in range(8)]

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
        strat = Sampler(c).expect("X", 20000, seed=1, stratify=True)
        flat = Sampler(c).expect("X", 20000, seed=2)

        self.assertLess(
            abs(strat - flat), 0.05, msg=f"strat {strat:.3f} vs flat {flat:.3f}"
        )


if __name__ == "__main__":
    rc = 0
    rc |= Exam("Noise", "Pauli-noise Monte-Carlo sampling", "noise.md").run(
        load(NoiseTests)
    )
    rc |= Exam(
        "Coherent", "Coherent-noise importance sampling vs exact", "coherent.md"
    ).run(load(CoherentTests))
    rc |= Exam("Amplitude", "Amplitude-damping channel vs exact", "amplitude.md").run(
        load(AmplitudeTests)
    )
    rc |= Exam("Stratified", "Stratified importance sampling", "stratified.md").run(
        load(StratifiedTests)
    )
    sys.exit(rc)
