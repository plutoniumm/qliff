import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit
from aaronson.qec import DetectorSampler


def _flip_circuit(p):
    c = Circuit(1)
    c.append("M", [0])
    c.append("X_ERROR", [0], p)
    c.append("M", [0])
    c.detector(-1, -2)
    c.observable(0, -1)

    return c


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
    runner = Exam("QEC", "Detector and observable sampling", "qec.md")
    sys.exit(runner.run(load(QECTests)))
