from __future__ import annotations

import numpy as np

from ..noise.channel import make_channel
from ..simulator import CLIFFORD_OPS, MEAS, Simulator

from ..circuit import Circuit
from .tn import (
    Tensor,
    TensorNetworkDecoder,
    _dleg,
    _obs_out,
    _oleg,
    parity,
)

# Coherent-noise decoder: a factor-graph tensor contraction over the CIRCUIT's
# noise branches, not a DetectorErrorModel. MWPM / BP+OSD / MLD all consume a DEM,
# which can only represent INDEPENDENT Pauli noise -- it cannot honestly carry a
# coherent rotation or amplitude-damping channel, whose branch weights are SIGNED
# quasiprobabilities. Here each noise LOCATION stays a single multi-branch variable
# (exactly one branch fires): its tensor sums the signed branch weights onto the
# detector / observable legs that branch flips. Contracting pins the detector legs
# to the observed syndrome and leaves the observable legs open, so the network
# collapses to the (real) total weight of each logical class; the argmax is the
# most-likely correction. On a purely Pauli circuit every location's branches are
# probabilities and the contraction reduces to exact MLD -- this generalizes it.
#
# A branch's ops are general Cliffords (H, S, S_DAG, Z, reset), not just Paulis,
# so the DEM's sign-free Pauli propagation cannot signature them. We instead
# differentially propagate: replay the circuit's Cliffords + measurements once with
# the branch's ops injected at its location and once without, sharing the RNG seed,
# and XOR the detector / observable parities. Detectors are deterministic in a code
# memory, so the shared seed cancels the genuinely-random bits and the difference
# is exactly the set the branch flips.

_DIFF_SEED = 0xC0FFEE

# leg helpers (_dleg / _oleg / _obs_out) are shared with the DEM decoder in tn.py:
# a noise location and a DEM mechanism are interchangeable error sources here.


def _parity(record: list[int], recs: tuple) -> int:
    bit = 0
    for i in recs:
        bit ^= record[i]

    return bit


def _replay(circuit: Circuit, loc: int, ops: list, seed: int) -> list[int]:
    """
    Replay the circuit's Cliffords + measurements (noise channels skipped),
    injecting `ops` just before instruction `loc`; return the measurement record.
    loc = -1 injects nothing (the noiseless reference trajectory).
    """
    sim = Simulator(circuit.num_qubits, seed)

    for k, (name, targets, _arg) in enumerate(circuit.instructions):
        if k == loc:
            for gate, qubits in ops:
                getattr(sim, gate)(*qubits)
        if name in CLIFFORD_OPS:
            getattr(sim, name)(*targets)
        elif name in MEAS:
            getattr(sim, name)(*targets)

    return sim.record


class CoherentDecoder(TensorNetworkDecoder):
    """
    Quasiprobability tensor-network decoder consuming a noisy Circuit directly: the
    general case of TensorNetworkDecoder, where each source is a noise LOCATION whose
    branches carry SIGNED (and possibly complex) quasiprobabilities. Each location
    contributes one tensor whose legs are the detectors and observables its branches
    flip; the network contracts to the (real part of the) total weight per logical
    class and argmaxes it. Handles non-Pauli channels (coherent RZ/RX, amplitude
    damping) that no DEM decoder can represent; on Pauli-only circuits it reproduces
    "mld" exactly. Registered as "coherent" via make_circuit_decoder in decoder.py.
    """

    def __init__(self, circuit: Circuit):
        self.circuit = circuit
        self.num_detectors = len(circuit.detectors)
        self.num_observables = len(circuit.observables)
        self.max_bond = None

        # one tensor per noise location, plus per-detector / per-observable
        # incidence (which locations touch each).
        self._loc_tensor: list[Tensor] = []
        self._det_incidence: list[list[int]] = [[] for _ in range(self.num_detectors)]
        self._obs_locs: list[list[int]] = [[] for _ in range(self.num_observables)]
        self._dtype = float

        self._reference = _replay(circuit, -1, [], _DIFF_SEED)
        self._build_locations(circuit)

        self._init_network()

    def _branch_signature(self, loc: int, ops: list) -> tuple[frozenset, frozenset]:
        """
        Detectors / observables a single branch flips: differentially replay the
        circuit with the branch's Clifford ops injected at `loc` against the shared
        noiseless reference, then XOR detector / observable parities.
        """
        record = _replay(self.circuit, loc, ops, _DIFF_SEED)
        dets = frozenset(
            d
            for d, recs in enumerate(self.circuit.detectors)
            if _parity(record, recs) != _parity(self._reference, recs)
        )
        obs = frozenset(
            o
            for o, (_idx, recs) in enumerate(self.circuit.observables)
            if _parity(record, recs) != _parity(self._reference, recs)
        )

        return dets, obs

    def _build_locations(self, circuit: Circuit) -> None:
        complex_weights = False

        for loc, (name, targets, arg) in enumerate(circuit.instructions):
            if name in CLIFFORD_OPS:
                continue

            channel = make_channel(name, arg)
            sigs = []
            touched_dets: set[int] = set()
            touched_obs: set[int] = set()

            for weight, ops in channel.branches(targets):
                dets, obs = self._branch_signature(loc, ops)
                sigs.append((weight, dets, obs))
                touched_dets |= dets
                touched_obs |= obs

            if not touched_dets and not touched_obs:
                continue

            det_list = sorted(touched_dets)
            obs_list = sorted(touched_obs)
            self._record_location(det_list, obs_list, sigs)

            if any(w < 0.0 for w, _d, _o in sigs):
                complex_weights = True

        self._dtype = complex if complex_weights else float

    def _record_location(
        self,
        det_list: list[int],
        obs_list: list[int],
        sigs: list[tuple[float, frozenset, frozenset]],
    ) -> None:
        idx = len(self._loc_tensor)

        for d in det_list:
            self._det_incidence[d].append(idx)
        for o in obs_list:
            self._obs_locs[o].append(idx)

        legs = [_dleg(idx, d) for d in det_list]
        legs += [_oleg(idx, o) for o in obs_list]
        degree = len(legs)
        data = np.zeros((2,) * degree, dtype=float)

        det_pos = {d: k for k, d in enumerate(det_list)}
        obs_pos = {o: len(det_list) + k for k, o in enumerate(obs_list)}

        # one corner per branch: sum the signed weights of branches with identical
        # leg patterns (the no-flip branch lands on the all-zero corner).
        for weight, dets, obs in sigs:
            corner = [0] * degree
            for d in dets:
                corner[det_pos[d]] = 1
            for o in obs:
                corner[obs_pos[o]] = 1
            data[tuple(corner)] += weight

        self._loc_tensor.append(Tensor(data, tuple(legs)))

    def _build_static(self) -> list[Tensor]:
        tensors: list[Tensor] = []

        for tensor in self._loc_tensor:
            if self._dtype is complex:
                tensor = Tensor(tensor.data.astype(complex), tensor.legs)
            tensors.append(tensor)

        for o in range(self.num_observables):
            locs = self._obs_locs[o]
            legs = [_oleg(loc, o) for loc in locs] + [_obs_out(o)]
            tensors.append(Tensor(parity(len(legs), 0, dtype=self._dtype), tuple(legs)))

        return tensors
