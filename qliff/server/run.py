from __future__ import annotations

import time
from typing import Callable

from ..circuit import Circuit
from ..noise.channel import CHANNEL_META
from ..qec import registry
from ..qec.decoder import DECODER_SPECS
from ..qec.dem import DetectorErrorModel
from ..qec.threshold import isweep
from .schema import (
    CompileResponse,
    LerPoint,
    RunRequest,
    RunResponse,
)

# Bridge the wire schema to the QEC engine: RunRequest -> Circuit factory ->
# sample/decode/LER. A request carries either a `template` (canonical family +
# distance) or an explicit `spec` (resolved lattice geometry); rounds defaults to
# the code distance (or a small constant for free-form specs). Family dispatch +
# sizing come from qliff.qec.registry; decoder / channel capability sets are DERIVED
# below from the decoder registry + CHANNEL_META so they can never drift.

# Non-Pauli (coherent / amplitude-damping) channels carry signed branch weights no
# DetectorErrorModel can hold. The pauli-only DEM decoders genuinely can't decode
# them; the TN family ("tn"/"mld") and "coherent" handle them by contracting the
# circuit's signed quasiprobability branches instead (see decoder.make).
_NON_PAULI_CHANNELS = {name for name, meta in CHANNEL_META.items() if not meta.is_pauli}
# Decoders that honestly decode ONLY Pauli noise (DEM-backed): a non-Pauli channel
# paired with one of these can't even build its error model.
_PAULI_ONLY_DECODERS = {name for name, spec in DECODER_SPECS.items() if spec.pauli_only}
# Decoders that need a GRAPHLIKE error model (every fault flips <= 2 detectors).
# BP+OSD/TN/MLD all handle hyperedges; only matching (MWPM) is graphlike-only.
_GRAPHLIKE_DECODERS = {name for name, spec in DECODER_SPECS.items() if spec.graphlike}


def _noise_decoder_warning(req: RunRequest) -> str | None:
    """
    Warn when a non-Pauli channel is paired with a graphlike DEM decoder, which
    can't honestly decode it -- steer the caller to a TN-based decoder.
    """
    channel = req.noise.channel.upper()
    if channel not in _NON_PAULI_CHANNELS:
        return None

    if req.decoder not in _PAULI_ONLY_DECODERS:
        return None

    return (
        f"channel {channel!r} is non-Pauli; decoder {req.decoder!r} is DEM-based "
        "and cannot honestly decode it -- use 'tn', 'mld', or 'coherent' instead."
    )


def _graphlike_decoder_warning(req: RunRequest, circuit: Circuit) -> str | None:
    """
    Warn when a graphlike matching decoder (MWPM) meets a circuit whose error model
    has a hyperedge -- a fault flipping > 2 detectors, e.g. a 2-qubit channel like
    DEPOLARIZE2 on a 2D code. MWPM genuinely can't represent it; steer to a
    hyperedge-capable decoder. None unless that mismatch applies. Non-Pauli circuits
    are skipped (no DEM to build -- the non-Pauli guard covers those).
    """
    if req.decoder not in _GRAPHLIKE_DECODERS:
        return None

    try:
        dem = DetectorErrorModel(circuit)
    except ValueError:
        return None  # non-Pauli noise; handled by _noise_decoder_warning

    if dem.is_graphlike():
        return None

    return (
        f"decoder {req.decoder!r} is graphlike (matching) but the noise model has a "
        f"fault flipping {dem.max_degree()} detectors (a hyperedge, e.g. from "
        "DEPOLARIZE2 on a 2D code) -- use 'bposd', 'mld', or 'tn' instead."
    )


_DEFAULT_SPEC_ROUNDS = 3


def _template_circuit_fn(
    family: str,
    distance: int,
    rounds: int,
    channel: str,
    pattern: str,
    start: str,
    edge: str,
) -> Callable:
    """
    The canonical family's p -> Circuit factory, from the family registry. Surface
    families thread the stabiliser-pattern knobs (pattern/start/edge); the others
    ignore them. Raises on an unknown family.
    """
    return registry.circuit_factory(
        family, distance, rounds, channel, pattern, start, edge
    )


def _spec_circuit_fn(req: RunRequest, rounds: int) -> Callable:
    """
    Free-form LatticeSpec -> lattice.build_circuit(...) curried over p.
    """
    from ..qec import lattice

    spec = req.spec
    boundary = spec.boundary
    channel = req.noise.channel

    if spec.tiles:
        tiles = [t.model_dump() for t in spec.tiles]
        num_data, stabilizers, observables = lattice.resolve_tiles(tiles)
    else:
        num_data = spec.num_data
        stabilizers = [(s.type, s.data) for s in spec.stabilizers]
        observables = [(o.type, o.data) for o in spec.observables]

    return lambda p: lattice.build_circuit(
        num_data,
        stabilizers,
        observables,
        rounds,
        channel,
        p,
        boundary=boundary,
    )


def _rounds(req: RunRequest) -> int:
    """
    Explicit rounds, else the template distance, else a small default.
    """
    if req.rounds is not None:
        return req.rounds

    if req.template is not None:
        return req.template.distance

    return _DEFAULT_SPEC_ROUNDS


def make_circuit_fn(req: RunRequest) -> Callable[[float], Circuit]:
    """
    Build a p -> Circuit factory from a template or an explicit spec.
    """
    rounds = _rounds(req)
    if req.template is not None:
        return _template_circuit_fn(
            req.template.family,
            req.template.distance,
            rounds,
            req.noise.channel,
            req.template.pattern,
            req.template.start,
            req.template.edge,
        )

    if req.spec is not None:
        return _spec_circuit_fn(req, rounds)

    raise ValueError("request needs exactly one of template / spec")


def _p_values(req: RunRequest) -> list[float]:
    """
    Resolve the physical-rate sweep: p_sweep if given, else [p], else [0].
    """
    if req.noise.p_sweep:
        return list(req.noise.p_sweep)

    if req.noise.p is not None:
        return [req.noise.p]

    return [0.0]


def _representative_p(req: RunRequest) -> float:
    """
    A single p to build the circuit at for the static compile summary.
    """
    return _p_values(req)[0]


def _resolved_tiles(req: RunRequest) -> tuple[int, list, list]:
    """
    Resolve a free-form tile spec to (num_data, stabilizers, observables), or
    (0, [], []) if it doesn't resolve (e.g. tri/hex tiles, not yet supported).
    """
    from ..qec import lattice

    try:
        tiles = [t.model_dump() for t in req.spec.tiles]

        return lattice.resolve_tiles(tiles)
    except Exception:
        return 0, [], []


def _num_data(req: RunRequest) -> int:
    """
    Data-qubit count from the spec (explicit, or resolved from tiles) or the
    family/distance table (0 if N/A).
    """
    if req.spec is not None:
        if req.spec.num_data is not None:
            return req.spec.num_data

        if req.spec.tiles:
            return _resolved_tiles(req)[0]

    if req.template is not None:
        return registry.num_data(req.template.family, req.template.distance)

    return 0


def _num_stabilizers(req: RunRequest, circuit: Circuit, num_data: int) -> int:
    """
    Stabilizer count from the spec (explicit, or resolved from tiles), else
    inferred ancillas (qubits - data).
    """
    if req.spec is not None:
        if req.spec.stabilizers:
            return len(req.spec.stabilizers)

        if req.spec.tiles:
            return len(_resolved_tiles(req)[1])

    if num_data > 0 and circuit.num_qubits >= num_data:
        return circuit.num_qubits - num_data

    return 0


def compile_summary(req: RunRequest) -> CompileResponse:
    """
    Static circuit summary at a representative p. Never raises: on a bad spec
    it returns ok=False with the error in `warnings`.
    """
    warnings: list[str] = []
    decoder_warning = _noise_decoder_warning(req)
    if decoder_warning is not None:
        warnings.append(decoder_warning)

    try:
        circuit_fn = make_circuit_fn(req)
        circuit = circuit_fn(_representative_p(req))
    except Exception as exc:  # bad spec / missing builder -> surface as warning
        warnings.append(str(exc))

        return CompileResponse(ok=False, warnings=warnings)

    graphlike_warning = _graphlike_decoder_warning(req, circuit)
    if graphlike_warning is not None:
        warnings.append(graphlike_warning)

    num_data = _num_data(req)

    return CompileResponse(
        ok=True,
        num_qubits=circuit.num_qubits,
        num_data=num_data,
        num_stabilizers=_num_stabilizers(req, circuit, num_data),
        num_detectors=len(circuit.detectors),
        num_observables=len(circuit.observables),
        warnings=warnings,
    )


def _describe(req: RunRequest) -> str:
    """
    One-line source description for the terminal log.
    """
    if req.template is not None:
        return f"{req.template.family} d={req.template.distance}"

    if req.spec is not None:
        return f"freeform ({len(req.spec.tiles)} tiles)"

    return "?"


def run_sweep(req: RunRequest, on_point=None) -> RunResponse:
    """
    Drive the full LER sweep. Calls on_point(LerPoint) per physical rate (for
    streaming) and returns the complete RunResponse with timing + counts. Echoes
    progress to stdout so `./do serve` shows live activity in the terminal.
    """
    circuit_fn = make_circuit_fn(req)
    p_values = _p_values(req)

    warnings: list[str] = []
    decoder_warning = _noise_decoder_warning(req)
    if decoder_warning is not None:
        # a DEM decoder on non-Pauli noise can't even build its error model, so
        # fail fast with the actionable message rather than an opaque DEM crash.
        raise ValueError(decoder_warning)

    # peek at the first circuit once for qubit / detector counts.
    probe = circuit_fn(p_values[0])
    num_qubits = probe.num_qubits
    num_detectors = len(probe.detectors)

    graphlike_warning = _graphlike_decoder_warning(req, probe)
    if graphlike_warning is not None:
        # a matching decoder on a hyperedge model can't build, so fail fast with
        # the actionable message rather than PyMatching's opaque column error.
        raise ValueError(graphlike_warning)

    print(
        f">> run: {_describe(req)} | {len(p_values)} p-points x {req.shots} shots"
        f" | decoder={req.decoder} | {num_qubits} qubits, {num_detectors} detectors",
        flush=True,
    )
    for warning in warnings:
        print(f"   !! {warning}", flush=True)

    points: list[LerPoint] = []
    start = time.perf_counter()
    stream = isweep(circuit_fn, p_values, req.decoder, req.shots, req.seed)
    for p, ler, stderr in stream:
        point = LerPoint(p=p, ler=ler, stderr=stderr, shots=req.shots)
        points.append(point)
        print(f"   p={p:<9.4g} LER={ler:.3e} +/-{stderr:.1e}", flush=True)
        if on_point is not None:
            on_point(point)
    elapsed = time.perf_counter() - start
    print(f">> done in {elapsed:.2f}s ({len(points)} points)", flush=True)

    return RunResponse(
        decoder=req.decoder,
        points=points,
        num_qubits=num_qubits,
        num_detectors=num_detectors,
        elapsed=elapsed,
        warnings=warnings,
    )


# kept importable for callers that want a DEM without re-deriving the circuit.
def circuit_dem(circuit: Circuit) -> DetectorErrorModel:
    """
    Convenience: the DetectorErrorModel for an already-built circuit.
    """
    return DetectorErrorModel(circuit)
