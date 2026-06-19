import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from qliff import Circuit
from qliff.qec import (
    DetectorErrorModel,
    DetectorSampler,
    logical_fidelity,
    repetition_code,
    rotated_surface_code,
)


def _flip_circuit(p):
    c = Circuit(1)
    c.append("M", [0])
    c.append("X_ERROR", [0], p)
    c.append("M", [0])
    c.detector(-1, -2)
    c.observable(0, -1)

    return c


def _rep_round(p):
    c = Circuit(5)
    c.append("X_ERROR", [1], p)
    c.append("CX", [0, 3, 1, 3, 1, 4, 2, 4])
    c.append("MR", [3, 4])
    c.detector(-2)
    c.detector(-1)

    return c


class CodeTests(Question):
    def test_rep_detector_count(self):
        """
        The repetition code declares rounds*(d-1) + (d-1) detectors and one obs.
        """
        d, rounds = 5, 3
        c = repetition_code(d, rounds, 0.05)
        expect = rounds * (d - 1) + (d - 1)

        self.assertEqual(len(c.detectors), expect, msg=f"detector count != {expect}")

        self.assertEqual(len(c.observables), 1, msg="exactly one logical observable")

    def test_rep_dem_graphlike(self):
        """
        The repetition-code DEM is non-empty and almost entirely graphlike.
        """
        dem = DetectorErrorModel(repetition_code(5, 3, 0.05))
        mechs = len(dem.mechanisms)
        graphlike = len(dem.graphlike_edges())

        self.assertGreater(mechs, 0, msg="DEM must have mechanisms")

        self.assertGreaterEqual(
            graphlike, 0.9 * mechs, msg="most mechanisms must flip <= 2 detectors"
        )

    def test_rep_detection_scales(self):
        """
        The repetition-code detection-event rate grows with the error rate.
        """
        low = DetectorSampler(repetition_code(5, 3, 0.02)).sample(2000, seed=0)[0]
        high = DetectorSampler(repetition_code(5, 3, 0.1)).sample(2000, seed=1)[0]
        lo = float(low.mean())
        hi = float(high.mean())

        self.assertGreater(hi, lo, msg=f"rate must rise with p: {lo:.3f} -> {hi:.3f}")

    def test_surface_dem_graphlike(self):
        """
        The rotated surface-code DEM is non-empty and fully graphlike.
        """
        dem = DetectorErrorModel(rotated_surface_code(3, 3, 0.01))
        mechs = len(dem.mechanisms)
        graphlike = len(dem.graphlike_edges())

        self.assertGreater(mechs, 0, msg="surface DEM must have mechanisms")

        self.assertEqual(
            graphlike, mechs, msg="every surface mechanism must be graphlike"
        )

    def test_surface_structure(self):
        """
        The distance-3 surface code has 9 data qubits, 16 detectors and one obs.
        """
        c = rotated_surface_code(3, 3, 0.01)

        self.assertEqual(len(c.detectors), 16, msg="d=3 detector count")

        self.assertEqual(len(c.observables), 1, msg="one logical observable")

    def test_surface_noiseless_silent(self):
        """
        With no noise every surface detector and observable stays at zero.
        """
        c = rotated_surface_code(3, 3, 0.0)
        dets, obs = DetectorSampler(c).sample(128, seed=0)

        self.assertEqual(int(dets.sum()), 0, msg="noiseless detectors must be silent")

        self.assertEqual(int(obs.sum()), 0, msg="noiseless observable must not flip")

    def test_logical_fidelity(self):
        """
        logical_fidelity returns 1 - mean mismatch over predictions vs observed.
        """
        pred = np.array([[0], [1], [0], [0]], dtype=np.uint8)
        obs = np.array([[0], [0], [0], [0]], dtype=np.uint8)
        fid = logical_fidelity(pred, obs)

        self.assertLess(abs(fid - 0.75), 1e-9, msg=f"fidelity {fid} != 0.75")


class DEMTests(Question):
    def test_single_mechanism(self):
        """
        The flip circuit yields one mechanism flipping detector 0 + observable 0.
        """
        dem = DetectorErrorModel(_flip_circuit(0.1))
        p, dets, obs = dem.mechanisms[0]

        self.assertEqual(len(dem.mechanisms), 1, msg="expected one mechanism")

        self.assertEqual(dets, frozenset({0}), msg="should flip detector 0")

        self.assertEqual(obs, frozenset({0}), msg="should flip observable 0")

        self.assertLess(abs(p - 0.1), 1e-9, msg=f"prob {p} != 0.1")

    def test_check_matrix(self):
        """
        check_matrix returns aligned H / priors / observable arrays.
        """
        h, priors, obs_mat = DetectorErrorModel(_flip_circuit(0.1)).check_matrix()

        self.assertEqual(h.shape, (1, 1), msg="H shape")

        self.assertEqual(int(h[0, 0]), 1, msg="mechanism flips detector 0")

        self.assertEqual(obs_mat.shape, (1, 1), msg="observable matrix shape")

        self.assertLess(abs(priors[0] - 0.1), 1e-9, msg="prior probability")

    def test_graphlike_edge_two_detectors(self):
        """
        A data-qubit error flips two stabilizers, giving a matching edge.
        """
        dem = DetectorErrorModel(_rep_round(0.05))
        sigs = [tuple(sorted(d)) for _, d, _ in dem.mechanisms]
        edges = dem.graphlike_edges()

        self.assertIn((0, 1), sigs, msg="X on the middle qubit flips detectors 0 and 1")

        self.assertTrue(
            any(e[0] == (0, 1) for e in edges), msg="edge over detectors 0,1"
        )


class QECTests(Question):
    def test_no_noise_no_detections(self):
        """
        With no noise, no detectors fire and no logical flips occur.
        """
        dets, obs = DetectorSampler(_flip_circuit(0.0)).sample(64, seed=0)

        self.assertEqual(int(dets.sum()), 0, msg="no error must give no detections")

        self.assertEqual(int(obs.sum()), 0, msg="no error must give no flips")

    def test_certain_error_detected(self):
        """
        A certain X error fires the detector and flips the observable.
        """
        dets, obs = DetectorSampler(_flip_circuit(1.0)).sample(64, seed=1)

        self.assertTrue(
            bool((dets == 1).all()), msg="X_ERROR(1) must fire the detector"
        )

        self.assertTrue(
            bool((obs == 1).all()), msg="X_ERROR(1) must flip the observable"
        )

    def test_detection_rate(self):
        """
        Detection-event frequency tracks the error probability.
        """
        dets, _obs = DetectorSampler(_flip_circuit(0.2)).sample(5000, seed=2)
        rate = float(dets.mean())

        self.assertLess(abs(rate - 0.2), 0.03, msg=f"detection rate {rate:.3f} != 0.2")

    def test_shapes(self):
        """
        Sampling returns (shots, n_detectors) and (shots, n_observables).
        """
        dets, obs = DetectorSampler(_flip_circuit(0.1)).sample(10, seed=3)

        self.assertEqual(dets.shape, (10, 1), msg="detector array shape")

        self.assertEqual(obs.shape, (10, 1), msg="observable array shape")


if __name__ == "__main__":
    rc = 0
    rc |= Exam("Codes", "QEC code generators", "codes.md").run(load(CodeTests))
    rc |= Exam("DEM", "Detector error model + decoder exporters", "dem.md").run(
        load(DEMTests)
    )
    rc |= Exam("QEC", "Detector and observable sampling", "qec.md").run(load(QECTests))
    sys.exit(rc)
