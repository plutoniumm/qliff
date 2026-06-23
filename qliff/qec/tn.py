from __future__ import annotations

import numpy as np

from .dem import DetectorErrorModel

# Tensor-network primitives + a maximum-likelihood (MLD) decoder.
#
# MLD over a DetectorErrorModel is the contraction of a factor graph: every error
# mechanism is a binary variable carrying a bias tensor [1-p, p]; each detector
# imposes an XOR (parity) constraint pinned to the observed syndrome bit; each
# logical observable contributes a parity tensor with one OPEN leg. Contracting
# the network leaves a tensor indexed by the observables -- the total weight of
# every logical class -- and the argmax is the most likely correction. That is
# exact maximum-likelihood for the (first-order, independent) DEM, so it is never
# worse than MWPM / BP+OSD on the same model.
#
# The same primitives are complex-dtype-ready: a coherent-noise decoder sums
# branch AMPLITUDES (not probabilities) and reads |.|^2 at the open legs -- the
# one decoder family that survives non-Pauli noise, which no DEM decoder can.
# numpy only (BLAS einsum), matching dem.py; the Rust core stays the sampler.
#
# BOND TRUNCATION (max_bond): exact contraction cost scales with treewidth -- an
# intermediate tensor of k legs holds 2^k entries -- so it blows up past small
# distances. `contract(..., max_bond=chi)` caps that: before merging a pair whose
# SHARED bond (the product of its common legs, dim 2^s) exceeds chi, the bond is
# compressed by a truncated SVD that keeps only its chi largest singular values
# (Bravyi-Suchara-Vargo boundary contraction, done pairwise instead of as a full
# boundary MPS). Splitting a tensor as A=U.sqrt(S) and B=sqrt(S).Vh and discarding
# the tail singular values factors the bond through a rank-chi waist, so the merged
# tensor carries one bond of dim<=chi where it had 2^s, bounding intermediate size.
# As chi -> infinity no singular value is dropped and the result is bit-for-bit the
# exact contraction; at finite chi it is the best low-rank approximation of the cut.


class Tensor:
    """
    A dense array with one hashable label per axis (its "legs").
    """

    def __init__(self, data: np.ndarray, legs: tuple):
        self.data = np.asarray(data)
        self.legs = tuple(legs)

        if self.data.ndim != len(self.legs):
            raise ValueError(
                f"legs {self.legs} do not match data.ndim {self.data.ndim}"
            )


def _contract_pair(a: Tensor, b: Tensor) -> Tensor:
    """
    Contract two tensors over their shared legs (tensordot). Disjoint legs give
    an outer product. Each step touches only two operands, so it never hits the
    52-symbol ceiling of a single whole-network einsum.
    """
    shared = [leg for leg in a.legs if leg in b.legs]

    if len(shared) == 0:
        data = np.tensordot(a.data, b.data, axes=0)

        return Tensor(data, a.legs + b.legs)

    ax_a = [a.legs.index(leg) for leg in shared]
    ax_b = [b.legs.index(leg) for leg in shared]
    data = np.tensordot(a.data, b.data, axes=(ax_a, ax_b))
    rest = tuple(leg for leg in a.legs if leg not in shared)
    rest += tuple(leg for leg in b.legs if leg not in shared)

    return Tensor(data, rest)


def _compress_bond(a: Tensor, b: Tensor, max_bond: int) -> tuple[Tensor, Tensor]:
    """
    Truncate the shared bond between `a` and `b` to `max_bond`. The common legs
    are merged into one matrix index; a thin SVD keeps its `max_bond` largest
    singular values and splits the weight U.sqrt(S) into `a`, sqrt(S).Vh into `b`,
    replacing the old shared legs with one fresh bond of dim <= max_bond.
    """
    shared = [leg for leg in a.legs if leg in b.legs]
    bond_dim = int(np.prod([a.data.shape[a.legs.index(leg)] for leg in shared]))

    if bond_dim <= max_bond:
        return a, b

    a_rest = [leg for leg in a.legs if leg not in shared]
    b_rest = [leg for leg in b.legs if leg not in shared]
    a_perm = [a.legs.index(leg) for leg in a_rest] + [
        a.legs.index(leg) for leg in shared
    ]
    b_perm = [b.legs.index(leg) for leg in shared] + [
        b.legs.index(leg) for leg in b_rest
    ]
    a_shape = [a.data.shape[a.legs.index(leg)] for leg in a_rest]
    b_shape = [b.data.shape[b.legs.index(leg)] for leg in b_rest]
    a_mat = np.transpose(a.data, a_perm).reshape(-1, bond_dim)
    b_mat = np.transpose(b.data, b_perm).reshape(bond_dim, -1)
    m = a_mat @ b_mat
    u, s, vh = np.linalg.svd(m, full_matrices=False)
    k = min(max_bond, s.shape[0])
    root = np.sqrt(s[:k])
    new = ("bond", id(a), id(b))
    a_data = (u[:, :k] * root).reshape(a_shape + [k])
    b_data = (root[:, None] * vh[:k, :]).reshape([k] + b_shape)

    return Tensor(a_data, tuple(a_rest + [new])), Tensor(b_data, tuple([new] + b_rest))


def contract(
    tensors: list[Tensor], open_legs: list, max_bond: int | None = None
) -> Tensor:
    """
    Contract the network to its `open_legs` (every other leg is summed) by greedy
    pairwise contraction -- at each step join the pair whose result has the fewest
    legs, keeping intermediates small. Order never changes the value, only cost.
    Scalars (rank-0 tensors) fold in as a multiplicative factor. With `max_bond`
    set, a pair's shared bond is truncated to that bond dimension by SVD before
    merging, bounding intermediate size (exact as max_bond -> infinity).
    """
    scale = 1.0
    work: list[Tensor] = []

    for t in tensors:
        if t.data.ndim == 0:
            scale = scale * t.data.item()
        else:
            work.append(t)

    while len(work) > 1:
        best = None

        for i in range(len(work)):
            for j in range(i + 1, len(work)):
                shared = sum(1 for leg in work[i].legs if leg in work[j].legs)

                if shared == 0:
                    continue

                cost = work[i].data.ndim + work[j].data.ndim - 2 * shared

                if best is None or cost < best[0]:
                    best = (cost, i, j)

        # disconnected remainder: outer-product the first two.
        _, i, j = best if best is not None else (0, 0, 1)
        b = work.pop(j)
        a = work.pop(i)

        if max_bond is not None and best is not None:
            a, b = _compress_bond(a, b, max_bond)

        work.append(_contract_pair(a, b))

    if len(work) == 0:
        return Tensor(np.array(scale), ())

    res = work[0]

    if scale != 1.0:
        res = Tensor(res.data * scale, res.legs)

    perm = [res.legs.index(leg) for leg in open_legs]

    return Tensor(np.transpose(res.data, perm), tuple(open_legs))


def biased_copy(degree: int, p: float, dtype=float) -> np.ndarray:
    """
    A COPY tensor (all legs share one value) weighted (1-p) on the all-zero
    diagonal and p on the all-one diagonal: a binary variable fanned to `degree`
    legs with its prior folded in.
    """
    t = np.zeros((2,) * degree, dtype=dtype)
    t[(0,) * degree] = 1.0 - p
    t[(1,) * degree] = p

    return t


def parity(degree: int, target: int, dtype=float) -> np.ndarray:
    """
    An XOR constraint tensor: 1 where the leg indices sum to `target` (mod 2).
    """
    t = np.zeros((2,) * degree, dtype=dtype)

    for idx in np.ndindex(*t.shape):
        if sum(idx) % 2 == target:
            t[idx] = 1.0

    return t


def _dleg(m: int, d: int) -> tuple:
    # leg joining mechanism m's copy tensor to detector d's parity constraint.
    return ("d", m, d)


def _oleg(m: int, o: int) -> tuple:
    # leg joining mechanism m's copy tensor to observable o's parity tensor.
    return ("o", m, o)


def _obs_out(o: int) -> tuple:
    # the open leg carrying observable o's predicted flip bit.
    return ("obs", o)


class MaxLikelihoodDecoder:
    """
    Exact maximum-likelihood decoder via factor-graph tensor contraction over a
    DetectorErrorModel. Optimal on the DEM (>= MWPM/BP+OSD accuracy); cost grows
    with the network's treewidth, so it is the reference / small-to-mid-distance
    decoder. Registered as "mld" (and "tn"). Passing `max_bond=chi` caps the
    contraction's bond dimension via truncated SVD so it scales past small
    distances; `max_bond=None` (default) is the exact contraction.
    """

    def __init__(self, dem: DetectorErrorModel, max_bond: int | None = None):
        self.num_observables = dem.num_observables
        self.num_detectors = dem.num_detectors
        self.max_bond = max_bond

        self._priors = [p for p, _d, _o in dem.mechanisms]
        self._mech_dets = [sorted(dets) for _p, dets, _o in dem.mechanisms]
        self._mech_obs = [sorted(obs) for _p, _d, obs in dem.mechanisms]

        # incidence: which mechanisms touch each detector / observable.
        self._det_mechs = [[] for _ in range(self.num_detectors)]
        self._obs_mechs = [[] for _ in range(self.num_observables)]

        for m, dets in enumerate(self._mech_dets):
            for d in dets:
                self._det_mechs[d].append(m)

        for m, obs in enumerate(self._mech_obs):
            for o in obs:
                self._obs_mechs[o].append(m)

        # static tensors (syndrome-independent): one biased COPY per mechanism +
        # one parity tensor per observable (with its open leg).
        self._static = self._build_static()

        # per-shot only the detector tensors change; memoize the decoded result
        # per distinct syndrome (the all-zero syndrome dominates at low p).
        self._open = [_obs_out(o) for o in range(self.num_observables)]
        self._cache: dict = {}

    def _build_static(self) -> list[Tensor]:
        tensors: list[Tensor] = []

        for m, p in enumerate(self._priors):
            legs = [_dleg(m, d) for d in self._mech_dets[m]]
            legs += [_oleg(m, o) for o in self._mech_obs[m]]

            if len(legs) == 0:
                continue

            tensors.append(Tensor(biased_copy(len(legs), p), tuple(legs)))

        for o in range(self.num_observables):
            mechs = self._obs_mechs[o]
            legs = [_oleg(m, o) for m in mechs] + [_obs_out(o)]
            # XOR(incident) == open-leg  <=>  parity over all legs is even.
            tensors.append(Tensor(parity(len(legs), 0), tuple(legs)))

        return tensors

    def _detector_tensors(self, syndrome: np.ndarray) -> list[Tensor]:
        tensors: list[Tensor] = []

        for d in range(self.num_detectors):
            mechs = self._det_mechs[d]
            legs = [_dleg(m, d) for m in mechs]
            tensors.append(Tensor(parity(len(legs), int(syndrome[d])), tuple(legs)))

        return tensors

    def _decode_one(self, syndrome: np.ndarray) -> np.ndarray:
        tensors = self._static + self._detector_tensors(syndrome)
        weights = contract(tensors, self._open, max_bond=self.max_bond).data
        flat = np.asarray(weights).reshape(-1)

        if not np.any(flat > 0.0):
            # impossible syndrome under the model: default to no logical flip.
            return np.zeros(self.num_observables, dtype=np.uint8)

        best = int(np.argmax(flat))
        bits = np.unravel_index(best, (2,) * self.num_observables)

        return np.array(bits, dtype=np.uint8)

    def decode_batch(self, detection_events: np.ndarray) -> np.ndarray:
        det = np.ascontiguousarray(detection_events, dtype=np.uint8)
        shots = det.shape[0]
        preds = np.zeros((shots, self.num_observables), dtype=np.uint8)

        if det.shape[1] == 0 or self.num_observables == 0:
            return preds

        for s in range(shots):
            key = det[s].tobytes()
            hit = self._cache.get(key)

            if hit is None:
                hit = self._decode_one(det[s])
                self._cache[key] = hit

            preds[s] = hit

        return preds
