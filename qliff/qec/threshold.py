from __future__ import annotations

from itertools import combinations, product
from math import sqrt
from typing import Callable, Iterator

import numpy as np

from ..circuit import Circuit
from ..noise.channel import make_channel
from ..simulator import CLIFFORD_OPS, Simulator
from .codes import logical_fidelity
from .decoder import make_decoder
from .dem import DetectorErrorModel
from .sampler import (
    DetectorSampler,
    StratifiedDetectorSampler,
    WeightedDetectorSampler,
    record_parity,
)

# Logical-error-rate measurement + physical-rate sweeps: sample a noisy circuit,
# decode, score predicted vs true observable flips. Pulls decoders (pymatching /
# ldpc) via qliff.qec.decoder, so import this module DIRECTLY -- never via
# qliff.qec.__init__ -- to keep `import qliff` numpy-only.


def _build_decoder(circuit: Circuit, decoder_name: str, max_bond: int | None = None):
    """
    Circuit-aware decoder construction. Prefer the circuit factory (lights up the
    `coherent` non-Pauli decoder once it lands); fall back to a DEM-backed decoder
    so the Pauli decoders (mwpm/bposd/mld/tn) work today. `max_bond` caps the tensor
    contraction's bond dimension and only the truncating decoders accept it.
    """
    try:
        from .decoder import make_circuit_decoder

        return make_circuit_decoder(decoder_name, circuit, max_bond)
    except (ImportError, AttributeError):
        return make_decoder(decoder_name, DetectorErrorModel(circuit), max_bond)


def _has_nonpauli_noise(circuit: Circuit) -> bool:
    """
    True if any noise instruction is a non-Pauli (coherent / damping) channel,
    which has no honest detector-error model and needs weighted sampling.
    """
    for name, _targets, arg in circuit.instructions:
        try:
            channel = make_channel(name, arg)
        except NotImplementedError:
            continue

        if not channel.is_pauli:
            return True

    return False


def _weighted_error_rate(
    circuit: Circuit, decoder, shots: int, seed: int | None
) -> tuple[float, float]:
    """
    Quasiprobability LER for non-Pauli noise: the importance-weighted fraction of
    mis-decoded shots. stderr is the standard error of that weighted mean.
    """
    dets, obs, weights = WeightedDetectorSampler(circuit).sample(shots, seed)
    predictions = decoder.decode_batch(dets)

    if shots == 0:
        return 0.0, 0.0

    if obs.shape[1] == 0:
        errors = np.zeros(shots, dtype=np.float64)
    else:
        errors = np.any(predictions != obs, axis=1).astype(np.float64)

    contrib = weights * errors
    ler = float(np.mean(contrib))
    stderr = float(np.std(contrib) / sqrt(shots))

    return min(1.0, max(0.0, ler)), stderr


def _gamma(sampler: StratifiedDetectorSampler) -> float:
    """
    prod(gamma) over the circuit's noise locations -- the weight MAGNITUDE every
    stratified trajectory carries (up to P(k)); needed to turn a stratum's signed
    mean back into an absolute LER contribution.
    """
    total = 1.0
    for _branches, gamma in sampler.locs:
        total *= gamma

    return total


def _loo_beta(sw: np.ndarray, s: np.ndarray) -> np.ndarray:
    """
    Per-shot LEAVE-ONE-OUT control-variate coefficient beta_i = Cov_{-i}(s*w, s) /
    Var_{-i}(s), each computed WITHOUT its own shot. Signs are +/-1 so w = s*(s*w)
    and Var(s) = 1 - mean(s)^2; the leave-one-out sums are formed by subtracting shot
    i from the pooled totals, an O(n) vectorised pass. Because beta_i is independent
    of shot i, using it in y_i = s*w - beta_i * (s - r_k) reintroduces NO bias while
    still spending n-1 shots on each beta (unlike two-fold cross-fitting, which spends
    only half). Var_{-i}(s) ~ 0 (signs do not vary) -> beta_i = 0, i.e. the flat mean.
    """
    n = s.size
    if n < 3:
        return np.zeros(n, dtype=np.float64)

    w = sw * s
    m1 = (s.sum() - s) / (n - 1)
    msw = (sw.sum() - sw) / (n - 1)
    mw = (w.sum() - w) / (n - 1)
    cov = mw - msw * m1
    var = 1.0 - m1 * m1

    return np.where(var > 1e-12, cov / np.where(var > 1e-12, var, 1.0), 0.0)


def _cv_stratum(coef: float, r_k: float, s: np.ndarray, wrong: np.ndarray) -> tuple:
    """
    Control-variate LER contribution + variance for ONE stratum. Returns
    (coef * mean(y), coef^2 * Var(y) / n) where y = s*w - beta_loo * (s - r_k) is the
    per-shot control-variate variable. E[s] = r_k exactly, so E[y] = E[s*w] for any
    beta and the contribution is unbiased with NO denominator to blow up; the
    leave-one-out beta is the variance-optimal Cov(s*w, s)/Var(s), giving a variance
    provably no worse than the flat mean (beta = 0) or the self-normalised ratio.
    """
    sw = s * wrong
    y = sw - _loo_beta(sw, s) * (s - r_k)
    n = s.size
    contribution = coef * float(y.mean())
    variance = coef**2 * float(y.var(ddof=1)) / n if n > 1 else 0.0

    return contribution, variance


def _stratified_error_rate(
    circuit: Circuit, decoder, shots: int, seed: int | None
) -> tuple[float, float]:
    """
    Control-variate stratified LER for non-Pauli noise: sum_k coef[k] * mean(y_k),
    where coef[k] = Gamma * P(k) is the (exactly known) weight magnitude of a stratum-k
    trajectory and y = s*w - beta * (s - r_k) is the per-shot control-variate variable.
    Here s is the branch-sign product, w the mis-decoded indicator, and r_k =
    mass[k] / coef[k] = E[s] the EXACTLY known mean sign of the stratum. Because
    E[s] = r_k analytically, E[y] = E[s*w] for ANY fixed beta, so coef[k] * mean(y)
    is an UNBIASED estimate of the stratum's LER contribution with NO denominator to
    blow up -- unlike the self-normalised ratio sum(s*w)/sum(s), which diverged when a
    stratum's signs nearly cancelled (the 0.27x regression). beta is LEAVE-ONE-OUT
    (see _loo_beta), so it never biases the shot it scores; at the optimal beta =
    Cov(s*w, s)/Var(s) the variance is provably no worse than either the flat estimator
    or the ratio. stderr is the per-stratum standard error combined in quadrature.
    """
    sampler = StratifiedDetectorSampler(circuit)
    gamma = _gamma(sampler)

    def verdicts(counts, pass_seed):
        dets, obs, signs, strata = sampler.sample(0, pass_seed, counts=counts)
        predictions = np.asarray(decoder.decode_batch(dets))
        wrong = np.any(predictions != obs, axis=1).astype(np.float64)

        return signs, strata, wrong

    # Pilot pass proportional to P(k), then spend the rest by Neyman: shots follow
    # P(k) * sqrt(V_k), so strata that never fail (every low-k one, below threshold)
    # stop consuming budget and the failures get resolved instead. Proportional
    # allocation alone only TIES flat sampling; this is where the win comes from.
    pilot_counts = sampler.allocate(max(1, shots // 4))
    p_signs, p_strata, p_wrong = verdicts(pilot_counts, seed)

    # a stratum that never failed in the pilot is not proof it cannot fail, so floor
    # the spread at one pseudo-failure: Neyman then still funds it, just lightly. The
    # Neyman proxy is the flat within-stratum variance Var(s*w), which the control
    # variate can only shrink, so it never under-funds a stratum.
    spread = {}
    for k, n in pilot_counts.items():
        pick = p_strata == k
        flat = p_signs[pick] * p_wrong[pick]
        floor = 1.0 / max(n, 2) ** 2
        spread[k] = max(float(flat.var()) if flat.size > 1 else 0.0, floor)

    rest = shots - sum(pilot_counts.values())
    if rest > 0:
        extra = sampler.allocate(rest, spread=spread)
        m_signs, m_strata, m_wrong = verdicts(extra, None if seed is None else seed + 1)
    else:
        m_signs = np.zeros(0, dtype=np.float64)
        m_strata = np.zeros(0, dtype=np.int64)
        m_wrong = np.zeros(0, dtype=np.float64)

    signs = np.concatenate([p_signs, m_signs])
    strata = np.concatenate([p_strata, m_strata])
    wrong = np.concatenate([p_wrong, m_wrong])

    ler = 0.0
    variance = 0.0
    for raw in np.unique(strata):
        k = int(raw)
        coef = gamma * sampler.pk[k]
        if coef == 0.0:
            continue

        r_k = sampler.mass[k] / coef
        pick = strata == k
        contribution, var_k = _cv_stratum(coef, r_k, signs[pick], wrong[pick])
        ler += contribution
        variance += var_k

    return ler, sqrt(variance)


# Asymptote-pinned interpolation (opt-in). The self-normalised sign is only resolvable
# while <sign>_k = r_k stays above the sampling noise (k <~ 7 for amplitude damping,
# k <~ 2 for coherent RZ); past that F_k is garbage. So instead of paying for those
# strata, the interpolation pins the asymptotes and samples only the critical zone
# between them. The LOWER asymptote is MEASURED, never assumed: an exhaustive low-k
# scan pins F_k exactly for small k. This matters because the paper's assumption that
# F_k is trivial for k <= (d-1)/2 is FALSE for the unprotected surface-code colourings
# (css-EZ / css-OZ fail on a SINGLE amplitude-damping event, css-EX / css-OX do not),
# real physics the scan catches and an assumption would miss. The UPPER asymptote is
# F_k -> 0.5 as the logical state fully mixes, well supported by the clean logistic
# saturation of the unsigned conditional failure rate. Strata above the resolvable
# zone are pinned to the upper asymptote and the bias that introduces is bounded and
# reported (mass-weighted deviation from the pin).

_UPPER_ASYMPTOTE = 0.5


def _fault_branch_indices(sampler: StratifiedDetectorSampler) -> list[list[int]]:
    """
    Per noise location, the indices of its nonzero FAULT branches (never the identity
    branch 0) -- the choices an exactly-k-fault configuration draws from.
    """
    out = []
    for branches, _gamma in sampler.locs:
        out.append([i for i in range(1, len(branches)) if branches[i][0] != 0.0])

    return out


def _stratum_config_count(fault_indices: list[list[int]], k: int) -> int:
    """
    Exact number of exactly-k-fault configurations: the elementary symmetric
    polynomial e_k of the per-location fault-branch counts (choose which k locations
    fault, times the product of their branch counts).
    """
    poly = [1]
    for choices in fault_indices:
        size = len(choices)
        nxt = poly + [0]
        for j in range(len(poly) - 1, -1, -1):
            nxt[j + 1] += poly[j] * size
        poly = nxt

    return poly[k] if k < len(poly) else 0


def _run_fault_config(
    sampler: StratifiedDetectorSampler,
    circuit: Circuit,
    assignment: dict[int, int],
    seed: int | None,
) -> tuple[list[int], list[int], float]:
    """
    Run the circuit with a FIXED fault assignment {noise-location: branch index}
    (unlisted locations take their identity branch) and return
    (detection_events, observable_flips, signed_weight). The signed weight is the
    exact product of the chosen branch weights -- the trajectory's quasiprobability.
    Records are deterministic for Clifford fault branches; a reset branch injects
    genuine randomness, so those configurations are averaged over `seed` draws.
    """
    sim = Simulator(circuit.num_qubits, seed)
    weight = 1.0
    loc = 0

    for name, targets, _arg in circuit.instructions:
        if name in CLIFFORD_OPS:
            getattr(sim, name)(*targets)
            continue

        branches, _gamma = sampler.locs[loc]
        w, ops = branches[assignment.get(loc, 0)]
        weight *= w
        for gate, qubits in ops:
            getattr(sim, gate)(*qubits)
        loc += 1

    record = sim.record
    dets = [
        record_parity(record, d) ^ ref
        for d, ref in zip(circuit.detectors, sampler.det_ref)
    ]
    obs = [
        record_parity(record, recs) ^ ref
        for (_i, recs), ref in zip(circuit.observables, sampler.obs_ref)
    ]

    return dets, obs, weight


def _has_reset_branch(sampler: StratifiedDetectorSampler, assignment: dict) -> bool:
    # a fault config is deterministic unless one chosen branch performs a reset ("R"),
    # which collapses the qubit and randomises the syndrome -> needs outcome averaging.
    for loc, idx in assignment.items():
        _w, ops = sampler.locs[loc][0][idx]
        if any(gate == "R" for gate, _q in ops):
            return True

    return False


def _scan_stratum(
    sampler: StratifiedDetectorSampler,
    circuit: Circuit,
    decoder,
    k: int,
    fault_indices: list[list[int]],
    reps: int,
    seed: int | None,
) -> tuple[float, float, float, int]:
    """
    Exhaustively enumerate every exactly-k-fault configuration and return
    (ler_k, mass_k, variance_k, n_configs). ler_k = sum_config weight * P(wrong|config)
    is the stratum's EXACT signed LER contribution; mass_k = sum_config weight matches
    the analytic stratum mass. Deterministic (Clifford) configs are scored once;
    reset-bearing configs are averaged over `reps` outcome draws, whose Monte-Carlo
    error propagates into variance_k. This pins the lower asymptote per circuit.
    """
    rows = []
    weights = []
    reps_per = []
    rng = np.random.default_rng(seed)
    nloc = len(sampler.locs)

    for chosen in combinations(range(nloc), k):
        for assign in product(*(fault_indices[c] for c in chosen)):
            assignment = dict(zip(chosen, assign))
            r = reps if _has_reset_branch(sampler, assignment) else 1
            for _ in range(r):
                s = None if seed is None else int(rng.integers(1 << 62))
                dets, obs, weight = _run_fault_config(sampler, circuit, assignment, s)
                rows.append((dets, obs))
                weights.append(weight / r)
            reps_per.append(r)

    if not rows:
        return 0.0, 0.0, 0.0, 0

    dets = np.array([r[0] for r in rows], dtype=np.uint8)
    obs = np.array([r[1] for r in rows], dtype=np.uint8)
    weights = np.array(weights, dtype=np.float64)
    predictions = np.asarray(decoder.decode_batch(dets))
    if obs.shape[1] == 0:
        wrong = np.zeros(dets.shape[0], dtype=np.float64)
    else:
        wrong = np.any(predictions != obs, axis=1).astype(np.float64)

    ler_k = float((weights * wrong).sum())
    mass_k = float(weights.sum())
    # variance only from the reset-outcome averaging: deterministic configs add none.
    variance_k = 0.0
    i = 0
    for r in reps_per:
        if r > 1:
            block = wrong[i : i + r]
            w = float(weights[i])  # each rep already carries weight/r
            variance_k += (w * r) ** 2 * float(block.var()) / r
        i += r

    return ler_k, mass_k, variance_k, len(reps_per)


def _region_counts(
    pk: list[float], strata: list[int], budget: int, spread: dict | None = None
) -> dict[int, int]:
    # Neyman allocation of `budget` shots across a chosen subset of strata: shots
    # proportional to P(k) * sqrt(spread[k]); every stratum gets at least two so it can
    # report a spread. Used for the interpolation's critical zone only.
    weight = {
        k: pk[k] * (sqrt(spread[k]) if spread and spread.get(k) else 1.0)
        for k in strata
    }
    counts = {}
    for k in strata:
        if budget < 2:
            break
        counts[k] = 2
        budget -= 2

    total = sum(weight[k] for k in counts)
    if total > 0.0:
        for k in counts:
            counts[k] += int(budget * weight[k] / total)

    return counts


def _interpolated_error_rate(
    circuit: Circuit,
    decoder,
    shots: int,
    seed: int | None,
    exact_budget: int = 4000,
    sign_floor: float = 0.05,
    reps: int = 12,
) -> tuple[float, float, float]:
    """
    Asymptote-pinned stratified LER for non-Pauli noise, plus a bound on the bias the
    pinning introduces. Three regions:
      EXACT  (low k, <= exact_budget configs): F_k measured by an exhaustive scan --
             pins the LOWER asymptote per circuit, catching single-fault failures.
      SAMPLED (r_k resolvable, |r_k| >= sign_floor): the critical zone, estimated with
             the control-variate sampler and the full shot budget.
      PINNED (|r_k| < sign_floor): F_k fixed to the UPPER asymptote 0.5.
    Returns (ler, stderr, bias_bound). bias_bound is the mass-weighted deviation of the
    pinned strata from the pin, (0.5 - F_ref) * sum |mass[k]| over pinned k, where F_ref
    is the largest measured F_k; it is valid when F_k is monotone non-decreasing and
    bounded above by 0.5, which the measured unsigned failure rate supports.
    """
    sampler = StratifiedDetectorSampler(circuit)
    gamma = _gamma(sampler)
    fault_indices = _fault_branch_indices(sampler)
    live = [k for k in range(len(sampler.mass)) if sampler.pk[k] > 0.0]

    def coef_of(k):
        return gamma * sampler.pk[k]

    def r_of(k):
        c = coef_of(k)

        return sampler.mass[k] / c if c != 0.0 else 0.0

    # EXACT region: the low-k prefix the config budget can afford (always k = 0, 1).
    exact = []
    for k in live:
        if k > 0 and _stratum_config_count(fault_indices, k) > exact_budget:
            break
        exact.append(k)

    ler = 0.0
    variance = 0.0
    # F_ref anchors the bias bound and must be a trustworthy LOWER bound on the true
    # F at the pinning boundary, so it comes from the EXACT scan only -- a noisy
    # sampled F_k could overshoot 0.5 and silently zero the bound.
    exact_f = []
    for k in exact:
        ler_k, _mass_k, var_k, _n = _scan_stratum(
            sampler, circuit, decoder, k, fault_indices, reps, seed
        )
        ler += ler_k
        variance += var_k
        if sampler.mass[k] != 0.0:
            exact_f.append(ler_k / sampler.mass[k])

    # SAMPLED region: resolvable strata above the exact prefix.
    sampled = [k for k in live if k not in exact and abs(r_of(k)) >= sign_floor]
    if sampled:
        pilot = _region_counts(sampler.pk, sampled, max(1, shots // 4))
        p_dets, p_obs, p_signs, p_strata = sampler.sample(0, seed, counts=pilot)
        p_pred = np.asarray(decoder.decode_batch(p_dets))
        p_wrong = np.any(p_pred != p_obs, axis=1).astype(np.float64)
        spread = {}
        for k, n in pilot.items():
            flat = p_signs[p_strata == k] * p_wrong[p_strata == k]
            spread[k] = max(float(flat.var()) if flat.size > 1 else 0.0, 1.0 / n**2)

        rest = shots - sum(pilot.values())
        signs, strata, wrong = p_signs, p_strata, p_wrong
        if rest > 0:
            extra = _region_counts(sampler.pk, sampled, rest, spread)
            m_dets, m_obs, m_signs, m_strata = sampler.sample(
                0, None if seed is None else seed + 1, counts=extra
            )
            m_pred = np.asarray(decoder.decode_batch(m_dets))
            m_wrong = np.any(m_pred != m_obs, axis=1).astype(np.float64)
            signs = np.concatenate([signs, m_signs])
            strata = np.concatenate([strata, m_strata])
            wrong = np.concatenate([wrong, m_wrong])

        for k in sampled:
            pick = strata == k
            if not pick.any():
                continue
            contribution, var_k = _cv_stratum(
                coef_of(k), r_of(k), signs[pick], wrong[pick]
            )
            ler += contribution
            variance += var_k

    # PINNED region: everything else -> upper asymptote, with a reported bias bound.
    # Under a monotone non-decreasing F_k bounded above by 0.5, the true pinned F_k
    # lies in [F_ref, 0.5], so the pinned deviation is at most (0.5 - F_ref) per unit
    # of |mass|. F_ref is the largest EXACT-region F (monotone -> the boundary value).
    pinned = [k for k in live if k not in exact and k not in sampled]
    pinned_mass = sum(sampler.mass[k] for k in pinned)
    ler += _UPPER_ASYMPTOTE * pinned_mass

    f_ref = min(_UPPER_ASYMPTOTE, max([0.0, *exact_f]))
    bias_bound = (_UPPER_ASYMPTOTE - f_ref) * sum(abs(sampler.mass[k]) for k in pinned)

    return ler, sqrt(variance), bias_bound


def logical_error_rate(
    circuit: Circuit,
    decoder_name: str = "mwpm",
    shots: int = 10000,
    seed: int | None = None,
    max_bond: int | None = None,
    stratify: bool = False,
    interpolate: bool = False,
) -> tuple[float, float]:
    """
    (ler, stderr) for one circuit: sample -> decode -> compare. Pauli noise uses
    the binomial standard error sqrt(ler*(1-ler)/shots); non-Pauli noise uses
    importance-weighted sampling (the only honest path for coherent channels).
    `max_bond` caps the bond dimension of the tensor-network decoders ("tn" and
    "coherent"), trading exactness for a coarser contraction; None (the default) is
    the exact contraction, and the decoders with no contraction to truncate raise
    rather than silently ignore it. `stratify` switches the non-Pauli path to the
    control-variate stratified estimator, which drops the prod(gamma) variance factor
    (see _stratified_error_rate); it has no effect on Pauli noise. `interpolate`
    (implies stratify) additionally PINS the stratum asymptotes -- exhaustive low-k
    scan for the lower end, F_k -> 0.5 for the upper -- and samples only the resolvable
    middle; it is faster on deep circuits but introduces a bounded bias, so it is
    opt-in and the bias bound is available from _interpolated_error_rate.
    """
    decoder = _build_decoder(circuit, decoder_name, max_bond)

    if _has_nonpauli_noise(circuit):
        if interpolate:
            ler, stderr, _bias = _interpolated_error_rate(circuit, decoder, shots, seed)

            return ler, stderr

        if stratify:
            return _stratified_error_rate(circuit, decoder, shots, seed)

        return _weighted_error_rate(circuit, decoder, shots, seed)

    dets, obs = DetectorSampler(circuit).sample(shots, seed)
    predictions = decoder.decode_batch(dets)

    ler = 1.0 - logical_fidelity(predictions, obs)
    stderr = sqrt(ler * (1.0 - ler) / shots) if shots > 0 else 0.0

    return ler, stderr


def isweep(
    circuit_fn: Callable[[float], Circuit],
    p_values: list[float],
    decoder_name: str = "mwpm",
    shots: int = 10000,
    seed: int | None = None,
    max_bond: int | None = None,
) -> Iterator[tuple[float, float, float]]:
    """
    Stream (p, ler, stderr) one point at a time -- circuit_fn(p) builds the
    circuit for each physical rate. The seed is fixed across points so the curve
    is reproducible. `max_bond` threads through to the decoder unchanged.
    """
    for p in p_values:
        circuit = circuit_fn(p)
        ler, stderr = logical_error_rate(circuit, decoder_name, shots, seed, max_bond)
        yield p, ler, stderr


def sweep(
    circuit_fn: Callable[[float], Circuit],
    p_values: list[float],
    decoder_name: str = "mwpm",
    shots: int = 10000,
    seed: int | None = None,
    max_bond: int | None = None,
) -> list[tuple[float, float, float]]:
    """
    Eagerly collect the full (p, ler, stderr) curve; see `isweep` to stream.
    """
    return list(isweep(circuit_fn, p_values, decoder_name, shots, seed, max_bond))
