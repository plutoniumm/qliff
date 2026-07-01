from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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


class BatchDecoder:
    """
    Base handling the empty-input short-circuit shared by every decoder: a batch
    with no detector columns (or no observables) decodes trivially to an all-zero
    (shots, observables) block. `decode_batch` normalizes the events, returns that
    block on empty input, else delegates to `_decode_nonempty` -- so subclasses hold
    only their real decode logic. Subclasses set `num_observables`.
    """

    num_observables: int

    def decode_batch(self, detection_events: np.ndarray) -> np.ndarray:
        det = np.ascontiguousarray(detection_events, dtype=np.uint8)

        if det.shape[1] == 0 or self.num_observables == 0:
            return np.zeros((det.shape[0], self.num_observables), dtype=np.uint8)

        return self._decode_nonempty(det)

    def _decode_nonempty(self, det: np.ndarray) -> np.ndarray:
        """
        Decode a batch guaranteed to have >= 1 detector column and observable.
        """
        raise NotImplementedError


class MwpmDecoder(BatchDecoder):
    """
    Minimum-weight perfect matching (PyMatching v2) over the DEM's check matrix.
    Each mechanism becomes an edge weighted log((1-p)/p); the faults matrix maps
    a matched mechanism set to the observables it flips. Graphlike only.
    """

    def __init__(self, dem: DetectorErrorModel):
        import pymatching

        # MWPM is graphlike: each fault must flip <= 2 detectors (an edge between two
        # nodes / the boundary). A fault that flips 3+ detectors is a hyperedge --
        # e.g. a 2-qubit channel like DEPOLARIZE2 on a 2D code -- which matching
        # cannot represent. Catch it here with an actionable message instead of
        # leaking PyMatching's opaque "column has N ones" ValueError.
        if not dem.is_graphlike():
            raise ValueError(
                "MWPM needs a graphlike error model (each fault flips <= 2 "
                "detectors), but this circuit has a fault flipping "
                f"{dem.max_degree()} detectors (a hyperedge, e.g. from a "
                "2-qubit channel like DEPOLARIZE2). Use 'bposd', 'mld', or 'tn'."
            )
        h, _priors, obs_matrix = dem.check_matrix()
        self.num_observables = dem.num_observables
        self.matching = pymatching.Matching.from_check_matrix(
            h,
            weights=dem.weights(),
            faults_matrix=obs_matrix,
        )

    def _decode_nonempty(self, det: np.ndarray) -> np.ndarray:
        preds = self.matching.decode_batch(det)

        return np.asarray(preds, dtype=np.uint8)


class BpOsdDecoder(BatchDecoder):
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

    def _decode_nonempty(self, det: np.ndarray) -> np.ndarray:
        shots = det.shape[0]
        preds = np.zeros((shots, self.num_observables), dtype=np.uint8)

        for s in range(shots):
            recovered = self.decoder.decode(det[s]).astype(np.uint8)
            # GF(2): observable parity = (obs_matrix @ recovered) mod 2
            flips = (self.obs_matrix @ recovered) & 1
            preds[s] = flips.astype(np.uint8)

        return preds


@dataclass(frozen=True)
class DecoderSpec:
    """
    One decoder's registry record: its wire `name`, UI `label`, capability `note`,
    whether it honestly decodes only Pauli noise (`pauli_only`), whether it REQUIRES
    a graphlike error model (`graphlike` -- only MWPM does), its `mode` ("dem" builds
    a DetectorErrorModel, "circuit" consumes the circuit directly), and the `factory`
    that constructs it. Single source of truth: the server's Pauli-only / graphlike
    capability sets and the /decoders payload all read from here, so a decoder's
    capability flags cannot drift.
    """

    name: str
    label: str
    note: str
    pauli_only: bool
    graphlike: bool
    mode: str
    factory: Callable[..., Decoder]


def _mwpm_factory(dem: DetectorErrorModel) -> Decoder:
    return MwpmDecoder(dem)


def _bposd_factory(dem: DetectorErrorModel) -> Decoder:
    return BpOsdDecoder(dem)


def _mld_factory(dem: DetectorErrorModel) -> Decoder:
    from .tn import MaxLikelihoodDecoder

    return MaxLikelihoodDecoder(dem)


def _color_factory(dem: DetectorErrorModel) -> Decoder:
    from .colordec import ColorDecoder

    return ColorDecoder(dem)


def _coherent_factory(circuit) -> Decoder:
    from .coherent import CoherentDecoder

    return CoherentDecoder(circuit)


# Every decoder the engine offers, in the exact order /decoders lists them. "mld" and
# "tn" share the MLD factory (tn will gain bond-dim truncation); both are non-Pauli
# capable and auto-route to the coherent TN on non-Pauli noise (see `make`).
DECODER_SPECS: dict[str, DecoderSpec] = {
    "mwpm": DecoderSpec(
        name="mwpm",
        label="MWPM",
        note="minimum-weight perfect matching (graphlike)",
        pauli_only=True,
        graphlike=True,
        mode="dem",
        factory=_mwpm_factory,
    ),
    "bposd": DecoderSpec(
        name="bposd",
        label="BP+OSD",
        note="belief propagation + ordered-statistics decoding",
        pauli_only=True,
        graphlike=False,
        mode="dem",
        factory=_bposd_factory,
    ),
    "mld": DecoderSpec(
        name="mld",
        label="MLD",
        note="exact max-likelihood TN (Pauli + coherent)",
        pauli_only=False,
        graphlike=False,
        mode="dem",
        factory=_mld_factory,
    ),
    "tn": DecoderSpec(
        name="tn",
        label="TN",
        note="tensor-network max-likelihood (Pauli + coherent)",
        pauli_only=False,
        graphlike=False,
        mode="dem",
        factory=_mld_factory,
    ),
    "coherent": DecoderSpec(
        name="coherent",
        label="Coherent",
        note="non-Pauli/coherent TN",
        pauli_only=False,
        graphlike=False,
        mode="circuit",
        factory=_coherent_factory,
    ),
    "color": DecoderSpec(
        name="color",
        label="Color (min-weight)",
        note="dedicated min-weight lookup decoder; handles color-code hyperedges",
        pauli_only=True,
        graphlike=False,
        mode="dem",
        factory=_color_factory,
    ),
}


def _unknown_decoder_msg(name: str) -> str:
    names = ", ".join(f"'{n}'" for n in DECODER_SPECS)

    return f"unknown decoder {name!r}; expected one of {names}"


def make_decoder(name: str, dem: DetectorErrorModel) -> Decoder:
    """
    Dispatch a DEM decoder by name: "mwpm" (default), "bposd", "mld"/"tn" (exact
    maximum-likelihood by tensor contraction), or "color". "coherent" is circuit-aware,
    not DEM-based -- request it through make_circuit_decoder, which has access to the
    circuit's signed noise branches.
    """
    spec = DECODER_SPECS.get(name.lower())
    if spec is None:
        raise ValueError(_unknown_decoder_msg(name))

    if spec.mode == "circuit":
        raise ValueError(
            "'coherent' decodes the circuit's signed noise branches, not a DEM; "
            "build it via make_circuit_decoder(name, circuit)"
        )

    return spec.factory(dem)


def _circuit_is_pauli(circuit) -> bool:
    """
    True iff every noise location in the circuit is a Pauli channel, so a
    DetectorErrorModel can represent it. Non-Pauli locations (coherent RZ/RX,
    amplitude damping) carry signed / complex branch weights no DEM can hold.
    """
    from ..noise.channel import NOISE_FACTORIES, make_channel
    from ..simulator import CLIFFORD_OPS

    for name, _targets, arg in circuit.instructions:
        if name in CLIFFORD_OPS or name not in NOISE_FACTORIES:
            continue

        if not make_channel(name, arg).is_pauli:
            return False

    return True


def make(name: str, circuit) -> Decoder:
    """
    The single circuit-aware decoder entry point: build decoder `name` for `circuit`,
    reading its DecoderSpec.mode. "circuit"-mode decoders ("coherent") consume the
    circuit directly. "dem"-mode decoders build a DetectorErrorModel -- except the
    non-Pauli-capable ones ("mld"/"tn"), which fall back to the circuit-aware
    signed-quasiprobability TN (CoherentDecoder, which reduces to exact MLD on Pauli
    noise) when the circuit carries non-Pauli noise no DEM can hold. The graphlike DEM
    decoders ("mwpm", "bposd") and "color" stay pauli_only, so they take the DEM path,
    where DetectorErrorModel raises on non-Pauli noise.
    """
    spec = DECODER_SPECS.get(name.lower())
    if spec is None:
        raise ValueError(_unknown_decoder_msg(name))

    if spec.mode == "circuit":
        return spec.factory(circuit)

    if not spec.pauli_only and not _circuit_is_pauli(circuit):
        return _coherent_factory(circuit)

    return spec.factory(DetectorErrorModel(circuit))


def make_circuit_decoder(name: str, circuit) -> Decoder:
    """
    Circuit-aware decoder factory shared by the threshold / server code. Thin alias
    for `make`, kept for callers importing the historical name.
    """
    return make(name, circuit)
