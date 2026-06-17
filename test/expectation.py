import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Simulator, PauliString


class ExpectationTests(Question):
    def test_z_on_zero(self):
        """
        <Z> = +1 on |0>.
        """
        self.assertEqual(
            Simulator(1).peek_observable("Z"), 1, msg="<Z> on |0> must be +1"
        )

    def test_z_on_one(self):
        """
        <Z> = -1 on |1>.
        """
        self.assertEqual(
            Simulator(1).X(0).peek_observable("Z"), -1, msg="<Z> on |1> must be -1"
        )

    def test_x_on_plus(self):
        """
        <X> = +1 on |+>.
        """
        self.assertEqual(
            Simulator(1).H(0).peek_observable("X"), 1, msg="<X> on |+> must be +1"
        )

    def test_x_on_minus(self):
        """
        <X> = -1 on |->.
        """
        self.assertEqual(
            Simulator(1).H(0).Z(0).peek_observable("X"), -1, msg="<X> on |-> must be -1"
        )

    def test_z_on_plus_is_zero(self):
        """
        <Z> = 0 on |+> (anticommutes with the stabilizer).
        """
        self.assertEqual(
            Simulator(1).H(0).peek_observable("Z"), 0, msg="<Z> on |+> must be 0"
        )

    def test_bell_observables(self):
        """
        Bell state: <ZZ>=<XX>=+1, <YY>=-1, <ZI>=0.
        """
        s = Simulator(2).H(0).CX(0, 1)

        self.assertEqual(s.peek_observable("ZZ"), 1, msg="Bell <ZZ> must be +1")

        self.assertEqual(s.peek_observable("XX"), 1, msg="Bell <XX> must be +1")

        self.assertEqual(s.peek_observable("YY"), -1, msg="Bell <YY> must be -1")

        self.assertEqual(s.peek_observable("ZI"), 0, msg="Bell <ZI> must be 0")

    def test_signed_observable(self):
        """
        A '-' prefix flips the expectation.
        """
        self.assertEqual(
            Simulator(1).peek_observable("-Z"), -1, msg="'-' prefix must flip <Z>"
        )

    def test_pauli_string_arg(self):
        """
        peek_observable accepts a PauliString.
        """
        s = Simulator(2).H(0).CX(0, 1)

        self.assertEqual(
            s.peek_observable(PauliString.parse("ZZ")),
            1,
            msg="PauliString arg must give <ZZ>=+1",
        )


if __name__ == "__main__":
    sys.exit(
        Exam(
            "Expectation",
            "Pauli expectation values on stabilizer states",
            "expectation.md",
        ).run(load(ExpectationTests))
    )
