from __future__ import annotations

import numpy as np

from ..circuit import Circuit


def repetition_code(distance: int, rounds: int, p: float) -> Circuit:
    """
    Bit-flip repetition-code memory: distance data + distance-1 ancillas,
    per-round X error p per data qubit. Ancillas read adjacent Z parities;
    detectors compare each ancilla round-to-round; final data M seeds boundary
    detectors and the logical-Z observable.
    """
    c = Circuit()
    data = list(range(distance))
    anc = list(range(distance, 2 * distance - 1))
    checks = distance - 1

    for r in range(rounds):
        for q in data:
            c.append("X_ERROR", [q], p)

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


def _qubit_grid(distance: int) -> tuple[dict[tuple[int, int], int], list]:
    """
    Map rotated-surface-code sites to qubit indices. Returns (data, plaq):
    data[(r, c)] -> index over the d x d grid; plaq a list of
    (kind, anc_index, touched_data), kind in {"X", "Z"}.
    """
    data = {}
    for r in range(distance):
        for col in range(distance):
            data[(r, col)] = len(data)

    plaq = []
    index = len(data)

    for r in range(-1, distance):
        for col in range(-1, distance):
            kind = "Z" if (r + col) % 2 == 0 else "X"
            corners = [(r, col), (r, col + 1), (r + 1, col), (r + 1, col + 1)]
            touch = sorted(d for d in corners if d in data)

            if len(touch) == 4:
                plaq.append((kind, index, touch))
                index += 1
                continue
            if len(touch) != 2:
                continue

            on_row = r < 0 or r >= distance - 1
            keep = (kind == "Z" and on_row) or (kind == "X" and not on_row)
            if keep:
                plaq.append((kind, index, touch))
                index += 1

    return data, plaq


def rotated_surface_code(distance: int, rounds: int, p: float) -> Circuit:
    """
    Rotated planar surface-code Z-memory: d x d data grid, weight-4/2 X/Z
    plaquettes, logical |0>, DEPOLARIZE1 p per round. Only Z stabilizers declare
    round-to-round detectors (deterministic in a Z-basis memory), keeping the
    graph graphlike. Final data M seeds boundary Z detectors and the logical-Z
    observable along a column.
    """
    data, plaq = _qubit_grid(distance)
    z_checks = [pq for pq in plaq if pq[0] == "Z"]
    x_checks = [pq for pq in plaq if pq[0] == "X"]
    order = z_checks + x_checks
    width = len(order)
    c = Circuit()

    for r in range(rounds):
        for q in range(distance * distance):
            c.append("DEPOLARIZE1", [q], p)

        for kind, anc, touch in order:
            if kind == "X":
                c.append("H", [anc])
                for d in touch:
                    c.append("CX", [anc, data[d]])
                c.append("H", [anc])
            else:
                for d in touch:
                    c.append("CX", [data[d], anc])
            c.append("MR", [anc])
            if kind != "Z":
                continue
            if r == 0:
                c.detector(-1)
            else:
                c.detector(-1, -1 - width)

    n_data = distance * distance
    for q in range(n_data):
        c.append("M", [q])
    for k, (_kind, _anc, touch) in enumerate(z_checks):
        recs = [-n_data + data[d] for d in touch]
        prev = -n_data - width + k
        c.detector(*recs, prev)

    column = [-n_data + data[(r, 0)] for r in range(distance)]
    c.observable(0, *column)

    return c


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


def unrotated_surface_code(distance: int, rounds: int, p: float) -> Circuit:
    """
    Unrotated (standard) planar surface-code Z-memory: data on the (r+c)-even
    sites of a (2d-1)^2 grid, star X-checks and plaquette Z-checks. Only Z
    stabilizers declare round-to-round detectors (graphlike); final data M seeds
    boundary Z detectors and the logical-Z observable along the top data row.
    """
    side = 2 * distance - 1
    data, x_checks, z_checks = _unrotated_grid(distance)
    order = z_checks + x_checks
    width = len(order)
    n_data = len(data)
    c = Circuit()

    for r in range(rounds):
        for q in range(n_data):
            c.append("DEPOLARIZE1", [q], p)

        for k, (anc, touch) in enumerate(order):
            is_x = k >= len(z_checks)
            if is_x:
                c.append("H", [anc])
                for d in touch:
                    c.append("CX", [anc, d])
                c.append("H", [anc])
            else:
                for d in touch:
                    c.append("CX", [d, anc])
            c.append("MR", [anc])
            if is_x:
                continue
            if r == 0:
                c.detector(-1)
            else:
                c.detector(-1, -1 - width)

    for q in range(n_data):
        c.append("M", [q])
    for k, (_anc, touch) in enumerate(z_checks):
        recs = [-n_data + d for d in touch]
        prev = -n_data - width + k
        c.detector(*recs, prev)

    logical_z = [-n_data + data[(0, col)] for col in range(side) if (0, col) in data]
    c.observable(0, *logical_z)

    return c


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


def toric_code(distance: int, rounds: int, p: float) -> Circuit:
    """
    Toric-code Z-memory with periodic boundaries both directions (wraparound):
    data on the 2d^2 torus edges, d^2 star X-checks and d^2 plaquette Z-checks,
    two logical qubits. Only Z stabilizers declare round-to-round detectors;
    final data M seeds boundary Z detectors and the two logical-Z observables
    (one per non-contractible loop).
    """
    n_data, x_checks, z_checks, logicals = _toric_grid(distance)
    z_anc = list(range(n_data, n_data + len(z_checks)))
    x_anc = list(range(n_data + len(z_checks), n_data + len(z_checks) + len(x_checks)))
    width = len(z_checks) + len(x_checks)
    c = Circuit()

    for r in range(rounds):
        for q in range(n_data):
            c.append("DEPOLARIZE1", [q], p)

        for k, touch in enumerate(z_checks):
            anc = z_anc[k]
            for d in touch:
                c.append("CX", [d, anc])
            c.append("MR", [anc])
            if r == 0:
                c.detector(-1)
            else:
                c.detector(-1, -1 - width)

        for k, touch in enumerate(x_checks):
            anc = x_anc[k]
            c.append("H", [anc])
            for d in touch:
                c.append("CX", [anc, d])
            c.append("H", [anc])
            c.append("MR", [anc])

    for q in range(n_data):
        c.append("M", [q])
    for k, touch in enumerate(z_checks):
        recs = [-n_data + d for d in touch]
        prev = -n_data - width + k
        c.detector(*recs, prev)

    for obs_index, loop in enumerate(logicals):
        c.observable(obs_index, *[-n_data + d for d in loop])

    return c


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
