import random

from ..simulator import CLIFFORD_OPS, Simulator
from .channel import make_channel


class MonteCarlo:
    """
    Plain Monte-Carlo trajectory sampler for Pauli noise.

    Each trajectory runs the circuit on a fresh stabilizer state, sampling one
    Pauli branch per noise location. Pauli channels only; coherent/general
    channels raise here and need :class:`ImportanceSampler`.
    """

    def __init__(self, circuit):
        self.circuit = circuit

    def _apply(self, sim, name, targets, arg, rng):
        if name in CLIFFORD_OPS:
            getattr(sim, name)(*targets)

            return
        channel = make_channel(name, arg)
        if not channel.is_pauli:
            raise ValueError(f"{name} is not a Pauli channel; use ImportanceSampler")
        _weight, ops = channel.sample(targets, rng)
        for gate, qubits in ops:
            getattr(sim, gate)(*qubits)

    def _trajectory(self, rng):
        sim = Simulator(self.circuit.num_qubits, rng.getrandbits(63))
        for name, targets, arg in self.circuit.instructions:
            self._apply(sim, name, targets, arg, rng)

        return sim

    def sample(self, shots, seed=None):
        """
        Run ``shots`` trajectories; return one measurement record (list of 0/1)
        per shot.
        """
        rng = random.Random(seed)
        out = []
        for _ in range(shots):
            out.append(self._trajectory(rng).measure_record)

        return out

    def expect(self, observable, shots, seed=None):
        """
        Estimate ``<O>`` by averaging a Pauli observable over trajectories.

        The circuit should end without measurements; the observable is peeked on
        each trajectory's final state.
        """
        rng = random.Random(seed)
        total = 0.0
        for _ in range(shots):
            total += self._trajectory(rng).peek_observable(observable)

        return total / shots


class ImportanceSampler:
    """
    Importance sampler for general (quasiprobability) noise.

    Each trajectory samples one stabilizer-channel branch per noise location and
    accumulates an importance weight (the product of the per-channel
    ``sign * gamma`` factors). ``expect`` returns the reweighted estimate of
    ``<O>``, which is unbiased for the true noisy expectation even when channels
    are coherent. Pauli channels work too (every weight is 1).
    """

    def __init__(self, circuit):
        self.circuit = circuit

    def _trajectory(self, rng):
        sim = Simulator(self.circuit.num_qubits, rng.getrandbits(63))
        weight = 1.0
        for name, targets, arg in self.circuit.instructions:
            if name in CLIFFORD_OPS:
                getattr(sim, name)(*targets)
            else:
                factor, ops = make_channel(name, arg).sample(targets, rng)
                weight *= factor
                for gate, qubits in ops:
                    getattr(sim, gate)(*qubits)

        return sim, weight

    def expect(self, observable, shots, seed=None):
        """
        Estimate ``<O>`` over ``shots`` reweighted trajectories.
        """
        rng = random.Random(seed)
        total = 0.0
        for _ in range(shots):
            sim, weight = self._trajectory(rng)
            total += weight * sim.peek_observable(observable)

        return total / shots


def _poisson_binomial(phis):
    """
    Probability of exactly k successes for independent Bernoulli ``phis``.

    Returns a list ``P`` with ``P[k]`` for k in 0..len(phis).
    """
    probs = [1.0]
    for phi in phis:
        nxt = [0.0] * (len(probs) + 1)
        for k, p in enumerate(probs):
            nxt[k] += p * (1.0 - phi)
            nxt[k + 1] += p * phi
        probs = nxt

    return probs


class StratifiedSampler:
    """
    Importance sampler stratified by fault count -- the variance-reduction layer.

    The estimate is ``sum_k P(k) F_k``: ``P(k)`` is the exact Poisson-binomial
    probability of ``k`` faulty locations and ``F_k`` the importance estimate
    conditioned on exactly ``k`` faults. Stratifying cuts variance versus a flat
    importance sampler at the same shot budget. Unbiased for any channel set.
    """

    def __init__(self, circuit):
        self.circuit = circuit
        self.locs = []
        self.phis = []
        for name, targets, arg in circuit.instructions:
            if name in CLIFFORD_OPS:
                continue
            branches = make_channel(name, arg).branches(targets)
            gamma = sum(abs(w) for w, _ in branches)
            gfault = sum(abs(w) for w, _ in branches[1:])
            self.locs.append((branches, gamma))
            self.phis.append(gfault / gamma if gamma > 0.0 else 0.0)
        self.pk = _poisson_binomial(self.phis)

    def _fault_set(self, k, rng):
        phis = self.phis
        a = len(phis)
        suffix = [[0.0] * (a + 1) for _ in range(a + 1)]
        suffix[a][0] = 1.0
        for i in range(a - 1, -1, -1):
            for j in range(a - i + 1):
                ways = (1.0 - phis[i]) * suffix[i + 1][j]
                if j >= 1:
                    ways += phis[i] * suffix[i + 1][j - 1]
                suffix[i][j] = ways
        chosen = set()
        need = k
        for i in range(a):
            if need == 0:
                break
            denom = suffix[i][need]
            if denom <= 0.0:
                continue
            if rng.random() < phis[i] * suffix[i + 1][need - 1] / denom:
                chosen.add(i)
                need -= 1

        return chosen

    def _pick_branch(self, branches, rng):
        faults = [
            (i + 1, w, ops) for i, (w, ops) in enumerate(branches[1:]) if w != 0.0
        ]
        threshold = rng.random() * sum(abs(w) for _, w, _ in faults)
        acc = 0.0
        for bidx, w, _ops in faults:
            acc += abs(w)
            if threshold <= acc:
                return bidx

        return faults[-1][0]

    def _shot(self, k, observable, rng):
        faulty = self._fault_set(k, rng)
        sim = Simulator(self.circuit.num_qubits, rng.getrandbits(63))
        weight = 1.0
        loc = 0
        for name, targets, _arg in self.circuit.instructions:
            if name in CLIFFORD_OPS:
                getattr(sim, name)(*targets)
            else:
                branches, gamma = self.locs[loc]
                idx = self._pick_branch(branches, rng) if loc in faulty else 0
                w, ops = branches[idx]
                weight *= (1.0 if w >= 0.0 else -1.0) * gamma
                for gate, qubits in ops:
                    getattr(sim, gate)(*qubits)
                loc += 1

        return weight * sim.peek_observable(observable)

    def expect(self, observable, shots, seed=None):
        """
        Stratified estimate of ``<O>`` using about ``shots`` trajectories.
        """
        rng = random.Random(seed)
        total = 0.0
        for k, pk in enumerate(self.pk):
            if pk <= 0.0:
                continue
            nk = max(1, round(shots * pk))
            acc = sum(self._shot(k, observable, rng) for _ in range(nk))
            total += pk * (acc / nk)

        return total
