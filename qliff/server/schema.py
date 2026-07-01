from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Wire schema for the Studio server -- the single source of truth shared with the
# frontend. Mirror in studio/src/lib/schema.ts; keep the two in lockstep. Pydantic
# v2 so FastAPI validates requests and emits OpenAPI for free. Lives under
# qliff.server (never imported by `import qliff`), so pydantic stays in the
# [studio] extra and the core stays numpy-only. A run is specified one of two
# ways: a `template` (canonical family + distance, engine-generated) or an
# explicit `spec` (the builder's resolved lattice geometry).

TileKind = Literal["square", "tri", "hex"]
Pauli = Literal["X", "Z"]
CodeFamily = Literal[
    "repetition",
    "rotated_surface",
    "unrotated_surface",
    "toric",
    "hex_color",
    "triangular",
    "kagome",
]
DecoderName = Literal["mwpm", "bposd", "mld", "tn", "coherent", "color"]
Boundary = Literal["open", "periodic"]
ChannelArg = Literal["p", "theta", "vec3"]
# Surface-code stabiliser-pattern knobs (rotated + unrotated families), following the
# EVEN-X / EVEN-Z analysis: `pattern` (plain CSS vs the Hadamard-conjugated XZZX
# code), `start` (the X/Z colouring; "X" is the global-Hadamard dual, equivalent
# under symmetric noise but not under amplitude damping), and `edge` (which
# alternating boundary-edge set / logical orientation; rotated family only).
SurfacePattern = Literal["css", "xzzx"]
SurfaceStart = Literal["Z", "X"]
SurfaceEdge = Literal["even", "odd"]


class Tile(BaseModel):
    """
    One placed polygon on the canvas. rotation is degrees; for triangles 0 = up,
    180 = down. (row, col) are integer grid cells for snapping/joining.
    """

    id: str
    kind: TileKind
    row: int
    col: int
    rotation: int = 0


class Stabilizer(BaseModel):
    """
    A check: its Pauli type and the data-qubit indices it touches.
    """

    type: Pauli
    data: list[int]


class Observable(BaseModel):
    """
    A logical operator as the data-qubit indices it runs over.
    """

    type: Pauli
    data: list[int]


class LatticeSpec(BaseModel):
    """
    A code laid out in space. `tiles` is the builder's raw geometry (optional);
    the compiler resolves it -- or an explicit (num_data, stabilizers,
    observables) is supplied directly. `boundary` periodic => toric wraparound.
    """

    tiles: list[Tile] = Field(default_factory=list)
    num_data: int | None = None
    stabilizers: list[Stabilizer] = Field(default_factory=list)
    observables: list[Observable] = Field(default_factory=list)
    boundary: Boundary = "open"


class Template(BaseModel):
    """
    A canonical code family the engine can generate without explicit tiles. The
    surface families (rotated/unrotated) honour the stabiliser-pattern knobs
    (pattern/start/edge; `edge` is rotated-only); repetition/toric ignore them.
    """

    family: CodeFamily
    distance: int = Field(ge=2)
    pattern: SurfacePattern = "css"
    start: SurfaceStart = "Z"
    edge: SurfaceEdge = "even"


class NoiseModel(BaseModel):
    """
    A noise instruction name (matches the Circuit op, e.g. DEPOLARIZE1, X_ERROR)
    at strength p, or swept over p_sweep. Exactly one of p / p_sweep.
    """

    channel: str = "DEPOLARIZE1"
    p: float | None = None
    p_sweep: list[float] | None = None


class RunRequest(BaseModel):
    """
    A logical-error-rate run. Exactly one of template / spec is set.
    """

    template: Template | None = None
    spec: LatticeSpec | None = None
    rounds: int | None = None
    noise: NoiseModel
    shots: int = 10000
    decoder: DecoderName = "mwpm"
    seed: int | None = None


class CompileResponse(BaseModel):
    """
    Static summary of the compiled circuit; `ok` false => see warnings.
    """

    ok: bool
    num_qubits: int = 0
    num_data: int = 0
    num_stabilizers: int = 0
    num_detectors: int = 0
    num_observables: int = 0
    warnings: list[str] = Field(default_factory=list)


class LerPoint(BaseModel):
    """
    One swept point: logical error rate (+/- stderr) at physical rate p.
    """

    p: float
    ler: float
    stderr: float
    shots: int


class RunResponse(BaseModel):
    """
    The full LER curve for a finished run; `warnings` carries any decoder/channel
    mismatch notes (e.g. a non-Pauli channel decoded by a DEM decoder).
    """

    decoder: str
    points: list[LerPoint] = Field(default_factory=list)
    num_qubits: int = 0
    num_detectors: int = 0
    elapsed: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    """
    One WebSocket frame during a streaming run.
    """

    type: Literal["point", "done", "error"]
    point: LerPoint | None = None
    message: str | None = None


class TemplateInfo(BaseModel):
    """
    An entry in GET /api/templates: a family the UI can offer. patterns/starts/edges
    list the stabiliser-pattern options the family supports along each axis (one
    entry on an axis => no selector to offer for it).
    """

    family: CodeFamily
    label: str
    min_distance: int
    decoders: list[DecoderName]
    patterns: list[SurfacePattern] = Field(default_factory=lambda: ["css"])
    starts: list[SurfaceStart] = Field(default_factory=lambda: ["Z"])
    edges: list[SurfaceEdge] = Field(default_factory=lambda: ["even"])


class DecoderInfo(BaseModel):
    """
    An entry in GET /api/decoders: a decoder the UI can offer. `pauli_only`
    decoders honestly decode only Pauli channels; coherent/non-Pauli noise needs
    `pauli_only` false.
    """

    name: DecoderName
    label: str
    pauli_only: bool
    note: str


class ChannelInfo(BaseModel):
    """
    An entry in GET /api/channels: a noise channel the UI can offer. `arg` names
    the strength shape ("p" scalar, "theta" rotation angle, "vec3" Pauli rates);
    `is_pauli` false channels (RZ/RX/AMPLITUDE_DAMP) need the coherent decoder.
    """

    name: str
    label: str
    is_pauli: bool
    arg: ChannelArg
    note: str
