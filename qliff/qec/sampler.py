from __future__ import annotations

import random
from math import sqrt

import numpy as np

from .._core import ColTableau
from .._types import Targets
from ..noise.channel import make_channel
from ..noise.sampler import build_strata, compile_signed, fault_set, pick_branch
from ..simulator import CLIFFORD_OPS, Simulator

from ..circuit import Circuit


def _fold_records(
    records: np.ndarray, groups: list[Targets], refs: list[int]
) -> np.ndarray:
    """
    XOR-fold each record-index group against its noiseless reference bit, vectorised
    over shots: column j is the parity of records[:, i] for i in groups[j], flipped
    by refs[j]. Turns a raw (shots, num_meas) record array into detection events /
    observable flips.
    """
    shots = records.shape[0]
    out = np.zeros((shots, len(groups)), dtype=np.uint8)
    for j, recs in enumerate(groups):
        col = np.zeros(shots, dtype=np.uint8)
        for i in recs:
            col ^= records[:, i]

        out[:, j] = col ^ np.uint8(refs[j])

    return out


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
        array (shots,) of signed importance weights, one per trajectory. Built-in
        channels run the whole trajectory batch in the Rust signed sampler (rayon,
        one shared transpose per syndrome round); a custom channel with a branch op
        the core cannot lower falls back to the Python loop. Both draw one branch
        per noise location and carry weight prod(sign * gamma), so the weighted mean
        is unbiased either way -- only the RNG stream differs.
        """
        compiled = compile_signed(self.circuit)
        if compiled is None:
            return self._sample(shots, seed)

        instrs, tables = compiled
        rng_seed = random.Random(seed).getrandbits(64)
        core = ColTableau(self.circuit.num_qubits)
        buf, weights, num_meas = core.sample_batch_signed(
            instrs, tables, shots, rng_seed
        )
        records = np.frombuffer(buf, dtype=np.uint8).reshape(shots, num_meas)
        dets = _fold_records(records, self.circuit.detectors, self.det_ref)
        obs = _fold_records(
            records, [recs for _idx, recs in self.circuit.observables], self.obs_ref
        )

        return dets, obs, np.asarray(weights, dtype=np.float64)


class StratifiedDetectorSampler(_BaseSampler):
    """
    Low-variance detector sampler for NON-Pauli noise: stratify trajectories by
    fault count k, and let each stratum be SELF-NORMALISED downstream.

    WHY: WeightedDetectorSampler multiplies by gamma at every noise location, faulty
    or not, so every trajectory carries the same magnitude |w| = prod(gamma) = Gamma
    and only its SIGN varies. The estimator is then a plain mean of +/-Gamma, whose
    noise floor is Gamma while the signal is the logical error rate -- so it needs
    ~(Gamma/LER)^2 shots, and Gamma grows exponentially in the number of noise
    locations. That is the wall that makes amplitude-damping and coherent noise
    unaffordable past tiny patches.

    HOW: the true logical error rate is sum_k mass[k] * F_k, where mass[k] is the
    stratum's exact signed quasiprobability mass (computed analytically by
    stratum_masses, no sampling) and F_k is the CONDITIONAL error rate given k
    faults. Sampling a stratum with the |.|/gamma measure gives every trajectory in
    it the same |w| = Gamma * P(k), so estimating F_k as the RATIO
    sum(sign * wrong) / sum(sign) cancels that factor ALGEBRAICALLY: what survives
    depends only on the signs and is bounded. Gamma never enters the variance.

    This sampler therefore returns the raw per-shot SIGNS and each shot's stratum
    rather than a weight; the ratio and the mass-weighted sum happen in
    threshold._stratified_error_rate, which has the decoder's verdict. On Pauli
    noise every sign is +1 and mass[k] is the Poisson-binomial P(k), so the whole
    thing degenerates to ordinary stratified sampling.
    """

    strict = False
    # strata whose |mass| is below this fraction of the largest are not sampled;
    # the total mass actually dropped is recorded in `dropped_mass` after sample().
    MASS_TOL = 1e-12
    # a stratum estimated from ONE trajectory reports zero spread, which would
    # silently understate the error bar, so every sampled stratum gets at least two.
    # k=0 is exempt: it holds exactly one trajectory (the all-identity branch), so
    # its F_0 is exact and its variance really is zero.
    MIN_SHOTS = 2

    def __init__(self, circuit: Circuit):
        super().__init__(circuit)
        self.locs, self.phis, self.pk, self.mass = build_strata(circuit.instructions)
        self.dropped_mass = 0.0

    def _stratum_trajectory(
        self, k: int, rng: random.Random
    ) -> tuple[list[int], float]:
        # one trajectory conditioned on EXACTLY k faulty locations; returns the
        # measurement record and the product of the chosen branches' signs.
        faulty = fault_set(self.phis, k, rng)
        sim = Simulator(self.circuit.num_qubits, rng.getrandbits(63))
        sign = 1.0
        loc = 0

        for name, targets, _arg in self.circuit.instructions:
            if name in CLIFFORD_OPS:
                getattr(sim, name)(*targets)
                continue

            branches, _gamma = self.locs[loc]
            index = pick_branch(branches, rng) if loc in faulty else 0
            weight, ops = branches[index]
            if weight < 0.0:
                sign = -sign
            for gate, qubits in ops:
                getattr(sim, gate)(*qubits)
            loc += 1

        return sim.record, sign

    def allocate(
        self, shots: int, spread: dict[int, float] | None = None
    ) -> dict[int, int]:
        """
        Shots per stratum. The variance of the final estimate is
        Gamma^2 * sum_k P(k)^2 * V_k / n_k, so n_k proportional to P(k) exactly TIES
        flat importance sampling and Neyman's n_k proportional to P(k) * sqrt(V_k)
        provably beats it -- pass measured per-stratum spreads as `spread` to get
        that. Allocating by |mass| instead would be a TRAP: mass[k] = Gamma * P(k) *
        r^k with r the per-fault mean sign (r < 1), so it starves exactly the high-k
        strata that carry the failures. Strata below MASS_TOL, or that the budget
        cannot seat, are skipped and their mass banked in `dropped_mass`.
        """
        biggest = max((abs(m) for m in self.mass), default=0.0)
        live = [
            k
            for k, m in enumerate(self.mass)
            if abs(m) > self.MASS_TOL * biggest and self.pk[k] > 0.0
        ]
        weight = {
            k: self.pk[k] * (sqrt(spread[k]) if spread and spread.get(k) else 1.0)
            for k in live
        }
        # k=0 is a single trajectory whose value is exact; it never needs more.
        weight.pop(0, None)
        ranked = sorted(weight, key=lambda k: -weight[k])

        counts = {0: 1} if 0 in live else {}
        budget = shots - len(counts)
        for k in ranked:
            if budget < self.MIN_SHOTS:
                break
            counts[k] = self.MIN_SHOTS
            budget -= self.MIN_SHOTS

        total = sum(weight[k] for k in counts if k != 0)
        if total > 0.0:
            for k in counts:
                if k == 0:
                    continue
                counts[k] += int(budget * weight[k] / total)

        self.dropped_mass = sum(
            abs(m) for k, m in enumerate(self.mass) if k not in counts
        )

        return counts

    def sample(
        self,
        shots: int,
        seed: int | None = None,
        counts: dict[int, int] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        (detection_events, observable_flips, signs, strata): the first two uint8
        arrays shaped (shots, n_detectors)/(shots, n_observables), `signs` a float
        array of per-trajectory branch-sign products, and `strata` the int fault
        count each shot was drawn from. Pass an explicit `counts` (stratum -> shots,
        e.g. a Neyman allocation from a pilot pass) to override `allocate`; the
        realised shot count then follows it exactly.
        """
        rng = random.Random(seed)
        if counts is None:
            counts = self.allocate(shots)
        total = sum(counts.values())

        dets = np.zeros((total, len(self.circuit.detectors)), dtype=np.uint8)
        obs = np.zeros((total, len(self.circuit.observables)), dtype=np.uint8)
        signs = np.zeros(total, dtype=np.float64)
        strata = np.zeros(total, dtype=np.int64)

        s = 0
        for k in sorted(counts):
            for _i in range(counts[k]):
                record, sign = self._stratum_trajectory(k, rng)
                signs[s] = sign
                strata[s] = k
                for j, d in enumerate(self.circuit.detectors):
                    dets[s, j] = record_parity(record, d) ^ self.det_ref[j]
                for j, (_idx, recs) in enumerate(self.circuit.observables):
                    obs[s, j] = record_parity(record, recs) ^ self.obs_ref[j]
                s += 1

        return dets, obs, signs, strata
