import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit, Simulator, state_fidelity


def _teleport(prepare, seed):
    """
    Teleport a state prepared on q0 through a Bell pair (q1, q2) onto q2.
    """
    sim = Simulator(3, seed=seed)
    prepare(sim)
    sim.H(1).CX(1, 2)
    sim.CX(0, 1).H(0)
    if sim.M(1):
        sim.X(2)
    if sim.M(0):
        sim.Z(2)

    return sim


class StandardTests(Question):
    def test_bell_stabilizers(self):
        """
        The Bell state H(0).CX(0,1) has canonical stabilizers +XX, +ZZ.
        """
        sim = Simulator(2).H(0).CX(0, 1)

        self.assertEqual(
            sim.canonical_stabilizers(), ["+XX", "+ZZ"], msg="Bell stabilizers"
        )

    def test_bell_correlation(self):
        """
        Measuring both Bell qubits yields equal outcomes across many seeds.
        """
        for seed in range(200):
            sim = Simulator(2, seed=seed).H(0).CX(0, 1)
            m0 = sim.M(0)
            m1 = sim.M(1)

            self.assertEqual(m0, m1, msg=f"Bell outcomes must agree (seed {seed})")

    def test_ghz_stabilizers(self):
        """
        GHZ on 4 qubits via H + CX chain has the expected canonical stabilizers.
        """
        sim = Simulator(4).H(0).CX(0, 1, 1, 2, 2, 3)
        expected = ["+XXXX", "+ZIIZ", "+IZIZ", "+IIZZ"]

        self.assertEqual(sim.canonical_stabilizers(), expected, msg="GHZ4 stabilizers")

    def test_ghz_correlation(self):
        """
        GHZ all-Z measurements collapse to either all-zero or all-one.
        """
        for seed in range(150):
            sim = Simulator(4, seed=seed).H(0).CX(0, 1, 1, 2, 2, 3)
            outs = sim.M(0, 1, 2, 3)

            self.assertEqual(
                len(set(outs)), 1, msg=f"GHZ outcomes must all agree (seed {seed})"
            )

    def test_teleport_plus(self):
        """
        Teleporting |+> gives <X> = +1 on the output qubit q2.
        """
        for seed in range(12):
            sim = _teleport(lambda s: s.H(0), seed)

            self.assertEqual(
                sim.peek_observable("IIX"), 1, msg=f"|+> teleported <X> (seed {seed})"
            )

    def test_teleport_minus(self):
        """
        Teleporting |-> gives <X> = -1 on the output qubit q2.
        """
        for seed in range(12):
            sim = _teleport(lambda s: s.H(0).Z(0), seed)

            self.assertEqual(
                sim.peek_observable("IIX"), -1, msg=f"|-> teleported <X> (seed {seed})"
            )

    def test_teleport_zero(self):
        """
        Teleporting |0> gives <Z> = +1 on the output qubit q2.
        """
        for seed in range(12):
            sim = _teleport(lambda s: s, seed)

            self.assertEqual(
                sim.peek_observable("IIZ"), 1, msg=f"|0> teleported <Z> (seed {seed})"
            )

    def test_teleport_one(self):
        """
        Teleporting |1> gives <Z> = -1 on the output qubit q2.
        """
        for seed in range(12):
            sim = _teleport(lambda s: s.X(0), seed)

            self.assertEqual(
                sim.peek_observable("IIZ"), -1, msg=f"|1> teleported <Z> (seed {seed})"
            )

    def test_reset_to_zero(self):
        """
        R resets a qubit to |0>, so <Z> = +1 afterward.
        """
        sim = Simulator(1).X(0)
        sim.R(0)

        self.assertEqual(sim.peek_observable("Z"), 1, msg="R must reset to |0>")

    def test_measure_reset(self):
        """
        MR measures the prior value then leaves the qubit in |0>.
        """
        sim = Simulator(1).X(0)
        out = sim.MR(0)

        self.assertEqual(out, 1, msg="MR must report the pre-reset value")

        self.assertEqual(sim.peek_observable("Z"), 1, msg="MR must reset to |0>")

    def test_measure_then_reuse(self):
        """
        A qubit measured and reset can be re-prepared and remeasured.
        """
        sim = Simulator(1, seed=0).H(0)
        sim.MR(0)
        sim.X(0)

        self.assertEqual(sim.M(0), 1, msg="reused qubit must measure 1 after X")

    def test_stabilizer_deterministic(self):
        """
        On a Bell state, measure_pauli of ZZ and XX is a deterministic +1.
        """
        sim = Simulator(2).H(0).CX(0, 1)
        zz, zz_random = sim.measure_pauli("ZZ")
        xx, xx_random = sim.measure_pauli("XX")

        self.assertEqual(zz, 1, msg="Bell ZZ must be +1")

        self.assertFalse(zz_random, msg="Bell ZZ must be deterministic")

        self.assertEqual(xx, 1, msg="Bell XX must be +1")

        self.assertFalse(xx_random, msg="Bell XX must be deterministic")

    def test_stabilizer_random(self):
        """
        On a product state |00>, measuring XX is a random coin flip.
        """
        sim = Simulator(2, seed=0)
        _value, random = sim.measure_pauli("XX")

        self.assertTrue(random, msg="XX on |00> must be random")

    def test_noisy_flip_rate(self):
        """
        X_ERROR(p) flips |0> with empirical frequency close to p.
        """
        c = Circuit(1)
        c.X_ERROR(0, 0.25)
        c.M(0)
        recs = c.sample(5000, seed=2)
        rate = sum(r[0] for r in recs) / len(recs)

        self.assertLess(abs(rate - 0.25), 0.03, msg=f"flip rate {rate:.3f} != 0.25")

    def test_depolarize_flip_rate(self):
        """
        DEPOLARIZE1(0.75) on |0> gives a measured-one frequency near 0.5.
        """
        c = Circuit(1)
        c.DEPOLARIZE1(0, 0.75)
        c.M(0)
        recs = c.sample(5000, seed=3)
        rate = sum(r[0] for r in recs) / len(recs)

        self.assertLess(abs(rate - 0.5), 0.04, msg=f"depolarized {rate:.3f} != 0.5")

    def test_coherent_estimate(self):
        """
        For H(0).RZ(0, theta), estimate of <X> tracks cos(theta).
        """
        for theta in (0.0, math.pi / 4, math.pi / 2, math.pi):
            c = Circuit(1)
            c.H(0)
            c.RZ(0, theta)
            got = c.estimate("X", shots=5000, seed=7)
            want = math.cos(theta)

            self.assertLess(
                abs(got - want),
                0.05,
                msg=f"<X> for RZ({theta:.2f}): got {got:.3f} want {want:.3f}",
            )

    def test_fidelity_identical(self):
        """
        Two identical Bell states have fidelity 1.0.
        """
        a = Simulator(2).H(0).CX(0, 1)
        b = Simulator(2).H(0).CX(0, 1)

        self.assertEqual(state_fidelity(a, b), 1.0, msg="identical states fidelity 1")

    def test_fidelity_orthogonal(self):
        """
        Orthogonal |Phi+> and |Phi-> have fidelity 0.0.
        """
        phi_plus = Simulator(2).H(0).CX(0, 1)
        phi_minus = Simulator(2).X(0).H(0).CX(0, 1)

        self.assertEqual(
            state_fidelity(phi_plus, phi_minus), 0.0, msg="orthogonal fidelity 0"
        )

    def test_fidelity_half(self):
        """
        |0> and |+> overlap with fidelity 0.5.
        """
        zero = Simulator(1)
        plus = Simulator(1).H(0)

        self.assertEqual(state_fidelity(zero, plus), 0.5, msg="|0> vs |+> fidelity 0.5")


if __name__ == "__main__":
    runner = Exam("Standard", "Textbook stabilizer circuits", "standard.md")
    sys.exit(runner.run(load(StandardTests)))
