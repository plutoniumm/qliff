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
]
DecoderName = Literal["mwpm", "bposd"]
Boundary = Literal["open", "periodic"]


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
    A canonical code family the engine can generate without explicit tiles.
    """

    family: CodeFamily
    distance: int = Field(ge=2)


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
    The full LER curve for a finished run.
    """

    decoder: str
    points: list[LerPoint] = Field(default_factory=list)
    num_qubits: int = 0
    num_detectors: int = 0
    elapsed: float = 0.0


class RunEvent(BaseModel):
    """
    One WebSocket frame during a streaming run.
    """

    type: Literal["point", "done", "error"]
    point: LerPoint | None = None
    message: str | None = None


class TemplateInfo(BaseModel):
    """
    An entry in GET /api/templates: a family the UI can offer.
    """

    family: CodeFamily
    label: str
    min_distance: int
    decoders: list[DecoderName]
