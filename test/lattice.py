import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from qliff.qec import DetectorErrorModel, DetectorSampler, build_circuit, resolve_tiles


def _square_tiles(rows, cols):
    """
    A contiguous rows x cols grid of square studio tiles.
    """
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append(
                {
                    "kind": "square",
                    "row": r,
                    "col": c,
                    "rotation": 0,
                }
            )

    return out


def _odd_overlap(a, b):
    """
    Opposite-type Pauli supports anticommute iff their overlap is odd.
    """
    return len(set(a) & set(b)) % 2 == 1


class ResolveTilesTests(Question):
    def test_square_patch_shape(self):
        """
        A 3x3 square tiling resolves to 9 data, 8 stabilizers, two logicals.
        """
        num_data, stabs, obs = resolve_tiles(_square_tiles(3, 3))

        self.assertEqual(num_data, 9, msg="3x3 grid has 9 data qubits")

        self.assertEqual(len(stabs), 8, msg="d=3 patch has d^2-1 = 8 stabilizers")

        self.assertEqual(len(obs), 2, msg="a Z and an X logical")

    def test_stabilizers_commute(self):
        """
        Resolved X-checks and Z-checks all share even-size supports (commute).
        """
        _n, stabs, _obs = resolve_tiles(_square_tiles(3, 3))
        xs = [q for k, q in stabs if k == "X"]
        zs = [q for k, q in stabs if k == "Z"]
        bad = [
            (i, j)
            for i, xt in enumerate(xs)
            for j, zt in enumerate(zs)
            if _odd_overlap(xt, zt)
        ]

        self.assertEqual(bad, [], msg="resolved stabilizers must all commute")

    def test_logicals_anticommute(self):
        """
        The resolved Z and X logicals anticommute and commute with their checks.
        """
        _n, stabs, obs = resolve_tiles(_square_tiles(3, 3))
        log_z = dict(obs)["Z"]
        log_x = dict(obs)["X"]
        xs = [q for k, q in stabs if k == "X"]
        zs = [q for k, q in stabs if k == "Z"]

        self.assertTrue(_odd_overlap(log_z, log_x), msg="Z, X logicals anticommute")

        self.assertFalse(
            any(_odd_overlap(log_z, xt) for xt in xs),
            msg="logical Z commutes with X-checks",
        )

        self.assertFalse(
            any(_odd_overlap(log_x, zt) for zt in zs),
            msg="logical X commutes with Z-checks",
        )

    def test_tri_hex_resolve_to_color_families(self):
        """
        Triangular and hexagonal tiles resolve to their triangular-axis families: a
        bounding box of tri/hex tiles maps to a valid CSS patch (X and Z stabilizers
        commute, at least one logical).
        """
        for kind in ("tri", "hex"):
            tiles = [
                {
                    "kind": kind,
                    "row": r,
                    "col": c,
                }
                for r in range(3)
                for c in range(3)
            ]
            _n, stabs, obs = resolve_tiles(tiles)
            xs = [set(s) for t, s in stabs if t == "X"]
            zs = [set(s) for t, s in stabs if t == "Z"]

            self.assertFalse(
                any(len(x & z) % 2 for x in xs for z in zs),
                msg=f"{kind} stabilizers must commute",
            )

            self.assertTrue(
                any(t == "Z" for t, _ in obs), msg=f"{kind} patch must encode a logical"
            )

    def test_mixed_tile_kinds_rejected(self):
        """
        A drawing must be a single lattice kind; mixing square and tri/hex raises.
        """
        with self.assertRaises(ValueError):
            resolve_tiles([
                {
                    "kind": "square",
                    "row": 0,
                    "col": 0,
                },
                {
                    "kind": "tri",
                    "row": 0,
                    "col": 1,
                },
            ])


class BuildCircuitTests(Question):
    def test_qubit_and_detector_counts(self):
        """
        d=3 patch: 9 data + 8 ancilla = 17 qubits, 16 detectors, one Z obs.
        """
        num_data, stabs, obs = resolve_tiles(_square_tiles(3, 3))
        c = build_circuit(num_data, stabs, obs, rounds=3, p=0.0)

        self.assertEqual(c.num_qubits, 17, msg="9 data + 8 ancilla")

        self.assertEqual(len(c.detectors), 16, msg="4 Z-checks x 3 rounds + 4 boundary")

        self.assertEqual(len(c.observables), 1, msg="only the Z logical is readable")

    def test_noiseless_silent(self):
        """
        At p=0 the built circuit fires no detector and no logical flip.
        """
        num_data, stabs, obs = resolve_tiles(_square_tiles(3, 3))
        c = build_circuit(num_data, stabs, obs, rounds=3, p=0.0)
        dets, ob = DetectorSampler(c).sample(128, seed=0)

        self.assertEqual(int(dets.sum()), 0, msg="noiseless detectors must be silent")

        self.assertEqual(int(ob.sum()), 0, msg="noiseless observable must not flip")

    def test_detection_scales_with_noise(self):
        """
        The built circuit's detection-event rate rises with the noise rate.
        """
        num_data, stabs, obs = resolve_tiles(_square_tiles(3, 3))
        lo = DetectorSampler(build_circuit(num_data, stabs, obs, 3, p=0.02)).sample(
            2000, seed=0
        )[0]
        hi = DetectorSampler(build_circuit(num_data, stabs, obs, 3, p=0.1)).sample(
            2000, seed=1
        )[0]

        self.assertGreater(
            float(hi.mean()), float(lo.mean()), msg="detection rate must rise with p"
        )

    def test_dem_graphlike(self):
        """
        The built circuit's DEM is non-empty and fully graphlike.
        """
        num_data, stabs, obs = resolve_tiles(_square_tiles(3, 3))
        dem = DetectorErrorModel(build_circuit(num_data, stabs, obs, 3, p=0.02))
        mechs = len(dem.mechanisms)

        self.assertGreater(mechs, 0, msg="DEM must have mechanisms")

        self.assertEqual(
            len(dem.graphlike_edges()), mechs, msg="every mechanism must be graphlike"
        )

    def test_bad_boundary_rejected(self):
        """
        An unknown boundary keyword raises a clear ValueError.
        """
        num_data, stabs, obs = resolve_tiles(_square_tiles(3, 3))
        with self.assertRaises(ValueError):
            build_circuit(num_data, stabs, obs, 3, p=0.0, boundary="klein")

    def test_periodic_boundary_accepted(self):
        """
        A periodic boundary keyword builds a circuit (topology is in the stabs).
        """
        num_data, stabs, obs = resolve_tiles(_square_tiles(3, 3))
        c = build_circuit(num_data, stabs, obs, 3, p=0.0, boundary="periodic")

        self.assertEqual(c.num_qubits, 17, msg="boundary keyword does not add qubits")


if __name__ == "__main__":
    rc = 0
    rc |= Exam("ResolveTiles", "Studio tile to patch mapping", "resolve_tiles.md").run(
        load(ResolveTilesTests)
    )
    rc |= Exam(
        "BuildCircuit", "Explicit stabilizer circuit builder", "build_circuit.md"
    ).run(load(BuildCircuitTests))
    sys.exit(rc)
