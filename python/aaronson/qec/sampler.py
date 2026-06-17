import random

import numpy as np

from ..noise.channel import make_channel
from ..simulator import CLIFFORD_OPS, Simulator


class DetectorSampler:
    """
    Sample detection events and logical-observable flips from a noisy circuit.

    A detection event is a detector's measured parity XORed with its noiseless
    value. Uses Pauli-noise trajectories; coherent channels raise here (estimate
    those logical error rates with the importance sampler instead).
    """

    def __init__(self, circuit):
        self.circuit = circuit
        reference = self._record(None, noiseless=True)
        self.det_ref = [self._parity(reference, d) for d in circuit.detectors]
        self.obs_ref = [self._parity(reference, r) for _, r in circuit.observables]

    def _parity(self, record, recs):
        bit = 0
        for i in recs:
            bit ^= record[i]

        return bit

    def _record(self, rng, noiseless=False):
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

        return sim.measure_record

    def sample(self, shots, seed=None):
        """
        Return ``(detection_events, observable_flips)`` as uint8 arrays of shape
        ``(shots, n_detectors)`` and ``(shots, n_observables)``.
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
