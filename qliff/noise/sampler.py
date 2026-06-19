from __future__ import annotations

import random

import numpy as np

from .._core import ColTableau
from .._types import Branch
from ..circuit import Circuit
from ..pauli import PauliString
from ..simulator import CLIFFORD_OPS, GATE_OPCODE, GATES_1, GATES_2, MEAS, Simulator
from .channel import make_channel

_UNSET = object()  # sentinel: CompiledSampler reference not computed yet


def _compile_branches(branches: list[Branch]) -> list | None:
    # convert a channel's (weight, ops) branches to (weight, [(opcode, a, b), ...])
    # for the Rust sampler; None if any branch op has no core opcode.
    table = []
    for weight, ops in branches:
        cops = []
        for gate, qubits in ops:
            code = GATE_OPCODE.get(gate)
            if code is None:
                return None

            b = qubits[1] if len(qubits) == 2 else 0
            cops.append((code, qubits[0], b))
        table.append((float(weight), cops))

    return table


def _compile_estimate_branches(branches: list[Branch]) -> list | None:
    # (SIGNED weight, [(opcode, a, b), ...]) per branch for the Rust estimator;
    # opcode 9 = reset. None if a branch op has no core opcode.
    table = []
    for weight, ops in branches:
        cops = []
        for gate, qubits in ops:
            if gate == "R":
                cops.append((9, qubits[0], 0))
                continue

            code = GATE_OPCODE.get(gate)
            if code is None:
                return None

            b = qubits[1] if len(qubits) == 2 else 0
            cops.append((code, qubits[0], b))
        table.append((float(weight), cops))

    return table


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

    def _compile(self) -> tuple[list, list] | None:
        # Lower the circuit to the Rust batched sampler: a flat instruction stream
        # (kind, x, y, z) plus per-noise-op Pauli branch tables. Return None (->
        # Python fallback) for any non-Pauli channel or a branch op with no opcode
        # (e.g. a custom Channel emitting a gate the core doesn't know).
        instrs = []
        tables = []

        for name, targets, arg in self.circuit.instructions:
            if name in GATES_1:
                op = GATE_OPCODE[name]
                instrs.extend((0, op, q, 0) for q in targets)
            elif name in GATES_2:
                op = GATE_OPCODE[name]
                instrs.extend(
                    (0, op, targets[k], targets[k + 1])
                    for k in range(0, len(targets), 2)
                )
            elif name == "M":
                instrs.extend((1, 0, q, 0) for q in targets)
            elif name == "MR":
                instrs.extend((1, 1, q, 0) for q in targets)
            elif name == "R":
                instrs.extend((1, 2, q, 0) for q in targets)
            else:
                channel = make_channel(name, arg)
                if not channel.is_pauli:
                    return None

                table = _compile_branches(channel.branches(targets))
                if table is None:
                    return None

                instrs.append((2, len(tables), 0, 0))
                tables.append(table)

        return instrs, tables

    def sample(self, shots: int, seed: int | None = None) -> np.ndarray:
        """
        Run shots trajectories; return a uint8 (shots, measurements) array, one
        row per shot. Pauli noise only -- a non-Pauli channel raises. Built-in
        Pauli noise runs in the Rust batched sampler; a custom channel falls back
        to Python.
        """
        return CompiledSampler(self.circuit).sample(shots, seed)

    def _sample_python(self, shots: int, seed: int | None) -> np.ndarray:
        # Fallback: one tableau per shot in Python, but each Channel built once
        # (not per shot). Used when _compile can't lower the circuit.
        prepared = [
            (name, targets, None if name in CLIFFORD_OPS else make_channel(name, arg))
            for name, targets, arg in self.circuit.instructions
        ]
        rng = random.Random(seed)
        out = []

        for _ in range(shots):
            sim = Simulator(self.circuit.num_qubits, rng.getrandbits(63))
            for name, targets, channel in prepared:
                if channel is None:
                    getattr(sim, name)(*targets)
                    continue
                if not channel.is_pauli:
                    raise ValueError(f"{name} is not a Pauli channel; use expect()")
                _weight, ops = channel.sample(targets, rng)
                for gate, qubits in ops:
                    getattr(sim, gate)(*qubits)
            out.append(sim.record)

        return np.array(out, dtype=np.uint8)

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

    def _compile_estimate(self) -> tuple[list, list] | None:
        # Lower the circuit to the Rust importance estimator: gates + SIGNED-weight
        # noise branches (Pauli / Clifford / reset). None (-> Python fallback) for a
        # mid-circuit measurement (estimate evaluates <O> on the final state) or a
        # channel op with no core opcode (a custom non-Clifford gate).
        instrs = []
        tables = []

        for name, targets, arg in self.circuit.instructions:
            if name in GATES_1:
                op = GATE_OPCODE[name]
                instrs.extend((0, op, q, 0) for q in targets)
            elif name in GATES_2:
                op = GATE_OPCODE[name]
                instrs.extend(
                    (0, op, targets[k], targets[k + 1])
                    for k in range(0, len(targets), 2)
                )
            elif name in MEAS:
                return None
            else:
                table = _compile_estimate_branches(
                    make_channel(name, arg).branches(targets)
                )
                if table is None:
                    return None

                instrs.append((2, len(tables), 0, 0))
                tables.append(table)

        return instrs, tables

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
        lower variance. Built-in channels run the trajectory loop in Rust (rayon);
        a custom channel or a mid-circuit measurement falls back to Python.
        """
        if stratify:
            return self._expect_stratified(observable, shots, seed)

        obs = observable
        if isinstance(obs, str):
            obs = PauliString.parse(obs)
        if obs.phase % 2 == 1:
            raise ValueError("observable must be Hermitian (phase +1 or -1)")

        compiled = None
        if obs.n == self.circuit.num_qubits:
            compiled = self._compile_estimate()

        if compiled is not None:
            instrs, tables = compiled
            rng_seed = random.Random(seed).getrandbits(64)
            core = ColTableau(self.circuit.num_qubits)
            est = core.estimate(instrs, tables, obs.x, obs.z, shots, rng_seed)

            return -est if obs.phase == 2 else est

        # fallback: per-trajectory Python loop (custom channel or mid-circuit measure)
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
        # fmt: off
        faults = [
            (i + 1, w, ops)
                for i, (w, ops) in enumerate(branches[1:])
                if w != 0.0
        ]
        # fmt: on
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


class CompiledSampler:
    """
    Reusable sampler: lower the circuit to the Rust batched sampler once, then
    sample(shots) repeatedly without recompiling -- amortizes the compile across
    calls (e.g. logical-error-rate sweeps). Built-in Pauli noise runs in Rust; a
    custom / non-Pauli channel falls back to the Python loop, like Sampler.sample.
    """

    def __init__(self, circuit: Circuit):
        self._sampler = Sampler(circuit)
        self._compiled = self._sampler._compile()
        self._core = None if self._compiled is None else ColTableau(circuit.num_qubits)
        # cached noiseless reference (circuit-only): _UNSET until first sample();
        # then None (a measurement is random -> sample_batch) or the ref bit list.
        self._ref = _UNSET

    def sample(self, shots: int, seed: int | None = None) -> np.ndarray:
        if self._compiled is None:
            return self._sampler._sample_python(shots, seed)

        instrs, tables = self._compiled
        rng_seed = random.Random(seed).getrandbits(64)

        # The reference run is the frame sampler's one serial cost and depends only
        # on the circuit -> compute it ONCE and reuse across calls (amortizes it
        # over an LER sweep). None => a measurement is random => per-shot sample_batch.
        if self._ref is _UNSET:
            self._ref = self._core.frame_reference(instrs)

        if self._ref is None:
            buf, num_meas = self._core.sample_batch(instrs, tables, shots, rng_seed)
        else:
            buf, num_meas = self._core.frame_run(
                instrs, tables, self._ref, shots, rng_seed
            )

        return np.frombuffer(buf, dtype=np.uint8).reshape(shots, num_meas)
