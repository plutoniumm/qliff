import itertools
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coherent import _quasi_sample
from MDR import Exam, Question, load

from qliff.noise.channel import bias_split
from qliff.qec import (
    DetectorErrorModel,
    DetectorSampler,
    logical_fidelity,
    rotated_surface_code,
    toric_code,
    unrotated_surface_code,
)
from qliff.qec.codes import (
    SURFACE_DEFORMS,
    SURFACE_MEMORIES,
    SURFACE_PATTERNS,
    SURFACE_STARTS,
    SURFACE_EDGES,
    _rotated_layout,
    _sym_commute,
    _sym_vec,
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

        with self.assertRaises(ValueError):
            rotated_surface_code(3, 3, 3, 0.0, memory="Y")


def _ler(circuit, shots, seed):
    """
    Exact-MLD logical error rate for a Pauli-noise circuit.
    """
    dets, obs = DetectorSampler(circuit).sample(shots, seed)
    predictions = make_circuit_decoder("mld", circuit).decode_batch(dets)

    return 1.0 - logical_fidelity(predictions, obs)


def _random_deforms(n, trials, seed):
    """
    `trials` random {qubit: deformation} maps over n qubits.
    """
    rng = random.Random(seed)
    names = sorted(SURFACE_DEFORMS)

    return [
        {q: rng.choice(names) for q in range(n)} for _t in range(trials)
    ]


class DeformationTests(Question):
    def test_y_paulis_commute_symplectically(self):
        """
        Two Y operators on the same qubit commute: the symplectic form XORs its two
        cross terms, where ORing them would drop exactly this case (the bug that
        only surfaces once H_YZ puts Y-type corners on a face).
        """
        y_a = _sym_vec([(0, "Y"), (1, "Z")], 2)
        y_b = _sym_vec([(0, "Y"), (1, "Z")], 2)

        self.assertTrue(_sym_commute(y_a, y_b, 2), msg="Y and Y must commute")

        self.assertFalse(
            _sym_commute(_sym_vec([(0, "Y")], 2), _sym_vec([(0, "X")], 2), 2),
            msg="Y and X must anticommute",
        )

    def test_deform_map_reproduces_xzzx(self):
        """
        The xzzx pattern is exactly "H on the (r+c)-even sublattice", so an explicit
        deform map spelling that out must emit a bit-identical circuit.
        """
        for rows, cols in ((3, 3), (4, 4), (2, 4)):
            spelled = {
                r * cols + col: ("H" if (r + col) % 2 == 0 else "I")
                for r in range(rows)
                for col in range(cols)
            }
            enum = rotated_surface_code(rows, cols, 2, 0.01, pattern="xzzx")
            explicit = rotated_surface_code(rows, cols, 2, 0.01, deform=spelled)

            self.assertEqual(
                enum.instructions,
                explicit.instructions,
                msg=f"{rows}x{cols} deform map must reproduce the xzzx enum",
            )

    def test_deformed_layouts_are_valid_codes(self):
        """
        Random per-qubit deformations (including the Y-type H_YZ) still yield valid
        stabiliser codes in both memories: checks commute pairwise and the logical
        commutes with every check.
        """
        bad = []
        for memory in SURFACE_MEMORIES:
            for i, deform in enumerate(_random_deforms(9, 8, seed=11)):
                _n, stabs, obs, _fr = _rotated_layout(
                    3, 3, "css", "Z", "even", deform, memory
                )
                sup = [corners for _p, corners in stabs]
                pairs_ok = all(
                    _paulis_commute(sup[a], sup[b])
                    for a in range(len(sup))
                    for b in range(a + 1, len(sup))
                )
                if not (pairs_ok and all(_paulis_commute(obs[0], s) for s in sup)):
                    bad.append(f"{memory}/#{i}")

        self.assertEqual(bad, [], msg="deformed layouts must be valid codes")

    def test_deformed_noiseless_silent(self):
        """
        At p=0 every memory and every random deformation fires no detector and no
        logical flip -- the check that catches a wrong frame prep, a wrong CY
        lowering, or a sign error in the deformation.
        """
        bad = []
        for memory in SURFACE_MEMORIES:
            for i, deform in enumerate(_random_deforms(9, 8, seed=13)):
                c = rotated_surface_code(
                    3, 3, 2, 0.0, deform=deform, memory=memory, prep=True
                )
                dets, obs = DetectorSampler(c).sample(128, seed=0)
                if int(dets.sum()) + int(obs.sum()) != 0:
                    bad.append(f"{memory}/#{i}")

        self.assertEqual(bad, [], msg="deformed variants must be silent at p=0")

    def test_z_memory_is_blind_to_z_noise(self):
        """
        A Z-memory prepares logical |0>, so a Z error is harmless BY CONSTRUCTION:
        under pure phase-flip noise no detector fires at all. Correct physics, and
        the reason a Z-memory is a degenerate probe of Z-biased noise.
        """
        c = rotated_surface_code(3, 3, 2, 0.1, channel="Z_ERROR", prep=True)
        dets, obs = DetectorSampler(c).sample(512, seed=5)

        self.assertEqual(int(dets.sum()) + int(obs.sum()), 0, msg="Z-mem sees no Z")

    def test_x_memory_sees_z_noise(self):
        """
        The dual (X-)memory is the experiment to run under Z-biased noise: the same
        phase-flip channel that a Z-memory cannot see does fire its detectors.
        """
        c = rotated_surface_code(3, 3, 2, 0.1, channel="Z_ERROR", memory="X",
                                 prep=True)
        dets, _obs = DetectorSampler(c).sample(512, seed=5)

        self.assertGreater(int(dets.sum()), 0, msg="X-mem must see Z noise")

    def test_memory_duality(self):
        """
        The X-memory under phase-flip noise is the mirror of the Z-memory under
        bit-flip noise, so the two logical error rates agree.
        """
        z_mem = rotated_surface_code(3, 3, 2, 0.05, channel="X_ERROR", prep=True)
        x_mem = rotated_surface_code(3, 3, 2, 0.05, channel="Z_ERROR", memory="X",
                                     prep=True)
        a = _ler(z_mem, 4000, 5)
        b = _ler(x_mem, 4000, 5)

        self.assertLess(abs(a - b), 0.02, msg=f"duality: {a:.4f} vs {b:.4f}")

    def test_bias_half_is_depolarizing(self):
        """
        Z-bias eta = pz / (px + py), so eta = 0.5 is the equal-thirds split: a
        PAULI_CHANNEL_1 at bias 0.5 must match DEPOLARIZE1 exactly.
        """
        depol = rotated_surface_code(3, 3, 2, 0.02, channel="DEPOLARIZE1")
        biased = rotated_surface_code(
            3, 3, 2, 0.02, channel="PAULI_CHANNEL_1", bias=0.5
        )

        self.assertEqual(
            bias_split(0.02, 0.5),
            (0.02 / 3.0, 0.02 / 3.0, 0.02 / 3.0),
            msg="eta=0.5 must be the equal-thirds split",
        )

        self.assertEqual(
            _ler(depol, 3000, 5),
            _ler(biased, 3000, 5),
            msg="eta=0.5 must reproduce depolarizing",
        )

    def test_bias_raises_zero_z_memory_ler(self):
        """
        Raising the Z-bias drives the X-memory's logical error rate UP for css (no
        bias protection) while the Z-memory's stays pinned at zero -- the reason the
        memory knob has to exist before any biased-noise study.
        """
        z_mem, x_mem = [], []
        for eta in (0.5, 30.0):
            for memory, out in (("Z", z_mem), ("X", x_mem)):
                c = rotated_surface_code(
                    3, 3, 2, 0.05, channel="PAULI_CHANNEL_1", bias=eta,
                    memory=memory, prep=True,
                )
                out.append(_ler(c, 3000, 7))

        self.assertEqual(z_mem[1], 0.0, msg=f"Z-mem at eta=30 must be 0, got {z_mem}")

        self.assertGreater(
            x_mem[1], x_mem[0], msg=f"X-mem must worsen with bias, got {x_mem}"
        )

    def test_bad_deform_and_bias_rejected(self):
        """
        An unknown deformation name, an out-of-range qubit, and a bias on a scalar
        channel all raise ValueError rather than silently doing something else.
        """
        with self.assertRaises(ValueError):
            rotated_surface_code(3, 3, 2, 0.0, deform={0: "bogus"})

        with self.assertRaises(ValueError):
            rotated_surface_code(3, 3, 2, 0.0, deform={99: "H"})

        with self.assertRaises(ValueError):
            rotated_surface_code(3, 3, 2, 0.01, channel="DEPOLARIZE1", bias=10.0)


if __name__ == "__main__":
    rc = 0
    rc |= Exam("Unrotated", "Unrotated planar surface code", "unrotated.md").run(
        load(UnrotatedTests)
    )
    rc |= Exam("Toric", "Periodic toric code", "toric.md").run(load(ToricTests))
    rc |= Exam(
        "SurfaceVariants", "Surface-code stabiliser-pattern variants", "variants.md"
    ).run(load(SurfaceVariantTests))
    rc |= Exam(
        "Deformations",
        "Per-qubit Clifford deformations, dual memory, and noise bias",
        "deformations.md",
    ).run(load(DeformationTests))
    sys.exit(rc)
