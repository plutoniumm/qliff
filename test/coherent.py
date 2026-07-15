import itertools
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

from qliff.circuit import Circuit
from qliff.noise.channel import make_channel
from qliff.qec import (
    DetectorErrorModel,
    DetectorSampler,
    logical_fidelity,
    repetition_code,
    rotated_surface_code,
)
from qliff.qec.decoder import make_circuit_decoder, make_decoder
from qliff.simulator import CLIFFORD_OPS, MEAS, Simulator


def _rep_coherent(distance: int, noise: str, arg: float, rounds: int = 1) -> Circuit:
    """
    Bit-flip repetition code whose per-round data noise is a NON-Pauli channel
    (RX rotation or amplitude damping wrapped into the X basis), so the circuit
    carries signed quasiprobability branches no DEM can represent.
    """
    c = Circuit()
    data = list(range(distance))
    anc = list(range(distance, 2 * distance - 1))
    checks = distance - 1

    for r in range(rounds):
        for q in data:
            if noise == "AMPLITUDE_DAMP":
                c.append("H", [q]).append("AMPLITUDE_DAMP", [q], arg).append("H", [q])
            else:
                c.append(noise, [q], arg)

        for i in range(checks):
            c.append("CX", [data[i], anc[i]])
            c.append("CX", [data[i + 1], anc[i]])

        for i in range(checks):
            c.append("MR", [anc[i]])
            if r == 0:
                c.detector(-1)
            else:
                c.detector(-1, -1 - checks)

    for q in data:
        c.append("M", [q])
    for i in range(checks):
        c.detector(-distance + i, -distance + i + 1, -distance - checks + i)

    c.observable(0, *[-distance + i for i in range(distance)])

    return c


def _brute_quasiprob_class(decoder, circuit: Circuit, syndrome: np.ndarray) -> int:
    """
    Exact quasiprobability oracle: enumerate one branch per noise location,
    multiply the signed branch weights, accumulate onto the (detector, observable)
    pattern the combined branch set flips, restrict to the observed syndrome, and
    argmax the real per-class weight. The reference the decoder must reproduce.
    """
    locs = []
    for loc, (name, targets, arg) in enumerate(circuit.instructions):
        if name in CLIFFORD_OPS:
            continue
        channel = make_channel(name, arg)
        sigs = [
            (w, *decoder._branch_signature(loc, ops))
            for w, ops in channel.branches(targets)
        ]
        locs.append(sigs)

    num_obs = len(circuit.observables)
    num_det = len(circuit.detectors)
    weights = np.zeros(2**num_obs)

    for combo in itertools.product(*locs):
        w = 1.0
        dets: set[int] = set()
        obs: set[int] = set()

        for bw, bd, bo in combo:
            w *= bw
            dets ^= set(bd)
            obs ^= set(bo)

        if all((1 if k in dets else 0) == int(syndrome[k]) for k in range(num_det)):
            idx = sum((1 if k in obs else 0) << k for k in range(num_obs))
            weights[idx] += w

    return int(np.argmax(weights))


def _quasi_sample(
    circuit: Circuit, shots: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Syndrome generator for non-Pauli circuits (DetectorSampler is Pauli-only):
    draw one branch per location with probability |weight| / gamma, replay the
    Cliffords + measurements, and read detection events / observable flips against
    a fixed identity-branch reference trajectory.
    """
    rng = random.Random(seed)
    noise = [
        i
        for i, (n, _t, _a) in enumerate(circuit.instructions)
        if n not in CLIFFORD_OPS and n not in MEAS
    ]
    index = {loc: k for k, loc in enumerate(noise)}

    def replay(branch_ops: list[list], inner_seed: int) -> list[int]:
        sim = Simulator(circuit.num_qubits, inner_seed)
        for loc, (name, targets, _arg) in enumerate(circuit.instructions):
            if name in CLIFFORD_OPS:
                getattr(sim, name)(*targets)
            elif name in MEAS:
                getattr(sim, name)(*targets)
            else:
                for gate, qubits in branch_ops[index[loc]]:
                    getattr(sim, gate)(*qubits)

        return sim.record

    def par(record: list[int], recs: tuple) -> int:
        bit = 0
        for i in recs:
            bit ^= record[i]

        return bit

    reference = replay([[] for _ in noise], 7919)
    det_ref = [par(reference, d) for d in circuit.detectors]
    obs_ref = [par(reference, r) for _o, r in circuit.observables]

    dets = np.zeros((shots, len(circuit.detectors)), dtype=np.uint8)
    obs = np.zeros((shots, len(circuit.observables)), dtype=np.uint8)

    for s in range(shots):
        ops = []
        for loc in noise:
            name, targets, arg = circuit.instructions[loc]
            branches = make_channel(name, arg).branches(targets)
            gamma = sum(abs(w) for w, _ in branches)
            threshold = rng.random() * gamma
            acc = 0.0
            chosen = branches[-1][1]
            for w, b_ops in branches:
                acc += abs(w)
                if threshold <= acc:
                    chosen = b_ops
                    break
            ops.append(chosen)

        record = replay(ops, rng.getrandbits(63))
        for j, d in enumerate(circuit.detectors):
            dets[s, j] = par(record, d) ^ det_ref[j]
        for j, (_o, r) in enumerate(circuit.observables):
            obs[s, j] = par(record, r) ^ obs_ref[j]

    return dets, obs


class CoherentTests(Question):
    def test_reduces_to_mld_on_repetition(self):
        """
        On a purely Pauli repetition code the coherent decoder reproduces exact
        MLD on every syndrome -- proving it generalizes the maximum-likelihood
        decoder rather than replacing it.
        """
        circuit = repetition_code(3, 1, 0.15)
        mld = make_decoder("mld", DetectorErrorModel(circuit))
        coherent = make_circuit_decoder("coherent", circuit)
        mismatches = 0

        for s in itertools.product((0, 1), repeat=coherent.num_detectors):
            syndrome = np.array(s, dtype=np.uint8)
            if not np.array_equal(
                mld._decode_one(syndrome), coherent._decode_one(syndrome)
            ):
                mismatches += 1

        self.assertEqual(mismatches, 0, msg="coherent must equal MLD on Pauli noise")

    def test_reduces_to_mld_on_surface(self):
        """
        On a sampled rotated-surface-code memory the coherent decoder's batch
        predictions match exact MLD shot for shot.
        """
        circuit = rotated_surface_code(3, 3, 3, 0.07)
        dem = DetectorErrorModel(circuit)
        dets, _obs = DetectorSampler(circuit).sample(800, seed=11)
        mld = make_decoder("mld", dem).decode_batch(dets)
        coherent = make_circuit_decoder("coherent", circuit).decode_batch(dets)

        self.assertTrue(np.array_equal(mld, coherent), msg="coherent != MLD on surface")

    def test_matches_quasiprob_oracle_rotation(self):
        """
        Under a coherent RX rotation the decoder's argmax matches the brute-force
        signed-quasiprobability oracle on every syndrome -- correct non-Pauli ML.
        """
        circuit = _rep_coherent(3, "RX", 0.45)
        decoder = make_circuit_decoder("coherent", circuit)
        mismatches = 0

        for s in itertools.product((0, 1), repeat=decoder.num_detectors):
            syndrome = np.array(s, dtype=np.uint8)
            oracle = _brute_quasiprob_class(decoder, circuit, syndrome)
            if int(decoder._decode_one(syndrome)[0]) != oracle:
                mismatches += 1

        self.assertEqual(mismatches, 0, msg="coherent must match RX quasiprob oracle")

    def test_matches_quasiprob_oracle_damping(self):
        """
        Under amplitude damping (negative Z quasiprobability + reset branch) the
        decoder's argmax matches the brute-force quasiprobability oracle on every
        syndrome.
        """
        circuit = _rep_coherent(3, "AMPLITUDE_DAMP", 0.3)
        decoder = make_circuit_decoder("coherent", circuit)
        mismatches = 0

        for s in itertools.product((0, 1), repeat=decoder.num_detectors):
            syndrome = np.array(s, dtype=np.uint8)
            oracle = _brute_quasiprob_class(decoder, circuit, syndrome)
            if int(decoder._decode_one(syndrome)[0]) != oracle:
                mismatches += 1

        self.assertEqual(mismatches, 0, msg="coherent must match AD quasiprob oracle")

    def test_beats_trivial_predictor(self):
        """
        Decoding sampled coherent-RX syndromes end to end, the logical error rate
        is far below the trivial always-zero predictor's -- the decoder corrects
        real non-Pauli noise.
        """
        circuit = _rep_coherent(3, "RX", 0.45, rounds=2)
        dets, obs = _quasi_sample(circuit, 3000, 7)
        preds = make_circuit_decoder("coherent", circuit).decode_batch(dets)
        coherent = 1.0 - logical_fidelity(preds, obs)
        trivial = 1.0 - logical_fidelity(np.zeros_like(obs), obs)

        self.assertLess(
            coherent,
            trivial - 0.05,
            msg=f"coherent {coherent:.3f} !< trivial {trivial:.3f}",
        )

    def test_make_decoder_rejects_coherent_without_circuit(self):
        """
        Requesting "coherent" through the DEM-only make_decoder raises a clear
        error pointing callers to make_circuit_decoder.
        """
        dem = DetectorErrorModel(repetition_code(3, 1, 0.1))

        with self.assertRaises(ValueError) as ctx:
            make_decoder("coherent", dem)

        self.assertIn(
            "make_circuit_decoder",
            str(ctx.exception),
            msg="error must name the factory",
        )

    def test_circuit_decoder_dispatches_pauli_names(self):
        """
        make_circuit_decoder compiles a DEM for Pauli names: its "mld" route equals
        building MaxLikelihoodDecoder from the circuit's DEM directly.
        """
        circuit = repetition_code(3, 1, 0.12)
        dets, _obs = DetectorSampler(circuit).sample(200, seed=3)
        direct = make_decoder("mld", DetectorErrorModel(circuit)).decode_batch(dets)
        viafactory = make_circuit_decoder("mld", circuit).decode_batch(dets)

        self.assertTrue(
            np.array_equal(direct, viafactory), msg="factory mld must match"
        )

    def test_tn_and_mld_route_to_coherent_on_non_pauli(self):
        """
        The "tn"/"mld" names span both noise regimes: on a non-Pauli (coherent RX)
        circuit make_circuit_decoder auto-routes them to the circuit-aware
        quasiprobability TN, decoding every syndrome identically to "coherent".
        """
        circuit = _rep_coherent(3, "RX", 0.45)
        coherent = make_circuit_decoder("coherent", circuit)
        tn = make_circuit_decoder("tn", circuit)
        mld = make_circuit_decoder("mld", circuit)
        mismatches = 0

        for s in itertools.product((0, 1), repeat=coherent.num_detectors):
            syndrome = np.array(s, dtype=np.uint8)
            ref = coherent._decode_one(syndrome)
            if not np.array_equal(tn._decode_one(syndrome), ref):
                mismatches += 1
            if not np.array_equal(mld._decode_one(syndrome), ref):
                mismatches += 1

        self.assertEqual(
            mismatches, 0, msg="'tn'/'mld' must decode non-Pauli noise via coherent"
        )


if __name__ == "__main__":
    rc = Exam(
        "CoherentTN", "Quasiprobability (non-Pauli) tensor decoder", "coherent_tn.md"
    ).run(load(CoherentTests))
    sys.exit(rc)
