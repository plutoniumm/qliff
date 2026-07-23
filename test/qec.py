import os
import sys
from typing import get_args

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from qliff import Circuit
from qliff.noise.channel import CHANNEL_META, apply_data_noise, channel_arg
from qliff.qec import (
    DetectorErrorModel,
    DetectorSampler,
    logical_fidelity,
    repetition_code,
    rotated_surface_code,
    toric_code,
    unrotated_surface_code,
)
from qliff.qec.decoder import DECODER_SPECS, make_circuit_decoder
from qliff.qec.sampler import StratifiedDetectorSampler
from qliff.qec.threshold import (
    _cv_stratum,
    _fault_branch_indices,
    _interpolated_error_rate,
    _loo_beta,
    _scan_stratum,
    _stratified_error_rate,
    _stratum_config_count,
    _weighted_error_rate,
)
from qliff.qec.registry import FAMILIES
from qliff.server.schema import CodeFamily, DecoderName


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
        dem = DetectorErrorModel(rotated_surface_code(3, 3, 3, 0.01))
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
        c = rotated_surface_code(3, 3, 3, 0.01)

        self.assertEqual(len(c.detectors), 16, msg="d=3 detector count")

        self.assertEqual(len(c.observables), 1, msg="one logical observable")

    def test_surface_noiseless_silent(self):
        """
        With no noise every surface detector and observable stays at zero.
        """
        c = rotated_surface_code(3, 3, 3, 0.0)
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

    def test_multi_branch_channel_sums(self):
        """
        A channel's branches are mutually exclusive, so two of them flipping the same
        detector SUM rather than combining as independent errors. DEPOLARIZE1's X and
        Y both flip a Z-basis measurement, so the mechanism is exactly 2p/3 -- merging
        them independently undercounts by O(p^2) (20% low at p=0.6).
        """
        for p in (0.01, 0.1, 0.6):
            c = Circuit()
            c.append("DEPOLARIZE1", (0,), p)
            c.append("M", (0,))
            c.detector(-1)
            dem = DetectorErrorModel(c)

            self.assertEqual(len(dem.mechanisms), 1, msg=f"one mechanism at p={p}")

            self.assertLess(
                abs(dem.mechanisms[0][0] - 2.0 * p / 3.0),
                1e-12,
                msg=f"p={p}: DEM {dem.mechanisms[0][0]} != 2p/3 {2.0 * p / 3.0}",
            )

    def test_dem_agrees_with_sampler(self):
        """
        The DEM's detection probability matches the circuit sampler's measured rate --
        the two paths must not disagree with each other.
        """
        p = 0.2
        c = Circuit()
        c.append("DEPOLARIZE1", (0,), p)
        c.append("M", (0,))
        c.detector(-1)
        dets, _obs = DetectorSampler(c).sample(200000, seed=3)
        predicted = DetectorErrorModel(c).mechanisms[0][0]

        self.assertLess(
            abs(float(dets.mean()) - predicted),
            0.005,
            msg=f"sampler {dets.mean():.5f} vs DEM {predicted:.5f}",
        )

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


# every code-family builder at a small distance, keyed by name -> p->Circuit.
_BUILDERS = {
    "repetition": lambda ch: repetition_code(5, 3, 0.06, channel=ch),
    "rotated_surface": lambda ch: rotated_surface_code(3, 3, 3, 0.06, channel=ch),
    "unrotated_surface": lambda ch: unrotated_surface_code(3, 3, 0.06, channel=ch),
    "toric": lambda ch: toric_code(3, 3, 0.06, channel=ch),
}
# the five Pauli channels the builders must shape correctly: scalar-arg 1Q ones,
# the (px,py,pz) vector channel, and the 2-qubit pair channel.
_PAULI_CHANNELS = [
    "DEPOLARIZE1",
    "DEPOLARIZE2",
    "X_ERROR",
    "Z_ERROR",
    "PAULI_CHANNEL_1",
]


class NoiseChannelTests(Question):
    def test_channel_arg_shapes(self):
        """
        channel_arg splits PAULI_CHANNEL_1's scalar p into a (p/3,p/3,p/3) vector and
        leaves every scalar-arg channel's p untouched.
        """
        self.assertEqual(
            channel_arg("PAULI_CHANNEL_1", 0.06),
            (0.02, 0.02, 0.02),
            msg="vector channel must split p evenly",
        )

        for ch in ("DEPOLARIZE1", "DEPOLARIZE2", "X_ERROR", "Z_ERROR"):
            self.assertEqual(channel_arg(ch, 0.06), 0.06, msg=f"{ch} arg stays scalar")

    def test_apply_data_noise_shapes(self):
        """
        apply_data_noise emits one 1Q op per qubit for scalar/vector channels (vector
        arg a 3-tuple) and one 2Q op per adjacent pair for DEPOLARIZE2.
        """

        def collect(channel, qubits):
            calls = []
            apply_data_noise(
                lambda n, t, a: calls.append((n, tuple(t), a)), channel, qubits, 0.06
            )

            return calls

        vec = collect("PAULI_CHANNEL_1", range(3))

        self.assertEqual(
            [t for _n, t, _a in vec], [(0,), (1,), (2,)], msg="1Q per qubit"
        )

        self.assertEqual(vec[0][2], (0.02, 0.02, 0.02), msg="vector arg is the 3-tuple")

        two = collect("DEPOLARIZE2", range(4))

        self.assertEqual(
            [t for _n, t, _a in two], [(0, 1), (2, 3)], msg="2Q on adjacent pairs"
        )

        x = collect("X_ERROR", range(2))

        self.assertEqual(
            [a for _n, _t, a in x], [0.06, 0.06], msg="scalar arg per qubit"
        )

    def test_every_family_every_channel_builds(self):
        """
        Every code family builds and DEM-builds under all five Pauli channels --
        the regression for PAULI_CHANNEL_1 (float not iterable) and DEPOLARIZE2
        (tuple index out of range) crashing the template builders.
        """
        bad = []
        for fam, build in _BUILDERS.items():
            for ch in _PAULI_CHANNELS:
                try:
                    DetectorErrorModel(build(ch))
                except Exception as exc:  # noqa: BLE001 -- catch is the assertion
                    bad.append(f"{fam}/{ch}: {type(exc).__name__}")

        self.assertEqual(bad, [], msg="every family x channel must build a DEM")

    def test_mwpm_rejects_hyperedges_with_steer(self):
        """
        DEPOLARIZE2 on a 2D code can yield hyperedges (a fault flipping > 2 detectors);
        on such a geometry MWPM must reject it with an actionable message, not
        PyMatching's opaque "column has N ones" error.
        """
        hyperedge = {
            "rotated_surface": rotated_surface_code(
                3, 3, 3, 0.06, channel="DEPOLARIZE2", edge="odd"
            ),
            "unrotated_surface": _BUILDERS["unrotated_surface"]("DEPOLARIZE2"),
            "toric": _BUILDERS["toric"]("DEPOLARIZE2"),
        }
        for fam, c in hyperedge.items():
            self.assertFalse(
                DetectorErrorModel(c).is_graphlike(),
                msg=f"{fam} should be non-graphlike",
            )
            with self.assertRaises(ValueError) as ctx:
                make_circuit_decoder("mwpm", c)

            self.assertIn("graphlike", str(ctx.exception), msg=f"{fam} steer text")

    def test_mwpm_accepts_graphlike_two_qubit(self):
        """
        DEPOLARIZE2 stays graphlike on the 1D repetition code (a pair fault flips <= 2
        detectors), so MWPM builds there -- the guard is geometry-aware, not a blanket
        channel ban.
        """
        dem = DetectorErrorModel(_BUILDERS["repetition"]("DEPOLARIZE2"))

        self.assertTrue(dem.is_graphlike(), msg="rep-code DEPOLARIZE2 DEM is graphlike")

        make_circuit_decoder("mwpm", _BUILDERS["repetition"]("DEPOLARIZE2"))


class WireContractTests(Question):
    """
    Guards that the dispatch registries stay byte-identical to the HTTP wire schema
    (schema.py Literals + CHANNEL_META), which the frontend mirrors by hand. The
    registries provide metadata BEHIND these names; the names themselves must not drift.
    """

    def test_family_names_match_schema(self):
        """
        The code-family registry keys are exactly the schema.CodeFamily wire Literal
        members, so /templates can never offer a family the wire contract lacks.
        """
        self.assertEqual(
            sorted(FAMILIES),
            sorted(get_args(CodeFamily)),
            msg="registry families != schema.CodeFamily members",
        )

    def test_decoder_names_match_schema(self):
        """
        The decoder registry keys are exactly the schema.DecoderName wire Literal
        members, so the capability flags and /decoders payload cannot drift from it.
        """
        self.assertEqual(
            sorted(DECODER_SPECS),
            sorted(get_args(DecoderName)),
            msg="registry decoders != schema.DecoderName members",
        )

    def test_channel_keys_match_served_channels(self):
        """
        CHANNEL_META's keys are exactly the channel names the /channels payload serves,
        so the served channel list stays welded to the noise engine's single source.
        """
        from qliff.server import api

        self.assertEqual(
            sorted(CHANNEL_META),
            sorted(c.name for c in api._CHANNELS),
            msg="CHANNEL_META keys != served /channels names",
        )

    def test_served_payloads_track_registries(self):
        """
        The /templates and /decoders payloads mirror their registries in order and
        membership -- deriving both from one place, not a hand-kept parallel list.
        """
        from qliff.server import api

        self.assertEqual(
            [t.family for t in api._TEMPLATES],
            list(FAMILIES),
            msg="/templates family order must match the family registry",
        )

        self.assertEqual(
            [d.name for d in api._DECODERS],
            list(DECODER_SPECS),
            msg="/decoders order must match the decoder registry",
        )


class StratifiedLERTests(Question):
    def test_masses_are_exact(self):
        """
        The per-stratum signed quasiprobability masses are computed analytically and
        must sum to 1 by trace preservation, for Pauli and non-Pauli noise alike.
        """
        for channel, p in (
            ("AMPLITUDE_DAMP", 0.05),
            ("DEPOLARIZE1", 0.05),
            ("RZ", 0.15),
        ):
            c = rotated_surface_code(3, 3, 1, p, channel=channel, prep=True)
            total = sum(StratifiedDetectorSampler(c).mass)

            self.assertLess(
                abs(total - 1.0), 1e-9, msg=f"{channel}: sum(mass) = {total}"
            )

    def test_degenerates_on_pauli_noise(self):
        """
        On Pauli noise every branch sign is +1 and the masses are the ordinary
        Poisson-binomial P(k), so the stratified estimator must reproduce plain
        detector sampling.
        """
        c = rotated_surface_code(3, 3, 1, 0.08, channel="DEPOLARIZE1", prep=True)
        decoder = make_circuit_decoder("mld", c)
        dets, obs = DetectorSampler(c).sample(20000, seed=2)
        plain = 1.0 - logical_fidelity(decoder.decode_batch(dets), obs)
        strat, err = _stratified_error_rate(c, decoder, 20000, 2)
        spread = np.sqrt(plain * (1 - plain) / 20000) + err

        self.assertLess(
            abs(strat - plain),
            3.0 * spread,
            msg=f"stratified {strat:.5f} vs plain {plain:.5f} (+/-{spread:.5f})",
        )

    def test_agrees_with_flat_importance_sampling(self):
        """
        On amplitude damping the control-variate stratified estimator and the flat
        quasiprobability estimator must agree -- they estimate the same quantity, so
        this is the unbiasedness check that matters for non-Pauli noise.
        """
        c = rotated_surface_code(4, 4, 1, 0.08, channel="AMPLITUDE_DAMP", prep=True)
        decoder = make_circuit_decoder("coherent", c)
        flat, flat_err = _weighted_error_rate(c, decoder, 20000, 3)
        strat, strat_err = _stratified_error_rate(c, decoder, 20000, 3)

        self.assertLess(
            abs(strat - flat),
            3.0 * np.sqrt(flat_err**2 + strat_err**2),
            msg=f"strat {strat:.5f}+/-{strat_err:.5f} vs "
            f"flat {flat:.5f}+/-{flat_err:.5f}",
        )

    def test_control_variate_is_unbiased_over_many_seeds(self):
        """
        Averaged over many seeds the control-variate estimator must sit on the flat
        quasiprobability mean -- a pooled unbiasedness check that no per-seed accident
        can pass, guarding against a bias sneaking in through the leave-one-out beta.
        """
        c = rotated_surface_code(3, 3, 1, 0.10, channel="AMPLITUDE_DAMP", prep=True)
        decoder = make_circuit_decoder("coherent", c)
        flat = [_weighted_error_rate(c, decoder, 8000, s)[0] for s in range(1, 13)]
        cv = [_stratified_error_rate(c, decoder, 4000, s)[0] for s in range(1, 13)]
        flat_mean = float(np.mean(flat))
        cv_mean = float(np.mean(cv))
        combined = np.std(flat) / np.sqrt(len(flat)) + np.std(cv) / np.sqrt(len(cv))

        self.assertLess(
            abs(cv_mean - flat_mean),
            4.0 * combined,
            msg=f"cv {cv_mean:.5f} vs flat {flat_mean:.5f} (+/-{combined:.5f})",
        )

    def test_leave_one_out_beta_excludes_its_own_shot(self):
        """
        The leave-one-out control-variate coefficient for shot i must equal the plain
        Cov(s*w, s)/Var(s) computed on every OTHER shot -- that independence is exactly
        what keeps the control variate unbiased, so it is checked directly.
        """
        s = np.array([1.0, -1.0, 1.0, -1.0, 1.0, 1.0])
        wrong = np.array([1.0, 0.0, 0.0, 1.0, 1.0, 0.0])
        sw = s * wrong
        beta = _loo_beta(sw, s)
        for i in range(s.size):
            keep = np.arange(s.size) != i
            si, swi = s[keep], sw[keep]
            mean_s = si.mean()
            cov = float((swi * si).mean()) - float(swi.mean()) * mean_s
            want = cov / (1.0 - mean_s * mean_s)

            self.assertAlmostEqual(
                beta[i], want, places=12, msg=f"loo beta[{i}] != manual leave-out"
            )

    def test_control_variate_is_finite_when_signs_cancel(self):
        """
        The self-normalised ratio sum(s*w)/sum(s) diverged when a stratum's signs
        cancelled (sum(s) = 0) -- the 0.27x regression. The control variate has no such
        denominator, so on that exact input it must return a finite contribution.
        """
        s = np.array([1.0, 1.0, -1.0, -1.0])
        wrong = np.array([1.0, 0.0, 0.0, 0.0])

        self.assertEqual(float(s.sum()), 0.0, msg="test setup: signs must cancel")

        contribution, variance = _cv_stratum(2.0, 0.0, s, wrong)

        self.assertTrue(np.isfinite(contribution), msg="contribution blew up")

        self.assertTrue(np.isfinite(variance), msg="variance blew up")

    def test_exact_scan_reproduces_stratum_mass(self):
        """
        The exhaustive low-k scan sums the exact signed branch weights, so its total
        weight per stratum must reproduce the analytic Poisson-binomial mass -- the
        correctness anchor for the interpolation's pinned lower asymptote.
        """
        c = rotated_surface_code(3, 3, 1, 0.08, channel="AMPLITUDE_DAMP", prep=True)
        sampler = StratifiedDetectorSampler(c)
        decoder = make_circuit_decoder("coherent", c)
        fault_indices = _fault_branch_indices(sampler)
        for k in (0, 1, 2):
            _ler_k, mass_k, _var_k, n = _scan_stratum(
                sampler, c, decoder, k, fault_indices, 4, seed=0
            )

            self.assertEqual(
                n, _stratum_config_count(fault_indices, k), msg=f"k={k} config count"
            )

            self.assertAlmostEqual(
                mass_k, sampler.mass[k], places=9, msg=f"k={k} scanned mass != analytic"
            )

    def test_interpolation_agrees_with_full_run_within_its_bias_bound(self):
        """
        The asymptote-pinned interpolation must agree with a full control-variate run
        to within the statistical error plus the bias bound it reports -- validated on
        a patch small enough that the full run is affordable and honest.
        """
        c = rotated_surface_code(4, 4, 1, 0.10, channel="AMPLITUDE_DAMP", prep=True)
        decoder = make_circuit_decoder("coherent", c)
        full, full_err = _stratified_error_rate(c, decoder, 4000, 5)
        interp, interp_err, bias = _interpolated_error_rate(
            c, decoder, 4000, 5, exact_budget=100, reps=6
        )

        self.assertGreaterEqual(bias, 0.0, msg="bias bound must be non-negative")

        self.assertLessEqual(
            abs(interp - full),
            4.0 * (full_err + interp_err) + bias,
            msg=f"interp {interp:.5f}+/-{interp_err:.5f} vs full {full:.5f} "
            f"(bias<= {bias:.5f})",
        )

    def test_interpolation_pins_high_k_and_stays_within_bound(self):
        """
        Forcing a high sign floor pins the poorly-resolved high-k strata, so the bias
        bound turns strictly positive; even then the interpolated LER must agree with a
        full control-variate run to within statistics plus that reported bound.
        """
        c = rotated_surface_code(4, 4, 1, 0.10, channel="AMPLITUDE_DAMP", prep=True)
        decoder = make_circuit_decoder("coherent", c)
        full, full_err = _stratified_error_rate(c, decoder, 4000, 7)
        interp, interp_err, bias = _interpolated_error_rate(
            c, decoder, 4000, 7, exact_budget=100, sign_floor=0.30, reps=6
        )

        self.assertGreater(bias, 0.0, msg="a high sign floor must pin some strata")

        self.assertLessEqual(
            abs(interp - full),
            4.0 * (full_err + interp_err) + bias,
            msg=f"interp {interp:.5f} vs full {full:.5f} (bias<= {bias:.5f})",
        )

    def test_every_sampled_stratum_can_report_spread(self):
        """
        A stratum estimated from one trajectory would report zero spread and
        understate the error bar, so every sampled stratum except k=0 (which holds
        exactly one trajectory, so its value is exact) gets at least two shots.
        """
        c = rotated_surface_code(3, 3, 1, 0.05, channel="AMPLITUDE_DAMP", prep=True)
        sampler = StratifiedDetectorSampler(c)
        _d, _o, _s, strata = sampler.sample(3000, seed=1)
        counts = {int(k): int((strata == k).sum()) for k in np.unique(strata)}
        thin = [k for k, n in counts.items() if k != 0 and n < 2]

        self.assertEqual(thin, [], msg=f"strata with < 2 shots: {counts}")

        self.assertLess(
            sampler.dropped_mass, 1e-9, msg="no meaningful mass may be dropped here"
        )


if __name__ == "__main__":
    rc = 0
    rc |= Exam("Codes", "QEC code generators", "codes.md").run(load(CodeTests))
    rc |= Exam("DEM", "Detector error model + decoder exporters", "dem.md").run(
        load(DEMTests)
    )
    rc |= Exam("QEC", "Detector and observable sampling", "qec.md").run(load(QECTests))
    rc |= Exam(
        "NoiseChannels", "Noise-channel arg shaping across code builders", "channels.md"
    ).run(load(NoiseChannelTests))
    rc |= Exam(
        "WireContract", "Registry <-> wire-schema sync guards", "wire_contract.md"
    ).run(load(WireContractTests))
    rc |= Exam(
        "StratifiedLER",
        "Self-normalised stratified logical-error-rate estimator",
        "stratified_ler.md",
    ).run(load(StratifiedLERTests))
    sys.exit(rc)
