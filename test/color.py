import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from qliff.qec import DetectorSampler, color, logical_fidelity
from qliff.qec.dem import DetectorErrorModel
from qliff.qec.decoder import make_circuit_decoder

# The triangular-axis families (qec/color.py): a 6.6.6 honeycomb COLOR code plus the
# triangular and kagome surface codes, all on a periodic triangular torus. These
# checks mirror the surface-family tests in codes.py: each must be a valid CSS code
# (X / Z stabilisers commute), encode a logical, stay silent without noise, scale its
# distance, and decode below the trivial predictor.

FAMILIES = ["hex_color", "triangular", "kagome"]
_LAYOUT = {
    "hex_color": color.hex_color_layout,
    "triangular": color.triangular_layout,
    "kagome": color.kagome_layout,
}


def _supports(stabs, kind):
    return [set(s) for t, s in stabs if t == kind]


def _z_logical_weights(obs):
    return [len(s) for t, s in obs if t == "Z"]


class ColorCodeTests(Question):
    def test_css_commute(self):
        """
        Every X-stabiliser and Z-stabiliser of each family share an even-size support
        (they commute) -- the defining validity condition of a CSS code.
        """
        bad = []
        for fam in FAMILIES:
            _n, stabs, _obs = _LAYOUT[fam](3)
            xs = _supports(stabs, "X")
            zs = _supports(stabs, "Z")
            if any(len(x & z) % 2 for x in xs for z in zs):
                bad.append(fam)

        self.assertEqual(bad, [], msg="X and Z stabilizers must commute")

    def test_encodes_logical(self):
        """
        Each family encodes at least one logical qubit (the GF(2) layout finds a
        Z-logical), so an LER curve is well defined.
        """
        for fam in FAMILIES:
            _n, _stabs, obs = _LAYOUT[fam](3)

            self.assertGreater(
                len(_z_logical_weights(obs)), 0, msg=f"{fam} encodes no logical"
            )

    def test_noiseless_silent(self):
        """
        At p=0 every family's memory fires no detector and flips no logical.
        """
        bad = []
        for fam in FAMILIES:
            c = color.color_code(fam, 3, 3, 0.0)
            dets, obs = DetectorSampler(c).sample(128, seed=0)
            if int(dets.sum()) + int(obs.sum()) != 0:
                bad.append(fam)

        self.assertEqual(bad, [], msg="every family must be silent at p=0")

    def test_distance_scales(self):
        """
        A larger requested distance yields a heavier minimum Z-logical -- the codes are
        genuine families, not a single fixed patch.
        """
        for fam in FAMILIES:
            small = min(_z_logical_weights(_LAYOUT[fam](3)[2]))
            big = min(_z_logical_weights(_LAYOUT[fam](4)[2]))

            self.assertGreater(
                big, small, msg=f"{fam} logical weight must grow: {small} -> {big}"
            )

    def test_hex_is_color_code_nongraphlike(self):
        """
        The honeycomb color code has weight-3 hyperedges (a data error flips 3 face
        detectors), so its DEM is NOT graphlike and MWPM is steered away to a
        hyperedge-capable decoder.
        """
        dem = DetectorErrorModel(color.color_code("hex_color", 3, 3, 0.03))

        self.assertFalse(dem.is_graphlike(), msg="hex color DEM must be non-graphlike")

        with self.assertRaises(ValueError):
            make_circuit_decoder("mwpm", color.color_code("hex_color", 3, 3, 0.03))

    def test_triangular_kagome_graphlike(self):
        """
        The triangular and kagome surface codes are graphlike (every fault flips <= 2
        detectors), so matching applies to them.
        """
        for fam in ("triangular", "kagome"):
            dem = DetectorErrorModel(color.color_code(fam, 3, 3, 0.03))

            self.assertTrue(dem.is_graphlike(), msg=f"{fam} DEM must be graphlike")

    def test_decode_below_trivial(self):
        """
        BP+OSD drives every family's logical error rate well below the trivial
        always-zero predictor under depolarizing noise -- the codes correct.
        """
        for fam in FAMILIES:
            c = color.color_code(fam, 3, 3, 0.04)
            dets, obs = DetectorSampler(c).sample(1500, seed=7)
            ler = 1.0 - logical_fidelity(make_circuit_decoder("bposd", c).decode_batch(dets), obs)
            trivial = 1.0 - logical_fidelity(np.zeros_like(obs), obs)

            self.assertLess(ler, trivial - 0.03, msg=f"{fam} LER {ler:.3f} !< {trivial:.3f}")

    def test_color_decoder_corrects_hex(self):
        """
        The dedicated min-weight "color" decoder corrects the honeycomb color code that
        MWPM cannot touch -- below the trivial predictor.
        """
        c = color.color_code("hex_color", 3, 3, 0.04)
        dets, obs = DetectorSampler(c).sample(1500, seed=5)
        ler = 1.0 - logical_fidelity(make_circuit_decoder("color", c).decode_batch(dets), obs)
        trivial = 1.0 - logical_fidelity(np.zeros_like(obs), obs)

        self.assertLess(ler, trivial - 0.03, msg=f"color LER {ler:.3f} !< {trivial:.3f}")


if __name__ == "__main__":
    rc = 0
    rc |= Exam(
        "ColorCodes", "Triangular-axis color / surface code families", "color.md"
    ).run(load(ColorCodeTests))
    sys.exit(rc)
