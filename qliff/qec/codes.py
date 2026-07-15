from __future__ import annotations

import numpy as np

from ..circuit import Circuit
from ..noise.channel import apply_data_noise
from .lattice import _emit_z_memory, _rotated_plaquettes, build_circuit

# Surface-code stabiliser-pattern knobs (rotated + unrotated families), following the
# mat-counting analysis of Dutta, Seksaria and Rudra. Three orthogonal axes:
#  - pattern: "css" (plain CSS) or "xzzx" (Hadamard on one data sublattice).
#  - start: the X/Z colouring -- which face sublattice carries the Z checks. "X"
#    RECOLOURS the checkerboard (swaps every face's kind); the experiment stays a
#    Z-memory (data |0>, Z checks primary, Z-line logical). Distinct from "Z" only
#    when no grid symmetry maps one colouring onto the other (both grid dims even
#    for the rotated family); the colourings then split under asymmetric noise (AD).
#  - edge: which alternating set of boundary edges is promoted to stabilisers; also
#    flips the logical orientation (column vs row). Rotated family only.
SURFACE_PATTERNS = ("css", "xzzx")
SURFACE_STARTS = ("Z", "X")
SURFACE_EDGES = ("even", "odd")


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
    universal_h: bool = False,
    prep: bool = False,
) -> Circuit:
    """
    Generalised syndrome-extraction memory for an arbitrary (possibly non-CSS)
    stabiliser code. `stabilizers` is a list of (primary, corners) where corners is
    [(data_qubit, "X"|"Z")]; `primary` checks declare round-to-round detectors and
    are reconstructed at readout. `q_basis` gives each data qubit's frame ("X" =>
    init |+> and read in the X basis, "Z" => |0> / Z basis); every primary check and
    observable must touch a qubit with the matching Pauli (the caller guarantees
    this). Attaches the given-order ancillas (n_data + i) and the X-frame data qubits
    and routes through the shared _emit_z_memory. `universal_h` (the XZZX frames)
    reads EVERY check with a |+> ancilla and per-corner CX / CZ so mixed faces
    extract correctly; CSS callers leave it off, keeping the bare CX ladder for
    pure-Z checks. `prep` prepends a noiseless projection round (see _emit_z_memory).
    Per-round data noise is the requested `channel` at strength p.
    """
    x_frame = [q for q in range(n_data) if q_basis.get(q, "Z") == "X"]
    stabs = [
        (primary, n_data + i, corners)
        for i, (primary, corners) in enumerate(stabilizers)
    ]

    return _emit_z_memory(
        n_data,
        stabs,
        observables,
        rounds,
        channel,
        p,
        x_frame=x_frame,
        universal_h=universal_h,
        prep=prep,
    )


def _flip_on(pauli: str, condition: bool) -> str:
    """
    Swap a single-qubit Pauli X<->Z when `condition` (a Hadamard sits on the qubit).
    """
    if not condition:
        return pauli

    return "X" if pauli == "Z" else "Z"


def _sym_vec(op: list[tuple[int, str]], n: int) -> int:
    """
    Pack a Pauli operator [(qubit, "X"|"Z")] into a 2n-bit symplectic int
    (X part low, Z part high).
    """
    v = 0
    for q, p in op:
        v ^= 1 << (q if p == "X" else n + q)

    return v


def _sym_commute(a: int, b: int, n: int) -> bool:
    """
    Whether two symplectic-packed Paulis commute (overlap parity of X-vs-Z parts).
    """
    mask = (1 << n) - 1
    cross = ((a & mask) & (b >> n)) | ((a >> n) & (b & mask))

    return bin(cross).count("1") % 2 == 0


def _in_span(gens: list[int], target: int) -> bool:
    """
    GF(2) membership of `target` in the span of `gens` (symplectic-packed ints).
    """
    piv: dict[int, int] = {}
    for g in gens:
        while g:
            lead = g.bit_length() - 1
            if lead in piv:
                g ^= piv[lead]
            else:
                piv[lead] = g
                break
    while target:
        lead = target.bit_length() - 1
        if lead not in piv:
            return False

        target ^= piv[lead]

    return True


def _pick_logical(
    n_data: int,
    stabilizers: list[tuple[bool, list[tuple[int, str]]]],
    in_h: dict[int, bool],
    lines: list[list[int]],
) -> list[tuple[int, str]]:
    """
    First border line (frame-adjusted Z on each qubit) that commutes with every
    stabiliser and is not a stabiliser product -- the tracked Z-logical. The
    candidate `lines` are qubit-index borders in preference order.
    """
    gens = [_sym_vec(corners, n_data) for _pr, corners in stabilizers]
    for line in lines:
        cand = [(q, _flip_on("Z", in_h[q])) for q in line]
        v = _sym_vec(cand, n_data)
        if all(_sym_commute(v, g, n_data) for g in gens) and not _in_span(gens, v):
            return cand

    raise ValueError("no border line is a valid logical for this layout")


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
    rows: int, cols: int, pattern: str, start: str, edge: str
) -> tuple[int, list, list, dict]:
    """
    Layout (n_data, stabilizers, observables, q_basis) for a non-default rotated
    surface-code variant on a rows x cols data grid (need not be square). The
    plaquette checkerboard and the boundary set come from _rotated_plaquettes for
    the chosen `edge`; for css, `start="X"` RECOLOURS the checkerboard (swaps every
    face's kind) while the experiment stays a Z-memory -- Z checks are primary and
    the tracked logical is the Z border line the recoloured boundary admits (found
    by _pick_logical). `pattern="xzzx"` puts one data sublattice in the Hadamard
    frame, conjugating per-corner Paulis, the logical and the readout basis; every
    face then carries the same XZZX pattern, so there is no checkerboard to
    recolour -- `start="X"` instead mirrors the frame onto the (r+c)-odd sublattice
    (a global X<->Z relabel). On grids with an even dimension that is a symmetry
    (EZ=EX, OZ=OX): xzzx variants differ by edge/orientation only. Emitted via
    _emit_memory.
    """
    n_data = rows * cols
    plaq = _rotated_plaquettes(rows, cols, edge)
    if start == "X" and pattern == "css":
        plaq = [("X" if kind == "Z" else "Z", touch) for kind, touch in plaq]

    h_par = 1 if start == "X" and pattern == "xzzx" else 0
    in_h = {
        r * cols + col: pattern == "xzzx" and (r + col) % 2 == h_par
        for r in range(rows)
        for col in range(cols)
    }
    stabilizers = [
        (kind == "Z", [(q, _flip_on(kind, in_h[q])) for q in touch])
        for kind, touch in plaq
    ]

    lines = [
        [r * cols for r in range(rows)],
        [col for col in range(cols)],
        [r * cols + cols - 1 for r in range(rows)],
        [(rows - 1) * cols + col for col in range(cols)],
    ]
    logical = _pick_logical(n_data, stabilizers, in_h, lines)
    q_basis = {q: ("X" if in_h[q] else "Z") for q in range(n_data)}

    return n_data, stabilizers, [logical], q_basis


def rotated_surface_code(
    rows: int,
    cols: int,
    rounds: int,
    p: float,
    channel: str = "DEPOLARIZE1",
    pattern: str = "css",
    start: str = "Z",
    edge: str = "even",
    prep: bool = False,
) -> Circuit:
    """
    Rotated planar surface-code memory: rows x cols data grid (need not be square),
    weight-4/2 plaquettes, `channel` noise (strength p / theta) per round. (pattern,
    start, edge) select the stabiliser pattern (see SURFACE_PATTERNS/STARTS/EDGES);
    the css/Z/even default is the Z-memory below -- only Z stabilizers declare
    round-to-round detectors (graphlike), final data M seeds boundary Z detectors and
    the logical-Z observable along a column. Other combinations route through
    _rotated_layout + _emit_memory (universal-H extraction only for xzzx frames).
    `prep` prepends a noiseless projection round so the first noise layer hits a
    code state rather than |0>^n (an AD fixed point) -- see _emit_z_memory.
    """
    _check_surface_knobs(pattern, start, edge)
    if (pattern, start, edge) != ("css", "Z", "even"):
        n_data, stabilizers, observables, q_basis = _rotated_layout(
            rows, cols, pattern, start, edge
        )

        return _emit_memory(
            n_data,
            stabilizers,
            observables,
            q_basis,
            rounds,
            channel,
            p,
            universal_h=pattern == "xzzx",
            prep=prep,
        )

    n_data = rows * cols
    plaq = _rotated_plaquettes(rows, cols)
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
    column = [r * cols for r in range(rows)]
    observables = [[(q, "Z") for q in column]]

    return _emit_z_memory(
        n_data, stabilizers, observables, rounds, channel, p, prep=prep
    )


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
    (there is no alternate boundary set to choose, so `edge` does not apply here).
    For css, `start="X"` RECOLOURS the lattice (stars become Z checks, plaquettes
    X) while the experiment stays a Z-memory with the Z border-line logical the
    recoloured boundary admits (_pick_logical); `pattern="xzzx"` puts one data-row
    sublattice in the Hadamard frame, and (as in _rotated_layout) `start="X"` then
    mirrors the frame onto the odd rows instead of recolouring. Emitted via
    _emit_memory.
    """
    side = 2 * distance - 1
    data, x_checks, z_checks = _unrotated_grid(distance)
    n_data = len(data)
    if start == "X" and pattern == "css":
        x_checks, z_checks = z_checks, x_checks
    h_row = 1 if start == "X" and pattern == "xzzx" else 0
    in_h = {idx: pattern == "xzzx" and r % 2 == h_row for (r, _c), idx in data.items()}

    stabilizers = []
    for _anc, touch in z_checks:
        stabilizers.append((True, [(q, _flip_on("Z", in_h[q])) for q in touch]))
    for _anc, touch in x_checks:
        stabilizers.append((False, [(q, _flip_on("X", in_h[q])) for q in touch]))

    lines = [
        [data[(0, col)] for col in range(side) if (0, col) in data],
        [data[(r, 0)] for r in range(side) if (r, 0) in data],
        [data[(side - 1, col)] for col in range(side) if (side - 1, col) in data],
        [data[(r, side - 1)] for r in range(side) if (r, side - 1) in data],
    ]
    logical = _pick_logical(n_data, stabilizers, in_h, lines)
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
            n_data,
            stabilizers,
            observables,
            q_basis,
            rounds,
            channel,
            p,
            universal_h=pattern == "xzzx",
        )

    side = 2 * distance - 1
    data, x_checks, z_checks = _unrotated_grid(distance)
    n_data = len(data)
    stabilizers = [
        (True, anc, [(d, "Z") for d in touch]) for anc, touch in z_checks
    ] + [(False, anc, [(d, "X") for d in touch]) for anc, touch in x_checks]
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
    stabilizers = [("Z", touch) for touch in z_checks] + [
        ("X", touch) for touch in x_checks
    ]
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
