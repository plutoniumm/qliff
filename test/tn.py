import itertools
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from qliff.qec import DetectorErrorModel, DetectorSampler
from qliff.qec.codes import (
    logical_fidelity,
    repetition_code,
    rotated_surface_code,
    toric_code,
    unrotated_surface_code,
)
from qliff.qec.decoder import (
    DECODER_SPECS,
    make_circuit_decoder,
    make_decoder,
)
from qliff.qec.threshold import _build_decoder, logical_error_rate, sweep
from qliff.qec.tn import MaxLikelihoodDecoder, Tensor, biased_copy, contract, parity


def _brute_force_class(dem, syndrome):
    """
    Exact maximum-likelihood by enumerating all 2^M mechanism configurations:
    the most probable logical class among configs matching the syndrome.
    """
    num_obs = dem.num_observables
    weights = np.zeros(2**num_obs)

    for bits in itertools.product((0, 1), repeat=len(dem.mechanisms)):
        dets = set()
        obs = set()
        prob = 1.0

        for m, on in enumerate(bits):
            p, dd, oo = dem.mechanisms[m]
            prob *= p if on else 1.0 - p

            if on:
                dets ^= set(dd)
                obs ^= set(oo)

        if all(
            (1 if k in dets else 0) == syndrome[k] for k in range(dem.num_detectors)
        ):
            idx = sum((1 if k in obs else 0) << k for k in range(num_obs))
            weights[idx] += prob

    return int(np.argmax(weights))


class TensorTests(Question):
    def test_contract_matches_matmul(self):
        """
        A contracted tensor chain equals the corresponding matrix product.
        """
        a = np.random.default_rng(0).random((3, 4))
        b = np.random.default_rng(1).random((4, 5))
        c = np.random.default_rng(2).random((5, 2))
        out = contract(
            [Tensor(a, ("i", "j")), Tensor(b, ("j", "k")), Tensor(c, ("k", "l"))],
            ["i", "l"],
        ).data

        self.assertTrue(np.allclose(out, a @ b @ c), msg="chain contraction != matmul")

    def test_contract_matches_einsum(self):
        """
        Contracting a small star network agrees with a direct numpy einsum.
        """
        rng = np.random.default_rng(7)
        a = rng.random((2, 2, 2))
        b = rng.random((2, 2))
        c = rng.random((2, 2))
        got = contract(
            [Tensor(a, ("x", "y", "z")), Tensor(b, ("y", "p")), Tensor(c, ("z", "q"))],
            ["x", "p", "q"],
        ).data
        want = np.einsum("xyz,yp,zq->xpq", a, b, c)

        self.assertTrue(np.allclose(got, want), msg="star contraction != einsum")

    def test_parity_tensor(self):
        """
        The parity tensor is 1 exactly where the leg indices XOR to its target.
        """
        even = parity(3, 0)
        odd = parity(3, 1)

        self.assertEqual(even[0, 0, 0], 1.0, msg="000 has even parity")

        self.assertEqual(even[1, 1, 0], 1.0, msg="110 has even parity")

        self.assertEqual(odd[1, 0, 0], 1.0, msg="100 has odd parity")

    def test_biased_copy_diagonal(self):
        """
        The biased COPY tensor carries (1-p) on the all-zero corner, p on all-one.
        """
        t = biased_copy(3, 0.1)

        self.assertExpectation(t[0, 0, 0], 0.9, msg="all-zero corner carries 1-p")

        self.assertExpectation(t[1, 1, 1], 0.1, msg="all-one corner carries p")

        self.assertEqual(t[1, 0, 0], 0.0, msg="off-diagonal entries vanish")

    def test_truncation_lossless_at_full_bond(self):
        """
        Truncated contraction at a bond >= the exact rank equals exact contraction.
        """
        rng = np.random.default_rng(13)
        a = Tensor(rng.random((2, 2, 2, 2)), ("p", "x", "y", "z"))
        b = Tensor(rng.random((2, 2, 2, 2)), ("x", "y", "z", "q"))
        exact = contract([a, b], ["p", "q"]).data
        full = contract([a, b], ["p", "q"], max_bond=8).data

        self.assertTrue(np.allclose(exact, full), msg="chi>=rank must be exact")

    def test_truncation_drops_information(self):
        """
        Truncating below the cut's rank loses information, so the result differs.
        """
        rng = np.random.default_rng(21)
        a = Tensor(rng.random((4, 4)).reshape(2, 2, 4), ("a1", "a2", "s"))
        b = Tensor(rng.random((4, 2, 2)), ("s", "b1", "b2"))
        exact = contract([a, b], ["a1", "a2", "b1", "b2"]).data
        cut = contract([a, b], ["a1", "a2", "b1", "b2"], max_bond=1).data
        rel = np.linalg.norm(exact - cut) / np.linalg.norm(exact)

        self.assertGreater(rel, 0.01, msg="chi=1 below rank-4 must truncate")


class MldTests(Question):
    def test_matches_brute_force(self):
        """
        MLD reproduces brute-force maximum-likelihood on every repetition-code
        syndrome.
        """
        dem = DetectorErrorModel(repetition_code(3, 1, 0.15))
        decoder = make_decoder("mld", dem)
        mismatches = 0

        for s in itertools.product((0, 1), repeat=dem.num_detectors):
            syndrome = np.array(s, dtype=np.uint8)
            mld = int(decoder._decode_one(syndrome)[0])

            if mld != _brute_force_class(dem, syndrome):
                mismatches += 1

        self.assertEqual(mismatches, 0, msg="MLD must equal brute-force ML")

    def test_never_worse_than_mwpm(self):
        """
        On a graphlike surface code MLD is never worse than MWPM (it is optimal).
        """
        circuit = rotated_surface_code(3, 3, 3, 0.07)
        dem = DetectorErrorModel(circuit)
        dets, obs = DetectorSampler(circuit).sample(2500, seed=11)
        mwpm = 1.0 - logical_fidelity(make_decoder("mwpm", dem).decode_batch(dets), obs)
        mld = 1.0 - logical_fidelity(make_decoder("mld", dem).decode_batch(dets), obs)

        self.assertLessEqual(mld, mwpm + 0.005, msg=f"MLD {mld:.4f} > MWPM {mwpm:.4f}")

    def test_beats_mwpm_with_correlations(self):
        """
        With depolarizing Y-correlations MLD beats MWPM, which decodes X/Z apart.
        """
        circuit = unrotated_surface_code(3, 3, 0.08)
        dem = DetectorErrorModel(circuit)
        dets, obs = DetectorSampler(circuit).sample(2000, seed=5)
        mwpm = 1.0 - logical_fidelity(make_decoder("mwpm", dem).decode_batch(dets), obs)
        mld = 1.0 - logical_fidelity(make_decoder("mld", dem).decode_batch(dets), obs)

        self.assertLess(mld, mwpm, msg=f"MLD {mld:.4f} not better than MWPM {mwpm:.4f}")

    def test_tn_untruncated_matches_mld(self):
        """
        The "tn" decoder with no bond cap resolves to the same maximum-likelihood
        contraction as "mld", so the default behaviour of both names is identical.
        """
        dem = DetectorErrorModel(repetition_code(3, 1, 0.1))
        dets, obs = DetectorSampler(repetition_code(3, 1, 0.1)).sample(200, seed=1)
        mld = make_decoder("mld", dem).decode_batch(dets)
        tn = make_decoder("tn", dem).decode_batch(dets)

        self.assertTrue(np.array_equal(mld, tn), msg="'tn' must match 'mld'")

    def test_truncated_matches_exact_all_syndromes(self):
        """
        A bonded MLD at modest chi reproduces exact MLD on every repetition d=3
        syndrome, so truncation is lossless once chi covers the cut.
        """
        dem = DetectorErrorModel(repetition_code(3, 1, 0.15))
        exact = MaxLikelihoodDecoder(dem)
        trunc = MaxLikelihoodDecoder(dem, max_bond=8)
        mismatches = 0

        for s in itertools.product((0, 1), repeat=dem.num_detectors):
            syndrome = np.array(s, dtype=np.uint8)

            if not np.array_equal(
                exact._decode_one(syndrome), trunc._decode_one(syndrome)
            ):
                mismatches += 1

        self.assertEqual(mismatches, 0, msg="chi=8 MLD must equal exact MLD")

    def test_truncated_matches_exact_batch(self):
        """
        A bonded MLD at modest chi reproduces exact decode_batch on sampled
        rotated-surface d=3 shots spanning many distinct syndromes.
        """
        circuit = rotated_surface_code(3, 3, 3, 0.06)
        dem = DetectorErrorModel(circuit)
        dets, obs = DetectorSampler(circuit).sample(500, seed=4)
        exact = MaxLikelihoodDecoder(dem).decode_batch(dets)
        trunc = MaxLikelihoodDecoder(dem, max_bond=16).decode_batch(dets)

        self.assertTrue(
            np.array_equal(exact, trunc), msg="chi=16 must match exact batch"
        )

    def test_truncated_runs_at_distance_five(self):
        """
        A bonded MLD returns predictions on rotated-surface d=5 (bounded bond),
        where the exact contraction's treewidth would otherwise explode.
        """
        circuit = rotated_surface_code(5, 5, 2, 0.05)
        dem = DetectorErrorModel(circuit)
        dets, obs = DetectorSampler(circuit).sample(6, seed=2)
        preds = MaxLikelihoodDecoder(dem, max_bond=8).decode_batch(dets)

        self.assertEqual(preds.shape, (6, dem.num_observables), msg="d=5 must decode")


class BondCapTests(Question):
    """
    The `max_bond` (chi) knob's route from the public API down to the contraction:
    logical_error_rate / sweep -> threshold._build_decoder -> decoder.make -> the
    tensor-network decoder's `max_bond`. Only the `bonded` decoders take it; the rest
    raise rather than silently drop a truncation request.
    """

    def test_only_the_tn_decoders_are_bonded(self):
        """
        Exactly the tensor-network decoders ("tn", "coherent") advertise `bonded` in
        the registry -- "mld" stays the exact reference and matching / BP+OSD / color
        have no contraction to cap.
        """
        bonded = {name for name, spec in DECODER_SPECS.items() if spec.bonded}

        self.assertEqual(
            bonded, {"tn", "coherent"}, msg=f"bonded decoders are {sorted(bonded)}"
        )

    def test_make_decoder_threads_max_bond(self):
        """
        make_decoder("tn", dem, max_bond=chi) reaches the decoder's `max_bond`, and
        omitting it leaves the exact (None) contraction.
        """
        dem = DetectorErrorModel(rotated_surface_code(3, 3, 3, 0.06))

        self.assertEqual(
            make_decoder("tn", dem, max_bond=8).max_bond, 8, msg="chi must reach 'tn'"
        )

        self.assertIsNone(
            make_decoder("tn", dem).max_bond, msg="no chi must stay exact"
        )

    def test_circuit_factory_threads_max_bond(self):
        """
        make_circuit_decoder -- the route threshold takes -- carries
        max_bond down to the tensor-network decoder it builds.
        """
        circuit = rotated_surface_code(3, 3, 3, 0.06)

        self.assertEqual(
            make_circuit_decoder("tn", circuit, 8).max_bond,
            8,
            msg="circuit factory must thread chi",
        )

        self.assertEqual(
            _build_decoder(circuit, "tn", 8).max_bond,
            8,
            msg="threshold._build_decoder must thread chi",
        )

    def test_unbonded_decoders_reject_max_bond(self):
        """
        Asking a decoder with no contraction to truncate ("mwpm", "bposd", "mld",
        "color") for a bond cap raises a ValueError naming it, so a truncation
        request is never silently ignored.
        """
        dem = DetectorErrorModel(rotated_surface_code(3, 3, 3, 0.06))

        for name in ("mwpm", "bposd", "mld", "color"):
            with self.assertRaises(ValueError) as ctx:
                make_decoder(name, dem, max_bond=8)

            self.assertIn(
                repr(name), str(ctx.exception), msg=f"{name} error must name it"
            )

    def test_rejects_a_non_positive_bond(self):
        """
        A cap below 1 keeps no singular value and would decode every syndrome to zero,
        so it is rejected up front rather than silently returning that.
        """
        dem = DetectorErrorModel(rotated_surface_code(3, 3, 3, 0.06))

        with self.assertRaises(ValueError) as ctx:
            make_decoder("tn", dem, max_bond=0)

        self.assertIn(">= 1", str(ctx.exception), msg="error must state the bound")

    def test_logical_error_rate_rejects_max_bond_on_mwpm(self):
        """
        The rejection survives the whole logical_error_rate call chain rather than
        being dropped somewhere in threshold's decoder construction.
        """
        circuit = rotated_surface_code(3, 3, 3, 0.06)

        with self.assertRaises(ValueError) as ctx:
            logical_error_rate(circuit, "mwpm", 100, 1, max_bond=8)

        self.assertIn("max_bond", str(ctx.exception), msg="error must name the knob")

    def test_logical_error_rate_exact_at_large_chi(self):
        """
        Run end to end, a bond cap wide enough to cover every cut gives exactly the
        exact decoder's logical error rate -- the knob is lossless at large chi.
        """
        circuit = rotated_surface_code(3, 3, 3, 0.06)
        exact = logical_error_rate(circuit, "mld", 400, 9)
        capped = logical_error_rate(circuit, "tn", 400, 9, max_bond=16)

        self.assertEqual(capped, exact, msg=f"chi=16 {capped} != exact {exact}")

    def test_tight_chi_changes_the_decoding(self):
        """
        A chi=1 cap really truncates the contraction: it disagrees with the exact
        decoder on some shots, proving the option reaches the contraction and is
        not quietly discarded on the way down.
        """
        circuit = rotated_surface_code(3, 3, 3, 0.07)
        dem = DetectorErrorModel(circuit)
        dets, _obs = DetectorSampler(circuit).sample(300, seed=4)
        exact = make_decoder("mld", dem).decode_batch(dets)
        cut = make_decoder("tn", dem, max_bond=1).decode_batch(dets)
        differing = int(np.sum(np.any(exact != cut, axis=1)))

        self.assertGreater(differing, 0, msg="chi=1 must change some predictions")

    def test_tight_chi_agrees_on_toric_at_wide_chi(self):
        """
        On a toric memory -- a denser network where truncation bites at chi=2 -- a
        tight cap changes the class weights while a wide one restores them to the
        exact contraction, bracketing the knob from both sides.
        """
        circuit = toric_code(3, 2, 0.06)
        dem = DetectorErrorModel(circuit)
        dets, _obs = DetectorSampler(circuit).sample(40, seed=6)
        decoder = MaxLikelihoodDecoder(dem)
        # a syndrome the model can actually produce, so the class weights are nonzero.
        syndrome = max(dets, key=lambda row: int(row.sum()))
        tensors = decoder._static + decoder._detector_tensors(syndrome)
        exact = contract(tensors, decoder._open).data.reshape(-1)
        tight = contract(tensors, decoder._open, max_bond=1).data.reshape(-1)
        wide = contract(tensors, decoder._open, max_bond=64).data.reshape(-1)
        norm = np.linalg.norm(exact)

        self.assertGreater(
            np.linalg.norm(exact - tight) / norm, 1e-3, msg="chi=1 must truncate"
        )

        self.assertLess(
            np.linalg.norm(exact - wide) / norm, 1e-9, msg="chi=64 must be exact"
        )

    def test_sweep_threads_max_bond(self):
        """
        sweep / isweep forward max_bond to every point of the curve, so a threshold
        sweep can run the truncating decoder.
        """
        curve = sweep(
            lambda p: rotated_surface_code(3, 3, 2, p),
            [0.02, 0.05],
            "tn",
            200,
            3,
            max_bond=8,
        )

        self.assertEqual(len(curve), 2, msg="sweep must yield one point per p")

        self.assertLess(curve[0][1], curve[1][1] + 0.05, msg="LER must track p")


if __name__ == "__main__":
    rc = 0
    rc |= Exam("TN", "Tensor-network contraction primitives", "tn.md").run(
        load(TensorTests)
    )
    rc |= Exam("MLD", "Maximum-likelihood (tensor) decoder", "mld.md").run(
        load(MldTests)
    )
    rc |= Exam(
        "BondCap", "Bond-dimension (chi) plumbing from the public API", "bond_cap.md"
    ).run(load(BondCapTests))
    sys.exit(rc)
