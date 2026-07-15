from __future__ import annotations

import random

import numpy as np

from .._types import Targets
from ..noise.channel import make_channel
from ..simulator import CLIFFORD_OPS, Simulator

from ..circuit import Circuit


def record_parity(record: list[int], recs: Targets) -> int:
    """
    XOR of the measurement record bits at `recs`: one detector/observable bit.
    """
    bit = 0
    for i in recs:
        bit ^= record[i]

    return bit


class _BaseSampler:
    """
    Shared detector-sampling core. Runs Pauli-noise trajectories and XOR-folds each
    detector/observable against its noiseless reference. Every trajectory carries a
    signed importance weight (Pauli locations contribute 1.0); subclasses pick
    whether to reject non-Pauli noise and whether to expose that weight.
    """

    strict: bool = False

    def __init__(self, circuit: Circuit):
        self.circuit = circuit

        reference, _weight = self._trajectory(None, noiseless=True)
        self.det_ref = [record_parity(reference, d) for d in circuit.detectors]
        self.obs_ref = [record_parity(reference, r) for _, r in circuit.observables]

    def _trajectory(
        self, rng: random.Random | None, noiseless: bool = False
    ) -> tuple[list[int], float]:
        seed = None if noiseless else rng.getrandbits(63)
        sim = Simulator(self.circuit.num_qubits, seed)
        weight = 1.0

        for name, targets, arg in self.circuit.instructions:
            if name in CLIFFORD_OPS:
                getattr(sim, name)(*targets)
            elif not noiseless:
                channel = make_channel(name, arg)
                if self.strict and not channel.is_pauli:
                    raise ValueError(f"{name} is not Pauli; use the importance sampler")
                factor, ops = channel.sample(targets, rng)
                weight *= factor
                for gate, qubits in ops:
                    getattr(sim, gate)(*qubits)

        return sim.record, weight

    def _sample(
        self, shots: int, seed: int | None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = random.Random(seed)
        dets = np.zeros((shots, len(self.circuit.detectors)), dtype=np.uint8)
        obs = np.zeros((shots, len(self.circuit.observables)), dtype=np.uint8)
        weights = np.ones(shots, dtype=np.float64)

        for s in range(shots):
            record, weight = self._trajectory(rng)
            weights[s] = weight

            for j, d in enumerate(self.circuit.detectors):
                dets[s, j] = record_parity(record, d) ^ self.det_ref[j]
            for j, (_, recs) in enumerate(self.circuit.observables):
                obs[s, j] = record_parity(record, recs) ^ self.obs_ref[j]

        return dets, obs, weights


class DetectorSampler(_BaseSampler):
    """
    Sample detection events and observable flips from a noisy circuit. A
    detection event = detector's measured parity XOR its noiseless value.
    Pauli-noise trajectories only -- coherent channels raise; use the
    importance sampler.
    """

    strict = True

    def sample(
        self, shots: int, seed: int | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        (detection_events, observable_flips) as uint8 arrays of shape
        (shots, n_detectors) and (shots, n_observables).
        """
        dets, obs, _weights = self._sample(shots, seed)

        return dets, obs


class WeightedDetectorSampler(_BaseSampler):
    """
    Detector sampler for circuits with NON-Pauli noise (coherent rotations,
    amplitude damping). Each trajectory carries a signed importance weight = the
    product of the per-location factors channel.sample returns (sign(weight) *
    gamma; Pauli locations contribute 1). The weighted mean of any statistic is
    unbiased under the true quasiprobability channel, so a logical-error estimate
    is the weighted fraction of mis-decoded shots. Pairs with the `coherent`
    decoder; mirrors DetectorSampler but keeps the weight.
    """

    strict = False

    def sample(
        self, shots: int, seed: int | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        (detection_events, observable_flips, weights): the first two as uint8
        arrays shaped (shots, n_detectors)/(shots, n_observables); weights a float
        array (shots,) of signed importance weights, one per trajectory.
        """
        return self._sample(shots, seed)
