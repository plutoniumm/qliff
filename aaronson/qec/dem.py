import numpy as np

from ..noise.channel import make_channel
from ..simulator import CLIFFORD_OPS, GATES_1, GATES_2

_PAULI_BITS = {
    "X": (1, 0),
    "Y": (1, 1),
    "Z": (0, 1),
}


def _fault_bits(ops, n):
    x = [0] * n
    z = [0] * n
    for gate, qubits in ops:
        if gate not in _PAULI_BITS:
            raise ValueError(f"DEM supports Pauli faults only, got {gate!r}")
        a, b = _PAULI_BITS[gate]
        x[qubits[0]] ^= a
        z[qubits[0]] ^= b

    return x, z


def _frame1(name, targets, x, z):
    for q in targets:
        if name == "H":
            x[q], z[q] = z[q], x[q]
        elif name in ("S", "S_DAG"):
            z[q] ^= x[q]


def _frame2(name, targets, x, z):
    for i in range(0, len(targets), 2):
        a, b = targets[i], targets[i + 1]
        if name in ("CX", "CNOT"):
            x[b] ^= x[a]
            z[a] ^= z[b]
        elif name == "CZ":
            z[b] ^= x[a]
            z[a] ^= x[b]
        elif name == "SWAP":
            x[a], x[b] = x[b], x[a]
            z[a], z[b] = z[b], z[a]


def _propagate(circuit, loc, fx, fz):
    """
    Inject the Pauli fault (fx, fz) at instruction loc and propagate it
    sign-free to the end, returning the set of measurement indices it flips.
    """
    n = circuit.num_qubits
    x = [0] * n
    z = [0] * n
    flipped = set()
    midx = 0
    for k, (name, targets, _arg) in enumerate(circuit.instructions):
        if k == loc:
            for q in range(n):
                x[q] ^= fx[q]
                z[q] ^= fz[q]
        if name in GATES_1:
            _frame1(name, targets, x, z)
        elif name in GATES_2:
            _frame2(name, targets, x, z)
        elif name == "M":
            for q in targets:
                if x[q]:
                    flipped.add(midx)
                midx += 1
        elif name == "MR":
            for q in targets:
                if x[q]:
                    flipped.add(midx)
                midx += 1
                x[q] = 0
                z[q] = 0
        elif name == "R":
            for q in targets:
                x[q] = 0
                z[q] = 0

    return flipped


def _odd(recs, flipped):
    return len(set(recs) & flipped) % 2 == 1


def _combine(p, q):
    return p * (1.0 - q) + q * (1.0 - p)


class DetectorErrorModel:
    """
    First-order detector error model. Each Pauli fault branch is propagated sign-free
    to the circuit end to find the detectors/observables it flips; branches with equal
    signatures merge as independent errors. Pauli noise only; exporters feed
    MWPM / BP / ML (no decoder bundled).
    """

    def __init__(self, circuit):
        self.num_detectors = len(circuit.detectors)
        self.num_observables = len(circuit.observables)
        merged = {}
        for loc, (name, targets, arg) in enumerate(circuit.instructions):
            if name in CLIFFORD_OPS:
                continue
            channel = make_channel(name, arg)
            if not channel.is_pauli:
                raise ValueError(f"DEM requires Pauli noise; {name} is not Pauli")
            for w, ops in channel.branches(targets)[1:]:
                if w == 0.0:
                    continue
                fx, fz = _fault_bits(ops, circuit.num_qubits)
                flipped = _propagate(circuit, loc, fx, fz)
                dets = frozenset(
                    d for d, recs in enumerate(circuit.detectors) if _odd(recs, flipped)
                )
                obs = frozenset(
                    o
                    for o, (_idx, recs) in enumerate(circuit.observables)
                    if _odd(recs, flipped)
                )
                if not dets and not obs:
                    continue
                key = (dets, obs)
                merged[key] = _combine(merged.get(key, 0.0), w)
        self.mechanisms = [(p, dets, obs) for (dets, obs), p in merged.items()]

    def check_matrix(self):
        """
        Return (H, priors, observable_matrix) numpy arrays for BP decoders.

        H is (detectors x mechanisms) uint8, observable_matrix is
        (observables x mechanisms) uint8, priors holds per-mechanism
        probabilities.
        """
        nm = len(self.mechanisms)
        h = np.zeros((self.num_detectors, nm), dtype=np.uint8)
        obs_mat = np.zeros((self.num_observables, nm), dtype=np.uint8)
        priors = np.zeros(nm)
        for m, (p, dets, obs) in enumerate(self.mechanisms):
            priors[m] = p
            for d in dets:
                h[d, m] = 1
            for o in obs:
                obs_mat[o, m] = 1

        return h, priors, obs_mat

    def weights(self):
        """
        Per-mechanism MWPM weights log((1-p)/p).
        """
        priors = np.array([p for p, _, _ in self.mechanisms])

        return np.log((1.0 - priors) / priors)

    def graphlike_edges(self):
        """
        Mechanisms flipping at most two detectors, as
        (detectors, observables, weight) tuples -- a matching graph.
        """
        edges = []
        for p, dets, obs in self.mechanisms:
            if len(dets) <= 2:
                weight = float(np.log((1.0 - p) / p))
                edges.append((tuple(sorted(dets)), tuple(sorted(obs)), weight))

        return edges
