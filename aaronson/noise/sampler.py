from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .._types import Branch, Targets
from ..pauli import PauliString
from ..simulator import CLIFFORD_OPS, Simulator
from .channel import make_channel

if TYPE_CHECKING:
    from ..circuit import Circuit


def _poisson_binomial(phis: list[float]) -> list[float]:
    probs = [1.0]
    for phi in phis:
        nxt = [0.0] * (len(probs) + 1)

        for k, p in enumerate(probs):
            nxt[k] += p * (1.0 - phi)
            nxt[k + 1] += p * phi

        probs = nxt

    return probs


class Sampler:
    """
    Trajectory sampler for a noisy circuit.
    expect():
        importance estimator, unbiased for any channel; reduces to plain
        Monte-Carlo on Pauli noise. stratify=True stratifies by fault count
        (exact Poisson-binomial P(k)) for lower variance at equal shots.
    sample():
        per-shot measurement records, Pauli only -- a bitstring can't carry a
        negative quasiprob weight, so non-Pauli raises.
    """

    def __init__(self, circuit: Circuit):
        self.circuit = circuit

    def _apply(
        self,
        sim: Simulator,
        name: str,
        targets: Targets,
        arg: object,
        rng: random.Random,
    ) -> None:
        if name in CLIFFORD_OPS:
            getattr(sim, name)(*targets)

            return

        channel = make_channel(name, arg)

        if not channel.is_pauli:
            raise ValueError(f"{name} is not a Pauli channel; use expect()")
        _weight, ops = channel.sample(targets, rng)

        for gate, qubits in ops:
            getattr(sim, gate)(*qubits)

    def _record_trajectory(self, rng: random.Random) -> Simulator:
        sim = Simulator(self.circuit.num_qubits, rng.getrandbits(63))

        for name, targets, arg in self.circuit.instructions:
            self._apply(sim, name, targets, arg, rng)

        return sim

    def sample(self, shots: int, seed: int | None = None) -> list[list[int]]:
        """
        Run shots trajectories; one measurement record (0/1 list) per shot.
        Pauli noise only -- a non-Pauli channel raises.
        """
        rng = random.Random(seed)
        out = []
        for _ in range(shots):
            out.append(self._record_trajectory(rng).record)

        return out

    def _weighted_trajectory(self, rng: random.Random) -> tuple[Simulator, float]:
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

    def expect(
        self,
        observable: PauliString | str,
        shots: int,
        seed: int | None = None,
        stratify: bool = False,
    ) -> float:
        """
        Estimate <observable>, unbiased for any channel. Each trajectory draws
        one branch per noise location with weight w = prod(sign * gamma);
        estimate = mean(w * <O>). stratify=True stratifies by fault count for
        lower variance.
        """
        if stratify:
            return self._expect_stratified(observable, shots, seed)

        rng = random.Random(seed)
        total = 0.0

        for _ in range(shots):
            sim, weight = self._weighted_trajectory(rng)
            total += weight * sim.peek(observable)

        return total / shots

    def _build_strata(self) -> tuple[list, list[float], list[float]]:
        # Lazily compute the per-location branch data and Poisson-binomial P(k)
        # used by stratified estimation; only paid when stratify=True is requested.
        locs = []
        phis = []

        for name, targets, arg in self.circuit.instructions:
            if name in CLIFFORD_OPS:
                continue
            branches = make_channel(name, arg).branches(targets)
            gamma = sum(abs(w) for w, _ in branches)
            gfault = sum(abs(w) for w, _ in branches[1:])
            locs.append((branches, gamma))
            phis.append(gfault / gamma if gamma > 0.0 else 0.0)

        return locs, phis, _poisson_binomial(phis)

    def _fault_set(self, phis: list[float], k: int, rng: random.Random) -> set[int]:
        # sample exactly k faulty locations from the Poisson-binomial.
        # suffix[i][j] = prob locations i.. yield j faults (DP, built backwards);
        # then walk forward, including i with its conditional prob given faults left.
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

    def _pick_branch(self, branches: list[Branch], rng: random.Random) -> int:
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

    def _shot(
        self,
        locs: list,
        phis: list[float],
        k: int,
        observable: PauliString | str,
        rng: random.Random,
    ) -> float:
        faulty = self._fault_set(phis, k, rng)
        sim = Simulator(self.circuit.num_qubits, rng.getrandbits(63))
        weight = 1.0
        loc = 0

        for name, targets, _arg in self.circuit.instructions:
            if name in CLIFFORD_OPS:
                getattr(sim, name)(*targets)
            else:
                branches, gamma = locs[loc]
                idx = self._pick_branch(branches, rng) if loc in faulty else 0
                w, ops = branches[idx]
                weight *= (1.0 if w >= 0.0 else -1.0) * gamma
                for gate, qubits in ops:
                    getattr(sim, gate)(*qubits)
                loc += 1

        return weight * sim.peek(observable)

    def _expect_stratified(
        self,
        observable: PauliString | str,
        shots: int,
        seed: int | None,
    ) -> float:
        # Estimate = sum_k P(k) F_k: P(k) the exact Poisson-binomial prob of k
        # faulty locations, F_k the importance estimate conditioned on k faults.
        # Lower variance than flat importance sampling at equal shots.
        locs, phis, pk = self._build_strata()
        rng = random.Random(seed)
        total = 0.0

        for k, p in enumerate(pk):
            if p <= 0.0:
                continue
            nk = max(1, round(shots * p))
            acc = sum(self._shot(locs, phis, k, observable, rng) for _ in range(nk))
            total += p * (acc / nk)

        return total
