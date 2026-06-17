import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import PauliString


class PauliTests(Question):
    def test_parse_repr_roundtrip(self):
        """
        Parsing then repr is the identity for signed Paulis.
        """
        for s in ("+XZ", "-Y", "+III", "-XYZ"):
            self.assertEqual(
                repr(PauliString.parse(s)), s, msg="parse/repr must round-trip"
            )

    def test_identity(self):
        """
        identity(n) is +I...I.
        """
        self.assertEqual(
            repr(PauliString.identity(3)), "+III", msg="identity(3) must be +III"
        )

    def test_from_sparse(self):
        """
        from_sparse places single-qubit Paulis.
        """
        self.assertEqual(
            repr(
                PauliString.from_sparse(
                    3,
                    {
                        0: "X",
                        2: "Z",
                    },
                )
            ),
            "+XIZ",
            msg="from_sparse must place X and Z",
        )

    def test_commutation(self):
        """
        X and Z anticommute; XX and ZZ commute.
        """
        self.assertFalse(
            PauliString.parse("X").commutes_with(PauliString.parse("Z")),
            msg="X and Z must anticommute",
        )

        self.assertTrue(
            PauliString.parse("XX").commutes_with(PauliString.parse("ZZ")),
            msg="XX and ZZ must commute",
        )

    def test_mul_xy_is_iz(self):
        """
        X * Y = +iZ.
        """
        self.assertEqual(
            repr(PauliString.parse("X") * PauliString.parse("Y")),
            "+iZ",
            msg="X * Y must be +iZ",
        )

    def test_mul_yx_is_minus_iz(self):
        """
        Y * X = -iZ.
        """
        self.assertEqual(
            repr(PauliString.parse("Y") * PauliString.parse("X")),
            "-iZ",
            msg="Y * X must be -iZ",
        )

    def test_mul_zz_is_identity(self):
        """
        Z * Z = +I.
        """
        self.assertEqual(
            repr(PauliString.parse("Z") * PauliString.parse("Z")),
            "+I",
            msg="Z * Z must be +I",
        )

    def test_mul_signs(self):
        """
        (-X)*(Y) carries the - through: = -iZ.
        """
        self.assertEqual(
            repr(PauliString.parse("-X") * PauliString.parse("Y")),
            "-iZ",
            msg="(-X) * Y must be -iZ",
        )


if __name__ == "__main__":
    sys.exit(
        Exam("Pauli", "PauliString parsing and algebra", "pauli.md").run(
            load(PauliTests)
        )
    )
