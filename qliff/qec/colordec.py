from __future__ import annotations

import itertools

import numpy as np

from .decoder import BatchDecoder
from .dem import DetectorErrorModel

# Dedicated decoder for the color / hyperedge families. MWPM needs a graphlike DEM
# (each fault flips <= 2 detectors); the 6.6.6 color code has weight-3 hyperedges, so
# matching cannot run. This is an exact minimum-weight lookup decoder over the DEM's
# fault mechanisms: it precomputes, for every syndrome reachable by up to `max_weight`
# faults, the fewest faults that produce it and the observable flip they imply, then
# decodes by table lookup. Unlike MWPM it handles hyperedges directly, and unlike the
# TN decoder it is cheap at decode time -- well suited to the small color-code patches.


class ColorDecoder(BatchDecoder):
    """
    Minimum-(number-of-faults) lookup decoder over a DetectorErrorModel. Optimal up to
    the `max_weight` truncation; syndromes needing more faults than that fall back to
    the trivial (no observable flip) prediction, which is rare at low physical rates.
    """

    def __init__(self, dem: DetectorErrorModel, max_weight: int = 3):
        self.num_observables = dem.num_observables
        self.num_detectors = dem.num_detectors
        mechs = [
            (frozenset(dets), frozenset(obs)) for _p, dets, obs in dem.mechanisms
        ]
        # Keep the precompute bounded: with many mechanisms a weight-3 sweep already
        # covers the correction radius of the small patches, so cap weight as the
        # mechanism count grows.
        weight = max_weight
        if len(mechs) > 200:
            weight = min(weight, 2)

        table: dict[tuple[int, ...], int] = {(): 0}
        best: dict[tuple[int, ...], int] = {(): 0}
        for w in range(1, weight + 1):
            for combo in itertools.combinations(range(len(mechs)), w):
                dets: set[int] = set()
                obs = 0
                for idx in combo:
                    dets ^= mechs[idx][0]
                    for o in mechs[idx][1]:
                        obs ^= 1 << o
                key = tuple(sorted(dets))
                if key not in best or w < best[key]:
                    best[key] = w
                    table[key] = obs

        self.table = table

    def _decode_nonempty(self, det: np.ndarray) -> np.ndarray:
        shots = det.shape[0]
        preds = np.zeros((shots, self.num_observables), dtype=np.uint8)

        for s in range(shots):
            key = tuple(int(i) for i in np.nonzero(det[s])[0])
            obs = self.table.get(key, 0)
            for o in range(self.num_observables):
                preds[s, o] = (obs >> o) & 1

        return preds
