from __future__ import annotations

import numpy as np

from ..circuit import Circuit
from ..noise.channel import apply_data_noise
from .lattice import _emit_z_memory, _rotated_plaquettes, build_circuit

# Surface-code stabiliser-pattern knobs (rotated + unrotated families), following the
# EVEN-X / EVEN-Z analysis of Dutta, Seksaria and Rudra. Three orthogonal axes:
#  - pattern: "css" (plain CSS) or "xzzx" (the Hadamard-conjugated XZZX code).
#  - start: the X/Z colouring; "Z" => type-A boxes are Z, "X" => its global-Hadamard
#    dual (the paper's EVEN-X, equivalent under symmetric noise but not under AD).
#  - edge: which alternating set of boundary edges is promoted to stabilisers; also
#    flips the logical orientation (column vs row). Rotated family only.
# Every (pattern, start, edge) is a Clifford conjugation of the css/Z/even base, so
# all inherit its distance and determinism and differ only under asymmetric noise.
SURFACE_PATTERNS = ("css", "xzzx")
SURFACE_STARTS = ("Z", "X")
SURFACE_EDGES = ("even", "odd")


def _hframe(start: str, pattern: str, sublattice: bool) -> bool:
    """
    Whether a data qubit sits in the Hadamard (X) frame: `start="X"` flips every
    qubit (global-Hadamard dual), and the XZZX pattern additionally flips the
    `sublattice` qubits. The two compose by XOR.
    """
    return (start == "X") != (pattern == "xzzx" and sublattice)


def _check_surface_knobs(pattern: str, start: str, edge: str) -> None:
    """
    Validate the three stabiliser-pattern knobs against the supported sets.
    """
    if pattern not in SURFACE_PATTERNS:
        raise ValueError(f"unknown pattern {pattern!r}; expected {SURFACE_PATTERNS}")
    if start not in SURFACE_STARTS:
        raise ValueError(f"unknown start {start!r}; expected {SURFACE_STARTS}")
    if edge not in SURFACE_EDGES:
        raise ValueError(f"unknown edge {edge!r}; expected {SURFACE_EDGES}")


def _emit_memory(
    n_data: int,
    stabilizers: list[tuple[bool, list[tuple[int, str]]]],
    observables: list[list[tuple[int, str]]],
    q_basis: dict[int, str],
    rounds: int,
    channel: str,
    p: float,
) -> Circuit:
    """
    Generalised syndrome-extraction memory for an arbitrary (possibly non-CSS)
    stabiliser code. `stabilizers` is a list of (primary, corners) where corners is
    [(data_qubit, "X"|"Z")]; `primary` checks declare round-to-round detectors and
    are reconstructed at readout. `q_basis` gives each data qubit's frame ("X" =>
    init |+> and read in the X basis, "Z" => |0> / Z basis); every primary check and
    observable must touch a qubit with the matching Pauli (the caller guarantees
    this). Attaches the given-order ancillas (n_data + i) and the X-frame data qubits
    and routes through the shared _emit_z_memory with universal_h -- every check is
    read with a |+> ancilla and a per-corner CX / CZ, so mixed XZZX faces extract
    correctly. Per-round data noise is the requested `channel` at strength p.
    """
    x_frame = [q for q in range(n_data) if q_basis.get(q, "Z") == "X"]
    stabs = [
        (primary, n_data + i, corners)
        for i, (primary, corners) in enumerate(stabilizers)
    ]

    return _emit_z_memory(
        n_data, stabs, observables, rounds, channel, p, x_frame=x_frame, universal_h=True
    )


def _flip_on(pauli: str, condition: bool) -> str:
    """
    Swap a single-qubit Pauli X<->Z when `condition` (a Hadamard sits on the qubit).
    """
    if not condition:
        return pauli

    return "X" if pauli == "Z" else "Z"


def repetition_code(
    distance: int,
    rounds: int,
    p: float,
    channel: str = "DEPOLARIZE1",
) -> Circuit:
    """
    Bit-flip repetition-code memory: distance data + distance-1 ancillas,
    per-round `channel` noise (strength p / theta) per data qubit. Ancillas read
    adjacent Z parities; detectors compare each ancilla round-to-round; final
    data M seeds boundary detectors and the logical-Z observable.
    """
    c = Circuit()
    data = list(range(distance))
    anc = list(range(distance, 2 * distance - 1))
    checks = distance - 1

    for r in range(rounds):
        apply_data_noise(c.append, channel, data, p)

        for i in range(checks):
            c.append("CX", [data[i], anc[i]])
            c.append("CX", [data[i + 1], anc[i]])

        for i in range(checks):
            c.append("MR", [anc[i]])
            if r == 0:
                c.detector(-1)
            else:
                c.detector(-1, -1 - checks)

    for q in data:
        c.append("M", [q])
    for i in range(checks):
        c.detector(-distance + i, -distance + i + 1, -distance - checks + i)

    c.observable(0, *[-distance + i for i in range(distance)])

    return c


def _rotated_layout(
    distance: int, pattern: str, start: str, edge: str
) -> tuple[int, list, list, dict]:
    """
    Layout (n_data, stabilizers, observables, q_basis) for a non-default rotated
    surface-code variant. The plaquette checkerboard and the boundary set come from
    _rotated_plaquettes for the chosen `edge` (the alternate boundary keeps the column
    logical for "even", the row logical for "odd"); `pattern`/`start` then put each
    data qubit in its Hadamard frame (_hframe), recolouring the per-corner Paulis. The
    former Z-checks stay primary, so every combination is a Clifford conjugation of
    the css/Z base and inherits its distance / determinism. Emitted via _emit_memory.
    """
    n_data = distance * distance
    in_h = {
        r * distance + col: _hframe(start, pattern, (r + col) % 2 == 0)
        for r in range(distance)
        for col in range(distance)
    }

    plaq = _rotated_plaquettes(distance, distance, edge)
    stabilizers = [
        (kind == "Z", [(q, _flip_on(kind, in_h[q])) for q in touch])
        for kind, touch in plaq
    ]

    if edge == "even":
        line = [r * distance for r in range(distance)]
    else:
        line = [col for col in range(distance)]
    logical = [(q, _flip_on("Z", in_h[q])) for q in line]
    q_basis = {q: ("X" if in_h[q] else "Z") for q in range(n_data)}

    return n_data, stabilizers, [logical], q_basis


def rotated_surface_code(
    distance: int,
    rounds: int,
    p: float,
    channel: str = "DEPOLARIZE1",
    pattern: str = "css",
    start: str = "Z",
    edge: str = "even",
) -> Circuit:
    """
    Rotated planar surface-code memory: d x d data grid, weight-4/2 plaquettes,
    `channel` noise (strength p / theta) per round. (pattern, start, edge) select the
    stabiliser pattern (see SURFACE_PATTERNS/STARTS/EDGES); the css/Z/even default is
    the Z-memory below -- only Z stabilizers declare round-to-round detectors
    (graphlike), final data M seeds boundary Z detectors and the logical-Z observable
    along a column. Other combinations route through _rotated_layout + _emit_memory.
    """
    _check_surface_knobs(pattern, start, edge)
    if (pattern, start, edge) != ("css", "Z", "even"):
        n_data, stabilizers, observables, q_basis = _rotated_layout(
            distance, pattern, start, edge
        )

        return _emit_memory(
            n_data, stabilizers, observables, q_basis, rounds, channel, p
        )

    n_data = distance * distance
    plaq = _rotated_plaquettes(distance, distance)
    labelled = [(kind, n_data + i, touch) for i, (kind, touch) in enumerate(plaq)]
    stabilizers = [
        (True, anc, [(q, "Z") for q in touch])
        for kind, anc, touch in labelled
        if kind == "Z"
    ] + [
        (False, anc, [(q, "X") for q in touch])
        for kind, anc, touch in labelled
        if kind == "X"
    ]
    column = [r * distance for r in range(distance)]
    observables = [[(q, "Z") for q in column]]

    return _emit_z_memory(n_data, stabilizers, observables, rounds, channel, p)


def _unrotated_grid(distance: int) -> tuple[dict, list, list]:
    """
    Standard (non-rotated) planar surface-code layout on a (2d-1)x(2d-1) grid.
    Data sit on (r+c) even sites (d^2+(d-1)^2 of them); X-checks on (r even,
    c odd) sites, Z-checks on the rest of the odd sites. Returns
    (data, x_checks, z_checks) with checks as (anc_index, touched_data).
    """
    side = 2 * distance - 1
    data = {}
    for r in range(side):
        for col in range(side):
            if (r + col) % 2 == 0:
                data[(r, col)] = len(data)

    x_checks = []
    z_checks = []
    index = len(data)
    for r in range(side):
        for col in range(side):
            if (r + col) % 2 == 0:
                continue
            corners = [(r - 1, col), (r + 1, col), (r, col - 1), (r, col + 1)]
            touch = sorted(data[p] for p in corners if p in data)
            if r % 2 == 0 and col % 2 == 1:
                x_checks.append((index, touch))
            else:
                z_checks.append((index, touch))
            index += 1

    return data, x_checks, z_checks


def _unrotated_layout(
    distance: int, pattern: str, start: str
) -> tuple[int, list, list, dict]:
    """
    Layout (n_data, stabilizers, observables, q_basis) for a non-default unrotated
    surface-code variant. The standard layout promotes every star/plaquette check
    (there is no alternate boundary set to choose, so `edge` does not apply here);
    `pattern`/`start` put each data qubit in its Hadamard frame (start="X" flips all,
    xzzx additionally flips the even-row sublattice), recolouring the per-corner
    Paulis. The former Z-checks stay primary, so each is a Clifford conjugation of
    the css/Z base. Emitted via _emit_memory.
    """
    side = 2 * distance - 1
    data, x_checks, z_checks = _unrotated_grid(distance)
    n_data = len(data)
    in_h = {idx: _hframe(start, pattern, r % 2 == 0) for (r, _c), idx in data.items()}

    stabilizers = []
    for _anc, touch in z_checks:
        stabilizers.append((True, [(q, _flip_on("Z", in_h[q])) for q in touch]))
    for _anc, touch in x_checks:
        stabilizers.append((False, [(q, _flip_on("X", in_h[q])) for q in touch]))

    row = [data[(0, col)] for col in range(side) if (0, col) in data]
    logical = [(q, _flip_on("Z", in_h[q])) for q in row]
    q_basis = {q: ("X" if in_h[q] else "Z") for q in range(n_data)}

    return n_data, stabilizers, [logical], q_basis


def unrotated_surface_code(
    distance: int,
    rounds: int,
    p: float,
    channel: str = "DEPOLARIZE1",
    pattern: str = "css",
    start: str = "Z",
    edge: str = "even",
) -> Circuit:
    """
    Unrotated (standard) planar surface-code memory: data on the (r+c)-even sites
    of a (2d-1)^2 grid, star X-checks and plaquette Z-checks, `channel` noise
    (strength p / theta) per round. (pattern, start) select the stabiliser pattern;
    `edge` is accepted for a uniform surface API but has no effect here (the standard
    layout has no alternate boundary set). The css/Z default is the Z-memory below;
    other combinations route through _unrotated_layout + _emit_memory.
    """
    _check_surface_knobs(pattern, start, edge)
    if (pattern, start) != ("css", "Z"):
        n_data, stabilizers, observables, q_basis = _unrotated_layout(
            distance, pattern, start
        )

        return _emit_memory(
            n_data, stabilizers, observables, q_basis, rounds, channel, p
        )

    side = 2 * distance - 1
    data, x_checks, z_checks = _unrotated_grid(distance)
    n_data = len(data)
    stabilizers = [
        (True, anc, [(d, "Z") for d in touch]) for anc, touch in z_checks
    ] + [
        (False, anc, [(d, "X") for d in touch]) for anc, touch in x_checks
    ]
    logical_z = [data[(0, col)] for col in range(side) if (0, col) in data]
    observables = [[(q, "Z") for q in logical_z]]

    return _emit_z_memory(n_data, stabilizers, observables, rounds, channel, p)


def _toric_grid(distance: int) -> tuple[int, list, list, list]:
    """
    Toric-code layout on a d x d torus: data on edges (d^2 horizontal +
    d^2 vertical), with periodic wraparound both directions. Returns
    (n_data, x_checks, z_checks, logicals); checks are (touched_data) tuples and
    logicals is [logZ1, logZ2] -- horizontal-edge and vertical-edge windings.
    """
    side = distance

    def horiz(r: int, col: int) -> int:
        return (r % side) * side + (col % side)

    def vert(r: int, col: int) -> int:
        return side * side + (r % side) * side + (col % side)

    n_data = 2 * side * side
    z_checks = []
    for r in range(side):
        for col in range(side):
            face = [horiz(r, col), horiz(r + 1, col), vert(r, col), vert(r, col + 1)]
            z_checks.append(sorted(face))

    x_checks = []
    for r in range(side):
        for col in range(side):
            star = [horiz(r, col), horiz(r, col - 1), vert(r, col), vert(r - 1, col)]
            x_checks.append(sorted(star))

    logical_z1 = [horiz(0, col) for col in range(side)]
    logical_z2 = [vert(r, 0) for r in range(side)]

    return n_data, x_checks, z_checks, [logical_z1, logical_z2]


def toric_code(
    distance: int,
    rounds: int,
    p: float,
    channel: str = "DEPOLARIZE1",
) -> Circuit:
    """
    Toric-code Z-memory with periodic boundaries both directions (wraparound):
    data on the 2d^2 torus edges, d^2 star X-checks and d^2 plaquette Z-checks,
    two logical qubits, `channel` noise (strength p / theta) per round. Only Z
    stabilizers declare round-to-round detectors; final data M seeds boundary Z
    detectors and the two logical-Z observables (one per non-contractible loop).
    """
    n_data, x_checks, z_checks, logicals = _toric_grid(distance)
    stabilizers = (
        [("Z", touch) for touch in z_checks]
        + [("X", touch) for touch in x_checks]
    )
    observables = [("Z", loop) for loop in logicals]

    return build_circuit(n_data, stabilizers, observables, rounds, channel, p)


def logical_fidelity(predictions: np.ndarray, observed: np.ndarray) -> float:
    """
    Logical fidelity = 1 - mean(prediction != observed) (complement of the
    logical error rate). Decoded vs true observable-flip arrays; a multi-column
    row errs if any column disagrees.
    """
    predictions = np.asarray(predictions)
    observed = np.asarray(observed)

    if predictions.ndim > 1:
        mismatch = np.any(predictions != observed, axis=1)
    else:
        mismatch = predictions != observed

    return 1.0 - float(np.mean(mismatch))
