from __future__ import annotations

import numpy as np

from .decoder import BatchDecoder
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
# distances. `contract(..., max_bond=chi)` is the standard remedy for that: before
# merging a pair whose SHARED bond (the product of its common legs, dim 2^s) exceeds
# chi, the bond is compressed by a truncated SVD that keeps only its chi largest
# singular values (Bravyi-Suchara-Vargo boundary contraction, done pairwise instead of
# a full boundary MPS). Splitting a tensor as A=U.sqrt(S) and B=sqrt(S).Vh and
# discarding the tail singular values factors the bond through a rank-chi waist, so
# the pair merges through a dim<=chi waist where it had 2^s. As chi -> infinity no
# singular value is dropped and the result is bit-for-bit the exact contraction; at
# finite chi each merge is the best rank-chi approximation of its cut.
#
# WHAT IT DOES NOT DO (yet): the PAIRWISE form compresses a bond by SVD-ing the
# pair's product, which it materializes first, and the merged tensor's legs are the
# two operands' free legs either way -- so a merge's result size is the same with and
# without chi. Today max_bond is therefore an ACCURACY dial (it costs one extra SVD
# per compressed merge, it does not save memory or time). Bounding the peak
# intermediate needs the full boundary-MPS ordering -- compress the boundary BETWEEN
# merges, keeping the state itself factored -- which the greedy pairwise order here
# does not do. Treat chi as "how much of each cut to keep", not as a memory escape
# hatch for large lattices.


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
    merging, so each merge is a rank-max_bond approximation (exact as max_bond ->
    infinity); see the header on what that does and does not bound.
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


def _dleg(i: int, d: int) -> tuple:
    # leg joining source i (a mechanism, or a noise location) to detector d's
    # parity constraint.
    return ("d", i, d)


def _oleg(i: int, o: int) -> tuple:
    # leg joining source i (a mechanism, or a noise location) to observable o's
    # parity tensor.
    return ("o", i, o)


def _obs_out(o: int) -> tuple:
    # the open leg carrying observable o's predicted flip bit.
    return ("obs", o)


class TensorNetworkDecoder(BatchDecoder):
    """
    Shared base for the factor-graph tensor-network decoders. Each builds a network
    of one variable tensor per error SOURCE (a DEM mechanism, or a circuit noise
    location) plus one parity tensor per observable; per shot it pins the detector
    legs to the syndrome and contracts to the total weight of each logical class,
    argmaxing the (real part of the) weight. MaxLikelihoodDecoder is the Pauli
    special case -- real, non-negative probabilities -- and CoherentDecoder is the
    general case of signed / complex quasiprobabilities; the caching decode loop and
    per-shot contraction are identical, so they live here. Subclasses set `_dtype`
    (float64 or complex), `max_bond`, the detector incidence `_det_incidence`, and
    `_build_static`.
    """

    num_detectors: int
    num_observables: int
    max_bond: int | None = None
    _dtype: type = float

    def _init_network(self) -> None:
        # call once the subclass has set its shape, `_dtype`, `_det_incidence`, and
        # whatever `_build_static` reads. Static tensors are syndrome-independent;
        # per shot only the detector tensors change, so memoize the decoded result
        # per distinct syndrome (the all-zero syndrome dominates at low p).
        self._static = self._build_static()
        self._open = [_obs_out(o) for o in range(self.num_observables)]
        self._cache: dict = {}

    def _build_static(self) -> list[Tensor]:
        """
        Syndrome-independent tensors: the source variables plus one open-legged
        observable parity tensor per observable.
        """
        raise NotImplementedError

    def _detector_tensors(self, syndrome: np.ndarray) -> list[Tensor]:
        tensors: list[Tensor] = []

        for d in range(self.num_detectors):
            legs = [_dleg(i, d) for i in self._det_incidence[d]]
            target = int(syndrome[d])
            tensors.append(
                Tensor(parity(len(legs), target, dtype=self._dtype), tuple(legs))
            )

        return tensors

    def _decode_one(self, syndrome: np.ndarray) -> np.ndarray:
        tensors = self._static + self._detector_tensors(syndrome)
        weights = contract(tensors, self._open, max_bond=self.max_bond).data
        # signed / complex branch weights sum to a per-class total that is real up to
        # round-off; np.real is a no-op for the float MLD dtype. argmax the real
        # weight -- the most-likely logical class.
        flat = np.real(np.asarray(weights).reshape(-1))

        if not np.any(flat > 0.0):
            # impossible syndrome under the model: default to no logical flip.
            return np.zeros(self.num_observables, dtype=np.uint8)

        best = int(np.argmax(flat))
        bits = np.unravel_index(best, (2,) * self.num_observables)

        return np.array(bits, dtype=np.uint8)

    def _decode_nonempty(self, det: np.ndarray) -> np.ndarray:
        shots = det.shape[0]
        preds = np.zeros((shots, self.num_observables), dtype=np.uint8)

        for s in range(shots):
            key = det[s].tobytes()
            hit = self._cache.get(key)

            if hit is None:
                hit = self._decode_one(det[s])
                self._cache[key] = hit

            preds[s] = hit

        return preds


class MaxLikelihoodDecoder(TensorNetworkDecoder):
    """
    Exact maximum-likelihood decoder via factor-graph tensor contraction over a
    DetectorErrorModel: the Pauli special case of TensorNetworkDecoder, where every
    source is a mechanism carrying a real probability [1-p, p]. Optimal on the DEM
    (>= MWPM/BP+OSD accuracy); cost grows with the network's treewidth, so it is the
    reference / small-to-mid-distance decoder. Passing `max_bond=chi` caps the
    contraction's bond dimension via truncated SVD, trading exactness for a coarser
    contraction; `max_bond=None` (default) is exact. Registered twice in decoder.py:
    as "mld", which pins max_bond to None and stays the exact reference, and as "tn",
    which forwards the caller's `max_bond`.
    """

    def __init__(self, dem: DetectorErrorModel, max_bond: int | None = None):
        self.num_observables = dem.num_observables
        self.num_detectors = dem.num_detectors
        self.max_bond = max_bond
        self._dtype = float

        self._priors = [p for p, _d, _o in dem.mechanisms]
        self._mech_dets = [sorted(dets) for _p, dets, _o in dem.mechanisms]
        self._mech_obs = [sorted(obs) for _p, _d, obs in dem.mechanisms]

        # incidence: which mechanisms touch each detector / observable.
        self._det_incidence = [[] for _ in range(self.num_detectors)]
        self._obs_mechs = [[] for _ in range(self.num_observables)]

        for m, dets in enumerate(self._mech_dets):
            for d in dets:
                self._det_incidence[d].append(m)

        for m, obs in enumerate(self._mech_obs):
            for o in obs:
                self._obs_mechs[o].append(m)

        self._init_network()

    def _build_static(self) -> list[Tensor]:
        # one biased COPY per mechanism + one parity tensor per observable (open leg).
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
