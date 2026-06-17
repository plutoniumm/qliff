import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit, Simulator
from aaronson.noise import BitFlip


class CircuitTests(Question):
    def test_bell_matches_direct(self):
        """
        A Bell circuit reproduces the directly-built Bell state.
        """
        c = Circuit().append("H", 0).append("CX", [0, 1])
        got = c.run(seed=1).canonical_stabilizers()
        want = Simulator(2).H(0).CX(0, 1).canonical_stabilizers()

        self.assertEqual(got, want, msg="circuit Bell must match direct Bell")

    def test_fluent_matches_append(self):
        """
        Fluent gate methods build the same instructions as append.
        """
        fluent = Circuit(2).H(0).CX(0, 1).M(0, 1)
        low = Circuit(2).append("H", 0).append("CX", [0, 1]).append("M", [0, 1])

        self.assertEqual(
            fluent.instructions, low.instructions, msg="fluent must equal append"
        )

    def test_custom_channel_round_trips(self):
        """
        A custom Channel added via noise() is sampled like a built-in one.
        """
        c = Circuit(1).X(0).noise(BitFlip(1.0), 0).M(0)
        record = c.sample(1, seed=0)[0]

        self.assertEqual(record, [0], msg="certain bit-flip must undo the X")

    def test_is_pauli_and_estimate(self):
        """
        is_pauli flags coherent noise and estimate stays unbiased for it.
        """
        pauli = Circuit(1).H(0).DEPOLARIZE1(0, 0.1)

        self.assertTrue(pauli.is_pauli, msg="depolarizing is a Pauli channel")

        coherent = Circuit(1).H(0).RZ(0, 0.0)

        self.assertFalse(coherent.is_pauli, msg="RZ is not a Pauli channel")

        est = coherent.estimate("X", 4000, seed=0)

        self.assertGreater(est, 0.9, msg="RZ(0) leaves <X> at +1")

    def test_measurements_recorded(self):
        """
        Measurement instructions populate the record in order.
        """
        c = Circuit().append("X", 0).append("M", [0, 1])

        self.assertEqual(
            c.run().measure_record, [1, 0], msg="measurements must record in order"
        )

    def test_reproducible_with_seed(self):
        """
        The same seed gives the same measurement record.
        """
        c = Circuit(2).append("H", 0).append("CX", [0, 1]).append("M", [0, 1])

        self.assertEqual(
            c.run(seed=42).measure_record,
            c.run(seed=42).measure_record,
            msg="same seed must reproduce the record",
        )

    def test_infers_num_qubits(self):
        """
        num_qubits grows to cover the targets used.
        """
        c = Circuit().append("H", 0).append("CX", [0, 3])

        self.assertEqual(c.num_qubits, 4, msg="num_qubits must cover target index 3")

    def test_len_and_repr(self):
        """
        len and repr reflect the instruction list.
        """
        c = Circuit().append("H", 0).append("CX", [0, 1])

        self.assertEqual(len(c), 2, msg="len must equal instruction count")

        self.assertIn("Circuit", repr(c), msg="repr must mention Circuit")

    def test_unknown_instruction_raises(self):
        """
        Noise/QEC instructions are not runnable by the bare runner yet.
        """
        c = Circuit(1).append("DEPOLARIZE1", [0], 0.1)
        with self.assertRaises(NotImplementedError):
            c.run()


if __name__ == "__main__":
    sys.exit(
        Exam("Circuit", "Circuit IR build and run", "circuit.md").run(
            load(CircuitTests)
        )
    )
