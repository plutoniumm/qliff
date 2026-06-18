from __future__ import annotations

import random

import numpy as np

from .._types import Targets
from ..noise.channel import make_channel
from ..simulator import CLIFFORD_OPS, Simulator

from ..circuit import Circuit


class DetectorSampler:
    """
    Sample detection events and observable flips from a noisy circuit. A
    detection event = detector's measured parity XOR its noiseless value.
    Pauli-noise trajectories only -- coherent channels raise; use the
    importance sampler.
    """

    def __init__(self, circuit: Circuit):
        self.circuit = circuit

        reference = self._record(None, noiseless=True)
        self.det_ref = [self._parity(reference, d) for d in circuit.detectors]
        self.obs_ref = [self._parity(reference, r) for _, r in circuit.observables]

    def _parity(self, record: list[int], recs: Targets) -> int:
        bit = 0
        for i in recs:
            bit ^= record[i]

        return bit

    def _record(self, rng: random.Random | None, noiseless: bool = False) -> list[int]:
        seed = None if noiseless else rng.getrandbits(63)
        sim = Simulator(self.circuit.num_qubits, seed)
        for name, targets, arg in self.circuit.instructions:
            if name in CLIFFORD_OPS:
                getattr(sim, name)(*targets)
            elif not noiseless:
                channel = make_channel(name, arg)
                if not channel.is_pauli:
                    raise ValueError(f"{name} is not Pauli; use the importance sampler")
                _factor, ops = channel.sample(targets, rng)
                for gate, qubits in ops:
                    getattr(sim, gate)(*qubits)

        return sim.record

    def sample(
        self, shots: int, seed: int | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        (detection_events, observable_flips) as uint8 arrays of shape
        (shots, n_detectors) and (shots, n_observables).
        """
        rng = random.Random(seed)
        dets = np.zeros((shots, len(self.circuit.detectors)), dtype=np.uint8)
        obs = np.zeros((shots, len(self.circuit.observables)), dtype=np.uint8)

        for s in range(shots):
            record = self._record(rng)

            for j, d in enumerate(self.circuit.detectors):
                dets[s, j] = self._parity(record, d) ^ self.det_ref[j]
            for j, (_, recs) in enumerate(self.circuit.observables):
                obs[s, j] = self._parity(record, recs) ^ self.obs_ref[j]

        return dets, obs
