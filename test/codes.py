import itertools
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coherent import _quasi_sample
from MDR import Exam, Question, load

from qliff.qec import (
    DetectorErrorModel,
    DetectorSampler,
    logical_fidelity,
    rotated_surface_code,
    toric_code,
    unrotated_surface_code,
)
from qliff.qec.codes import (
    SURFACE_PATTERNS,
    SURFACE_STARTS,
    SURFACE_EDGES,
    _rotated_layout,
    _toric_grid,
    _unrotated_grid,
    _unrotated_layout,
)
from qliff.qec.decoder import make_circuit_decoder


def _odd_overlap(a, b):
    """
    Two opposite-type Pauli supports anticommute iff their overlap is odd.
    """
    return len(set(a) & set(b)) % 2 == 1


def _paulis_commute(a, b):
    """
    Two mixed-Pauli supports [(qubit, "X"|"Z")] commute iff they act with
    DIFFERENT (anticommuting) single-qubit Paulis on an even number of shared
    qubits.
    """
    da = dict(a)
    db = dict(b)
    differ = sum(1 for q in set(da) & set(db) if da[q] != db[q])

    return differ % 2 == 0


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


def _counts(c):
    """
    (qubits, detectors, observables) of a built circuit.
    """
    return (c.num_qubits, len(c.detectors), len(c.observables))


def _rotated_combos():
    """
    All (pattern, start, edge) knob combinations for the rotated family.
    """
    return list(itertools.product(SURFACE_PATTERNS, SURFACE_STARTS, SURFACE_EDGES))


class SurfaceVariantTests(Question):
    def test_noiseless_silent(self):
        """
        At p=0 every rotated (pattern x start x edge) and unrotated (pattern x start)
        surface variant fires no detector and no logical flip.
        """
        bad = []
        for pat, st, ed in _rotated_combos():
            c = rotated_surface_code(3, 3, 3, 0.0, pattern=pat, start=st, edge=ed)
            dets, obs = DetectorSampler(c).sample(128, seed=0)
            if int(dets.sum()) + int(obs.sum()) != 0:
                bad.append(f"rotated/{pat}/{st}/{ed}")
        for pat, st in itertools.product(SURFACE_PATTERNS, SURFACE_STARTS):
            c = unrotated_surface_code(3, 3, 0.0, pattern=pat, start=st)
            dets, obs = DetectorSampler(c).sample(128, seed=0)
            if int(dets.sum()) + int(obs.sum()) != 0:
                bad.append(f"unrotated/{pat}/{st}")

        self.assertEqual(bad, [], msg="every variant must be silent at p=0")

    def test_stabilizers_commute(self):
        """
        Every surface variant is a valid stabiliser code: all checks pairwise commute
        and the logical commutes with every stabiliser.
        """
        bad = []
        layouts = [
            (f"rotated/{p}/{s}/{e}", _rotated_layout(3, 3, p, s, e))
            for p, s, e in _rotated_combos()
        ]
        layouts += [
            (f"unrotated/{p}/{s}", _unrotated_layout(3, p, s))
            for p, s in itertools.product(SURFACE_PATTERNS, SURFACE_STARTS)
        ]
        for tag, (_n, stabs, obs, _qb) in layouts:
            sup = [corners for _p, corners in stabs]
            pairs_ok = all(
                _paulis_commute(sup[i], sup[j])
                for i in range(len(sup))
                for j in range(i + 1, len(sup))
            )
            logical_ok = all(_paulis_commute(obs[0], s) for s in sup)
            if not (pairs_ok and logical_ok):
                bad.append(tag)

        self.assertEqual(bad, [], msg="variants must be valid stabiliser codes")

    def test_structure_matches_default(self):
        """
        Each variant is a Clifford conjugation of the css/Z/even default, so its
        qubit / detector / observable counts match it at d=3.
        """
        bad = []
        rref = _counts(rotated_surface_code(3, 3, 3, 0.0))
        for pat, st, ed in _rotated_combos():
            if (
                _counts(
                    rotated_surface_code(3, 3, 3, 0.0, pattern=pat, start=st, edge=ed)
                )
                != rref
            ):
                bad.append(f"rotated/{pat}/{st}/{ed}")
        uref = _counts(unrotated_surface_code(3, 3, 0.0))
        for pat, st in itertools.product(SURFACE_PATTERNS, SURFACE_STARTS):
            if (
                _counts(unrotated_surface_code(3, 3, 0.0, pattern=pat, start=st))
                != uref
            ):
                bad.append(f"unrotated/{pat}/{st}")

        self.assertEqual(bad, [], msg="variant structure must match the default")

    def test_decode_below_trivial(self):
        """
        Under depolarizing noise every rotated variant's exact-MLD logical error rate
        is far below the trivial always-zero predictor -- code distance is preserved.
        """
        for pat, st, ed in _rotated_combos():
            c = rotated_surface_code(3, 3, 3, 0.05, pattern=pat, start=st, edge=ed)
            dets, obs = DetectorSampler(c).sample(2500, seed=7)
            ler = 1.0 - logical_fidelity(
                make_circuit_decoder("mld", c).decode_batch(dets), obs
            )
            trivial = 1.0 - logical_fidelity(np.zeros_like(obs), obs)

            self.assertLess(
                ler,
                trivial - 0.05,
                msg=f"{pat}/{st}/{ed} LER {ler:.3f} !< {trivial:.3f}",
            )

    def test_colouring_equivalent_under_depolarizing(self):
        """
        The Z and X colourings at 2x2 (both dims even, so the colourings are
        genuinely distinct mats) are equivalent under symmetric (depolarizing)
        noise -- their logical error rates agree within sampling.
        """
        out = {}
        for st in ("Z", "X"):
            c = rotated_surface_code(2, 2, 3, 0.06, start=st)
            dets, obs = DetectorSampler(c).sample(6000, seed=2)
            out[st] = 1.0 - logical_fidelity(
                make_circuit_decoder("mld", c).decode_batch(dets), obs
            )

        self.assertLess(
            abs(out["Z"] - out["X"]),
            0.02,
            msg=f"depol Z {out['Z']:.3f} vs X {out['X']:.3f}",
        )

    def test_colouring_identical_when_symmetric(self):
        """
        At 3x3 the two colourings are the SAME mat (a grid rotation maps one onto
        the other -- mat count 1), so their layouts are exactly isomorphic and
        their LERs match under ANY noise, including amplitude damping.
        """
        out = {}
        for st in ("Z", "X"):
            c = rotated_surface_code(3, 3, 2, 0.12, channel="AMPLITUDE_DAMP", start=st)
            dets, obs = _quasi_sample(c, 1500, 7)
            out[st] = 1.0 - logical_fidelity(
                make_circuit_decoder("coherent", c).decode_batch(dets), obs
            )

        self.assertLess(
            abs(out["Z"] - out["X"]),
            0.05,
            msg=f"3x3 AD Z {out['Z']:.3f} vs X {out['X']:.3f} must agree (same mat)",
        )

    def test_colouring_splits_under_amplitude_damping(self):
        """
        At 2x4 (both dims even: X-heavy vs Z-heavy colourings, mat count 4) the
        colourings are NOT equivalent under amplitude damping -- the report's
        central asymmetry: the Z-check imbalance changes AD detection.
        """
        out = {}
        for st in ("Z", "X"):
            c = rotated_surface_code(2, 4, 2, 0.12, channel="AMPLITUDE_DAMP", start=st)
            dets, obs = _quasi_sample(c, 3000, 7)
            out[st] = 1.0 - logical_fidelity(
                make_circuit_decoder("coherent", c).decode_batch(dets), obs
            )

        self.assertGreater(
            abs(out["Z"] - out["X"]),
            0.03,
            msg=f"2x4 AD Z {out['Z']:.3f} vs X {out['X']:.3f} must split",
        )

    def test_unknown_knob_rejected(self):
        """
        An unknown pattern / start / edge raises ValueError naming the supported set.
        """
        with self.assertRaises(ValueError):
            rotated_surface_code(3, 3, 3, 0.0, pattern="bogus")

        with self.assertRaises(ValueError):
            rotated_surface_code(3, 3, 3, 0.0, start="Y")


if __name__ == "__main__":
    rc = 0
    rc |= Exam("Unrotated", "Unrotated planar surface code", "unrotated.md").run(
        load(UnrotatedTests)
    )
    rc |= Exam("Toric", "Periodic toric code", "toric.md").run(load(ToricTests))
    rc |= Exam(
        "SurfaceVariants", "Surface-code stabiliser-pattern variants", "variants.md"
    ).run(load(SurfaceVariantTests))
    sys.exit(rc)
