import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from aaronson import Circuit
from aaronson.qec import DetectorErrorModel


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


if __name__ == "__main__":
    runner = Exam("DEM", "Detector error model + decoder exporters", "dem.md")
    sys.exit(runner.run(load(DEMTests)))
