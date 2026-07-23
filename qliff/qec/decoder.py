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
    a graphlike error model (`graphlike` -- only MWPM does), whether it accepts a
    bond-dimension cap (`bonded` -- only the truncating tensor-network decoders do),
    its `mode` ("dem" builds a DetectorErrorModel, "circuit" consumes the circuit
    directly), and the `factory` that constructs it. A `bonded` factory takes
    (target, max_bond); every other takes (target) alone. Single source of truth: the
    server's Pauli-only / graphlike capability sets and the /decoders payload all read
    from here, so a decoder's capability flags cannot drift.
    """

    name: str
    label: str
    note: str
    pauli_only: bool
    graphlike: bool
    bonded: bool
    mode: str
    factory: Callable[..., Decoder]


def _mwpm_factory(dem: DetectorErrorModel) -> Decoder:
    return MwpmDecoder(dem)


def _bposd_factory(dem: DetectorErrorModel) -> Decoder:
    return BpOsdDecoder(dem)


def _mld_factory(dem: DetectorErrorModel) -> Decoder:
    from .tn import MaxLikelihoodDecoder

    return MaxLikelihoodDecoder(dem)


def _tn_factory(dem: DetectorErrorModel, max_bond: int | None = None) -> Decoder:
    from .tn import MaxLikelihoodDecoder

    return MaxLikelihoodDecoder(dem, max_bond=max_bond)


def _color_factory(dem: DetectorErrorModel) -> Decoder:
    from .colordec import ColorDecoder

    return ColorDecoder(dem)


def _coherent_factory(circuit, max_bond: int | None = None) -> Decoder:
    from .coherent import CoherentDecoder

    return CoherentDecoder(circuit, max_bond=max_bond)


# Every decoder the engine offers, in the exact order /decoders lists them. "mld" and
# "tn" are the SAME contraction but no longer aliases: "mld" is the exact reference
# decoder and refuses a bond cap, while "tn" is `bonded` and takes `max_bond=chi` to
# truncate the contraction ("tn" with max_bond=None, the default, is still bit-for-bit
# "mld"). Both are non-Pauli capable and auto-route to the coherent TN on non-Pauli
# noise (see `make`), which is `bonded` too.
DECODER_SPECS: dict[str, DecoderSpec] = {
    "mwpm": DecoderSpec(
        name="mwpm",
        label="MWPM",
        note="minimum-weight perfect matching (graphlike)",
        pauli_only=True,
        graphlike=True,
        bonded=False,
        mode="dem",
        factory=_mwpm_factory,
    ),
    "bposd": DecoderSpec(
        name="bposd",
        label="BP+OSD",
        note="belief propagation + ordered-statistics decoding",
        pauli_only=True,
        graphlike=False,
        bonded=False,
        mode="dem",
        factory=_bposd_factory,
    ),
    "mld": DecoderSpec(
        name="mld",
        label="MLD",
        note="exact max-likelihood TN, no truncation (Pauli + coherent)",
        pauli_only=False,
        graphlike=False,
        bonded=False,
        mode="dem",
        factory=_mld_factory,
    ),
    "tn": DecoderSpec(
        name="tn",
        label="TN",
        note="max-likelihood TN, bond-truncatable via max_bond (Pauli + coherent)",
        pauli_only=False,
        graphlike=False,
        bonded=True,
        mode="dem",
        factory=_tn_factory,
    ),
    "coherent": DecoderSpec(
        name="coherent",
        label="Coherent",
        note="non-Pauli/coherent TN, bond-truncatable via max_bond",
        pauli_only=False,
        graphlike=False,
        bonded=True,
        mode="circuit",
        factory=_coherent_factory,
    ),
    "color": DecoderSpec(
        name="color",
        label="Color (min-weight)",
        note="dedicated min-weight lookup decoder; handles color-code hyperedges",
        pauli_only=True,
        graphlike=False,
        bonded=False,
        mode="dem",
        factory=_color_factory,
    ),
}


def _unknown_decoder_msg(name: str) -> str:
    names = ", ".join(f"'{n}'" for n in DECODER_SPECS)

    return f"unknown decoder {name!r}; expected one of {names}"


def _check_max_bond(spec: DecoderSpec, max_bond: int | None) -> None:
    """
    Validate a `max_bond` against the decoder it is aimed at, so the knob can never be
    silently dropped: None (the exact contraction) suits every decoder, a cap below 1
    keeps no singular value at all and would decode every syndrome to zero, and a real
    cap reaches only the `bonded` decoders.
    """
    if max_bond is None:
        return

    if max_bond < 1:
        raise ValueError(
            f"max_bond must be a bond dimension >= 1, got {max_bond!r}; pass None "
            "for the exact contraction"
        )

    if spec.bonded:
        return

    names = ", ".join(f"'{n}'" for n, s in DECODER_SPECS.items() if s.bonded)
    raise ValueError(
        f"decoder {spec.name!r} has no tensor contraction to truncate, so it cannot "
        f"honour max_bond={max_bond!r}; drop it or use one of {names}"
    )


def _build(spec: DecoderSpec, target, max_bond: int | None) -> Decoder:
    """
    Call a spec's factory over its build target (a DEM, or the circuit for
    "circuit"-mode decoders), threading `max_bond` into the `bonded` factories only.
    """
    if spec.bonded:
        return spec.factory(target, max_bond)

    return spec.factory(target)


def make_decoder(
    name: str, dem: DetectorErrorModel, max_bond: int | None = None
) -> Decoder:
    """
    Dispatch a DEM decoder by name: "mwpm" (default), "bposd", "mld" (exact
    maximum-likelihood by tensor contraction), "tn" (that same contraction, capped at
    `max_bond` bond dimension), or "color". `max_bond` is honoured only by the `bonded`
    decoders and raises on any other, so a truncation request is never silently
    dropped. "coherent" is circuit-aware, not DEM-based -- request it through
    make_circuit_decoder, which has access to the circuit's signed noise branches.
    """
    spec = DECODER_SPECS.get(name.lower())
    if spec is None:
        raise ValueError(_unknown_decoder_msg(name))

    if spec.mode == "circuit":
        raise ValueError(
            "'coherent' decodes the circuit's signed noise branches, not a DEM; "
            "build it via make_circuit_decoder(name, circuit)"
        )

    _check_max_bond(spec, max_bond)

    return _build(spec, dem, max_bond)


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


def make(name: str, circuit, max_bond: int | None = None) -> Decoder:
    """
    The single circuit-aware decoder entry point: build decoder `name` for `circuit`,
    reading its DecoderSpec.mode. "circuit"-mode decoders ("coherent") consume the
    circuit directly. "dem"-mode decoders build a DetectorErrorModel -- except the
    non-Pauli-capable ones ("mld"/"tn"), which fall back to the circuit-aware
    signed-quasiprobability TN (CoherentDecoder, which reduces to exact MLD on Pauli
    noise) when the circuit carries non-Pauli noise no DEM can hold. The graphlike DEM
    decoders ("mwpm", "bposd") and "color" stay pauli_only, so they take the DEM path,
    where DetectorErrorModel raises on non-Pauli noise. `max_bond` caps the tensor
    contraction's bond dimension; only the `bonded` decoders ("tn", "coherent") take
    it -- including down the non-Pauli fallback, so "tn" truncates in both noise
    regimes -- and every other decoder raises on it.
    """
    spec = DECODER_SPECS.get(name.lower())
    if spec is None:
        raise ValueError(_unknown_decoder_msg(name))

    _check_max_bond(spec, max_bond)

    if spec.mode == "circuit":
        return _build(spec, circuit, max_bond)

    if not spec.pauli_only and not _circuit_is_pauli(circuit):
        return _coherent_factory(circuit, max_bond)

    return _build(spec, DetectorErrorModel(circuit), max_bond)


def make_circuit_decoder(name: str, circuit, max_bond: int | None = None) -> Decoder:
    """
    Circuit-aware decoder factory shared by the threshold / server code. Thin alias
    for `make`, kept for callers importing the historical name.
    """
    return make(name, circuit, max_bond)
