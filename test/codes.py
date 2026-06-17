import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from MDR import Exam, Question, load

from aaronson.qec import DetectorErrorModel, DetectorSampler
from aaronson.qec import repetition_code, rotated_surface_code, logical_fidelity


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


if __name__ == "__main__":
    runner = Exam("Codes", "QEC code generators", "codes.md")
    sys.exit(runner.run(load(CodeTests)))
