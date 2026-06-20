import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from qliff.qec import (
    DetectorErrorModel,
    DetectorSampler,
    toric_code,
    unrotated_surface_code,
)
from qliff.qec.codes import _toric_grid, _unrotated_grid


def _odd_overlap(a, b):
    """
    Two opposite-type Pauli supports anticommute iff their overlap is odd.
    """
    return len(set(a) & set(b)) % 2 == 1


class UnrotatedTests(Question):
    def test_stabilizers_commute(self):
        """
        Every unrotated X-check and Z-check share an even-size support (commute).
        """
        _data, x_checks, z_checks = _unrotated_grid(3)
        bad = [
            (xi, zi)
            for xi, xt in x_checks
            for zi, zt in z_checks
            if _odd_overlap(xt, zt)
        ]

        self.assertEqual(bad, [], msg="X/Z stabilizers must all commute")

    def test_logicals_commute_with_stabilizers(self):
        """
        The logical-Z row commutes with X-checks; the logical-X column with Z.
        """
        data, x_checks, z_checks = _unrotated_grid(3)
        side = 2 * 3 - 1
        log_z = [data[(0, col)] for col in range(side) if (0, col) in data]
        log_x = [data[(r, 0)] for r in range(side) if (r, 0) in data]

        self.assertFalse(
            any(_odd_overlap(log_z, xt) for _i, xt in x_checks),
            msg="logical Z must commute with every X stabilizer",
        )

        self.assertFalse(
            any(_odd_overlap(log_x, zt) for _i, zt in z_checks),
            msg="logical X must commute with every Z stabilizer",
        )

    def test_logicals_anticommute(self):
        """
        The unrotated logical-Z row and logical-X column anticommute (overlap 1).
        """
        data, _x, _z = _unrotated_grid(3)
        side = 2 * 3 - 1
        log_z = [data[(0, col)] for col in range(side) if (0, col) in data]
        log_x = [data[(r, 0)] for r in range(side) if (r, 0) in data]

        self.assertTrue(_odd_overlap(log_z, log_x), msg="logical Z, X must anticommute")

    def test_noiseless_silent(self):
        """
        At p=0 the unrotated d=3 memory fires no detector and no logical flip.
        """
        c = unrotated_surface_code(3, 3, 0.0)
        dets, obs = DetectorSampler(c).sample(128, seed=0)

        self.assertEqual(int(dets.sum()), 0, msg="noiseless detectors must be silent")

        self.assertEqual(int(obs.sum()), 0, msg="noiseless observable must not flip")

    def test_structure(self):
        """
        d=3 unrotated code: 13 data + 12 ancilla = 25 qubits, 24 detectors, 1 obs.
        """
        c = unrotated_surface_code(3, 3, 0.0)

        self.assertEqual(c.num_qubits, 25, msg="13 data + 12 ancilla")

        self.assertEqual(len(c.detectors), 24, msg="6 Z-checks x 3 rounds + 6 boundary")

        self.assertEqual(len(c.observables), 1, msg="one logical-Z observable")

    def test_dem_graphlike(self):
        """
        The unrotated surface-code DEM is non-empty and fully graphlike.
        """
        dem = DetectorErrorModel(unrotated_surface_code(3, 3, 0.02))
        mechs = len(dem.mechanisms)

        self.assertGreater(mechs, 0, msg="DEM must have mechanisms")

        self.assertEqual(
            len(dem.graphlike_edges()), mechs, msg="every mechanism must be graphlike"
        )


class ToricTests(Question):
    def test_stabilizers_commute(self):
        """
        Every toric star (X) and plaquette (Z) share an even-size support.
        """
        _n, x_checks, z_checks, _log = _toric_grid(3)
        bad = [
            (i, j)
            for i, xt in enumerate(x_checks)
            for j, zt in enumerate(z_checks)
            if _odd_overlap(xt, zt)
        ]

        self.assertEqual(bad, [], msg="toric stabilizers must all commute")

    def test_logicals_commute_with_stabilizers(self):
        """
        Both toric logical-Z loops commute with every star (X) stabilizer.
        """
        _n, x_checks, _z, logicals = _toric_grid(3)

        for loop in logicals:
            self.assertFalse(
                any(_odd_overlap(loop, xt) for xt in x_checks),
                msg="each logical Z must commute with every X stabilizer",
            )

    def test_two_logicals_independent(self):
        """
        The toric d=3 code carries two distinct logical-Z windings (two qubits).
        """
        _n, _x, _z, logicals = _toric_grid(3)

        self.assertEqual(len(logicals), 2, msg="toric code has two logical qubits")

        self.assertNotEqual(
            set(logicals[0]), set(logicals[1]), msg="the two loops differ"
        )

    def test_logical_x_anticommutes(self):
        """
        A toric logical-X loop anticommutes with its paired logical-Z winding.
        """
        side = 3

        def horiz(r, col):
            return (r % side) * side + (col % side)

        def vert(r, col):
            return side * side + (r % side) * side + (col % side)

        _n, _x, z_checks, logicals = _toric_grid(side)
        log_z1 = logicals[0]
        log_x1 = [horiz(r, 0) for r in range(side)]

        self.assertTrue(
            _odd_overlap(log_z1, log_x1), msg="logical X1, Z1 must anticommute"
        )

        self.assertFalse(
            any(_odd_overlap(log_x1, zt) for zt in z_checks),
            msg="logical X1 must commute with every Z plaquette",
        )

    def test_noiseless_silent(self):
        """
        At p=0 the toric d=3 memory fires no detector and no logical flip.
        """
        c = toric_code(3, 3, 0.0)
        dets, obs = DetectorSampler(c).sample(128, seed=0)

        self.assertEqual(int(dets.sum()), 0, msg="noiseless detectors must be silent")

        self.assertEqual(int(obs.sum()), 0, msg="noiseless observables must not flip")

    def test_structure(self):
        """
        d=3 toric code: 18 data + 18 ancilla = 36 qubits, 36 detectors, 2 obs.
        """
        c = toric_code(3, 3, 0.0)

        self.assertEqual(c.num_qubits, 36, msg="2*d^2 data + 2*d^2 ancilla")

        self.assertEqual(len(c.detectors), 36, msg="9 Z-checks x 3 rounds + 9 boundary")

        self.assertEqual(len(c.observables), 2, msg="two logical-Z observables")

    def test_dem_graphlike(self):
        """
        The toric surface-code DEM is non-empty and fully graphlike.
        """
        dem = DetectorErrorModel(toric_code(3, 3, 0.02))
        mechs = len(dem.mechanisms)

        self.assertGreater(mechs, 0, msg="DEM must have mechanisms")

        self.assertEqual(
            len(dem.graphlike_edges()), mechs, msg="every mechanism must be graphlike"
        )


if __name__ == "__main__":
    rc = 0
    rc |= Exam("Unrotated", "Unrotated planar surface code", "unrotated.md").run(
        load(UnrotatedTests)
    )
    rc |= Exam("Toric", "Periodic toric code", "toric.md").run(load(ToricTests))
    sys.exit(rc)
