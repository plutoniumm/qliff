from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from .dem import DetectorErrorModel

# Decoders over a DetectorErrorModel: detection events -> predicted observable
# flips. MWPM (pymatching) is the graphlike default; BP+OSD (ldpc) handles dense
# / non-graphlike codes (e.g. colour codes). Pulls pymatching / ldpc, so import
# this module DIRECTLY (never via qliff.qec.__init__) to keep `import qliff`
# numpy-only.


@runtime_checkable
class Decoder(Protocol):
    """
    Maps a batch of detection events to predicted observable flips.
    """

    def decode_batch(self, detection_events: np.ndarray) -> np.ndarray:
        """
        (shots, n_detectors) uint8 -> (shots, n_observables) uint8.
        """
        ...


class MwpmDecoder:
    """
    Minimum-weight perfect matching (PyMatching v2) over the DEM's check matrix.
    Each mechanism becomes an edge weighted log((1-p)/p); the faults matrix maps
    a matched mechanism set to the observables it flips. Graphlike only.
    """

    def __init__(self, dem: DetectorErrorModel):
        import pymatching

        h, _priors, obs_matrix = dem.check_matrix()
        self.num_observables = dem.num_observables
        self.matching = pymatching.Matching.from_check_matrix(
            h,
            weights=dem.weights(),
            faults_matrix=obs_matrix,
        )

    def decode_batch(self, detection_events: np.ndarray) -> np.ndarray:
        det = np.ascontiguousarray(detection_events, dtype=np.uint8)
        if det.shape[1] == 0:
            return np.zeros((det.shape[0], self.num_observables), dtype=np.uint8)

        preds = self.matching.decode_batch(det)

        return np.asarray(preds, dtype=np.uint8)


class BpOsdDecoder:
    """
    Belief propagation + ordered-statistics decoding (ldpc) over the DEM's check
    matrix. Recovers a mechanism vector per shot, then maps it through the
    observable matrix (mod 2) to observable flips. Handles non-graphlike codes.
    """

    def __init__(self, dem: DetectorErrorModel):
        import scipy.sparse as sp
        from ldpc import BpOsdDecoder as _BpOsdDecoder

        h, priors, obs_matrix = dem.check_matrix()
        self.num_observables = dem.num_observables
        self.num_detectors = dem.num_detectors
        self.obs_matrix = obs_matrix.astype(np.uint8)
        # clamp priors away from 0/1 so BP log-ratios stay finite.
        channel = np.clip(priors, 1e-9, 1.0 - 1e-9).tolist()
        self.decoder = _BpOsdDecoder(
            sp.csr_matrix(h.astype(np.uint8)),
            error_channel=channel,
            bp_method="product_sum",
            max_iter=0,
            osd_method="osd_cs",
            osd_order=7,
        )

    def decode_batch(self, detection_events: np.ndarray) -> np.ndarray:
        det = np.asarray(detection_events, dtype=np.uint8)
        shots = det.shape[0]
        preds = np.zeros((shots, self.num_observables), dtype=np.uint8)
        if det.shape[1] == 0:
            return preds

        for s in range(shots):
            recovered = self.decoder.decode(det[s]).astype(np.uint8)
            # GF(2): observable parity = (obs_matrix @ recovered) mod 2
            flips = (self.obs_matrix @ recovered) & 1
            preds[s] = flips.astype(np.uint8)

        return preds


def make_decoder(name: str, dem: DetectorErrorModel) -> Decoder:
    """
    Dispatch a decoder by name: "mwpm" (default) or "bposd".
    """
    key = name.lower()
    if key == "mwpm":
        return MwpmDecoder(dem)

    if key == "bposd":
        return BpOsdDecoder(dem)

    raise ValueError(f"unknown decoder {name!r}; expected 'mwpm' or 'bposd'")
