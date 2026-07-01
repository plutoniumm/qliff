from __future__ import annotations

from collections.abc import Iterable

from ..circuit import Circuit
from ..noise.channel import NOISE_FACTORIES, apply_data_noise


def _emit_z_memory(
    num_data: int,
    stabilizers: list[tuple[bool, int, list[tuple[int, str]]]],
    observables: list[list[tuple[int, str]]],
    rounds: int,
    noise_channel: str,
    p: float,
    x_frame: Iterable[int] = (),
    universal_h: bool = False,
) -> Circuit:
    """
    Shared Z-memory syndrome-extraction emitter for every code family (surface,
    toric, colour, and the XZZX / EVEN-X variants). Each stabilizer is
    (primary, ancilla, corners) with corners [(data, "X"|"Z")]; checks are emitted
    in the GIVEN order, so callers put the primary Z-checks first to keep the round
    detectors graphlike. Only `primary` checks declare round-to-round detectors and
    seed the boundary detectors after the transversal M. A pure-Z check reads with a
    bare data->ancilla CX ladder; any other check (a star, or a mixed XZZX face)
    reads with a |+> ancilla and a per-corner CX / CZ. `universal_h` forces that
    ancilla-Hadamard form on every check (the non-CSS variants), and `x_frame` lists
    the data qubits initialised |+> and read back in the X basis.
    """
    c = Circuit()
    width = len(stabilizers)

    for q in x_frame:
        c.append("H", [q])

    for r in range(rounds):
        apply_data_noise(c.append, noise_channel, range(num_data), p)

        for primary, anc, corners in stabilizers:
            if not universal_h and all(pauli == "Z" for _q, pauli in corners):
                for q, _pauli in corners:
                    c.append("CX", [q, anc])
            else:
                c.append("H", [anc])
                for q, pauli in corners:
                    if pauli == "X":
                        c.append("CX", [anc, q])
                    else:
                        c.append("CZ", [anc, q])
                c.append("H", [anc])
            c.append("MR", [anc])
            if not primary:
                continue
            if r == 0:
                c.detector(-1)
            else:
                c.detector(-1, -1 - width)

    for q in x_frame:
        c.append("H", [q])
    for q in range(num_data):
        c.append("M", [q])

    for slot, (primary, _anc, corners) in enumerate(stabilizers):
        if not primary:
            continue
        recs = [-num_data + q for q, _pauli in corners]
        prev = -num_data - width + slot
        c.detector(*recs, prev)

    for index, corners in enumerate(observables):
        c.observable(index, *[-num_data + q for q, _pauli in corners])

    return c


def build_circuit(
    num_data: int,
    stabilizers: list[tuple[str, list[int]]],
    observables: list[tuple[str, list[int]]],
    rounds: int,
    noise_channel: str = "DEPOLARIZE1",
    p: float = 0.0,
    boundary: str = "open",
) -> Circuit:
    """
    Assemble a Z-memory syndrome-extraction circuit from an explicit stabilizer
    list. Each stabilizer ("X"/"Z", data-qubit indices) gets one ancilla;
    `rounds` of extraction run with per-round `noise_channel` noise on the data
    (any qliff.noise channel: Pauli, coherent RZ/RX, or amplitude damping). Only
    Z-checks declare round-to-round detectors (graphlike); the final data M seeds
    boundary Z detectors and the Z-type logical observable(s). X-type observables
    are dropped: a Z-basis readout cannot reconstruct them deterministically.
    `boundary` is patch metadata (open/periodic) -- the stabilizer list already
    carries the topology, so it only validates here. Z-checks are grouped first,
    then emission is delegated to the shared _emit_z_memory.
    """
    if boundary not in ("open", "periodic"):
        raise ValueError(f"boundary must be 'open' or 'periodic', got {boundary!r}")
    if noise_channel not in NOISE_FACTORIES:
        raise ValueError(f"unsupported noise channel {noise_channel!r}")

    z_checks = [(i, q) for i, (k, q) in enumerate(stabilizers) if k.upper() == "Z"]
    x_checks = [(i, q) for i, (k, q) in enumerate(stabilizers) if k.upper() == "X"]
    order = z_checks + x_checks
    n_z = len(z_checks)
    stabs = [
        (slot < n_z, num_data + slot, [(d, "Z" if slot < n_z else "X") for d in touch])
        for slot, (_orig, touch) in enumerate(order)
    ]
    z_observables = [
        [(d, "Z") for d in support]
        for kind, support in observables
        if kind.upper() == "Z"
    ]

    return _emit_z_memory(num_data, stabs, z_observables, rounds, noise_channel, p)


def _rotated_plaquettes(
    rows: int,
    cols: int,
    edge: str = "even",
) -> list[tuple[str, list[int]]]:
    """
    Rotated-surface plaquette checkerboard over a rows x cols data grid (data index
    r*cols+col): weight-4 bulk faces plus the weight-2 boundary faces of the chosen
    `edge` set. kind is "Z" on the (r+col)-even faces, "X" on the odd ones. The
    weight-2 keep rule ("even" keeps the column-logical boundary, "odd" its dual) was
    a past EVEN-X/Z bug surface, so it is preserved exactly. Returns [(kind, touch)]
    in scan order; callers attach the ancilla / Hadamard recolour / observable.
    """
    data = {}
    for r in range(rows):
        for col in range(cols):
            data[(r, col)] = r * cols + col

    plaq = []
    for r in range(-1, rows):
        for col in range(-1, cols):
            kind = "Z" if (r + col) % 2 == 0 else "X"
            corners = [(r, col), (r, col + 1), (r + 1, col), (r + 1, col + 1)]
            touch = sorted(data[d] for d in corners if d in data)

            if len(touch) == 4:
                plaq.append((kind, touch))
                continue
            if len(touch) != 2:
                continue

            on_row = r < 0 or r >= rows - 1
            keep_even = (on_row and (r + col) % 2 == 0) or (
                not on_row and (r + col) % 2 == 1
            )
            if keep_even == (edge == "even"):
                plaq.append((kind, touch))

    return plaq


def _square_patch(rows: int, cols: int) -> tuple[int, list, list]:
    """
    Build a rotated-surface-code patch over a `rows` x `cols` data grid: weight-4
    bulk plaquettes plus weight-2 boundary checks (via _rotated_plaquettes), with a
    Z column logical and an X row logical. Returns (num_data, stabilizers, observables).
    """
    data = {}
    for r in range(rows):
        for col in range(cols):
            data[(r, col)] = len(data)

    stabilizers = _rotated_plaquettes(rows, cols)
    logical_z = [data[(r, 0)] for r in range(rows)]
    logical_x = [data[(0, col)] for col in range(cols)]
    observables = [("Z", logical_z), ("X", logical_x)]

    return len(data), stabilizers, observables


def resolve_tiles(
    tiles: list[dict],
) -> tuple[int, list[tuple[str, list[int]]], list[tuple[str, list[int]]]]:
    """
    Map a list of studio tiles to a stabiliser patch from their bounding box. All
    tiles must share a kind: "square" -> rotated-surface patch; "tri" -> triangular
    surface code; "hex" -> 6.6.6 honeycomb color code (both on the triangular axes,
    sized by the bounding box). Returns (num_data, stabilizers, observables).
    """
    if not tiles:
        raise ValueError("resolve_tiles needs at least one tile")

    kinds = {tile.get("kind", "square") for tile in tiles}
    if not kinds <= {"square", "tri", "hex"}:
        raise ValueError(f"unknown tile kind(s) {sorted(kinds - {'square', 'tri', 'hex'})}")
    if len(kinds) != 1:
        raise ValueError(f"mixed tile kinds {sorted(kinds)}; draw one lattice at a time")

    rows_seen = [int(tile["row"]) for tile in tiles]
    cols_seen = [int(tile["col"]) for tile in tiles]
    rows = max(rows_seen) - min(rows_seen) + 1
    cols = max(cols_seen) - min(cols_seen) + 1

    kind = next(iter(kinds))
    if kind == "square":
        return _square_patch(rows, cols)

    # tri / hex tiles resolve to the matching triangular-axis family at a distance
    # set by the drawn extent. Imported lazily: qec.color imports build_circuit from
    # here, so a top-level import would be circular.
    from .color import hex_color_layout, triangular_layout

    distance = max(2, max(rows, cols))

    return triangular_layout(distance) if kind == "tri" else hex_color_layout(distance)
