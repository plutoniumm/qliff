import numpy as np

from ..circuit import Circuit


def repetition_code(distance, rounds, p):
    """
    Build a bit-flip repetition-code memory experiment as a Circuit.

    ``distance`` data qubits hold one logical bit; ``distance - 1`` ancillas
    measure neighbouring Z parities each round via CX gates and ``MR``. Each data
    qubit suffers an X error with probability ``p`` per round. Detectors compare
    each ancilla to its previous round (and the first round to zero); a final
    round of data ``M`` seeds boundary detectors plus the logical-Z observable
    spanning all data qubits.
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


def _qubit_grid(distance):
    """
    Map rotated-surface-code coordinates to qubit indices.

    Data qubits sit on integer ``(row, col)`` sites with ``0 <= row, col <
    distance``; measure qubits sit on the half-integer plaquette centres. Returns
    ``(data, plaq)`` where ``data[(r, c)]`` is a qubit index and ``plaq`` lists
    ``(kind, r, c, neighbours)`` tuples for each stabilizer, ``kind`` in
    ``{"X", "Z"}`` and ``neighbours`` the data qubits it touches.
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


def rotated_surface_code(distance, rounds, p):
    """
    Build a rotated planar surface-code Z-memory experiment as a Circuit.

    Data qubits form a ``distance x distance`` grid; X- and Z-type stabilizers
    tile the plaquettes in the rotated checkerboard, weight-4 in the bulk and
    weight-2 on the boundaries. The logical qubit starts in ``|0>``: each round
    measures every stabilizer with an ancilla (H-conjugated CX schedule for X
    checks, plain CX for Z checks) and resets it with ``MR``. Circuit-level
    DEPOLARIZE1 noise of strength ``p`` hits every data qubit each round. Only the
    Z-type stabilizers -- which are deterministic for a Z-basis memory -- declare
    detectors comparing consecutive rounds, so the detector graph stays graphlike
    (X and Y data faults enter through their X-component alone). The final data
    ``M`` seeds boundary Z detectors and the logical-Z observable along one
    column.
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


def logical_fidelity(predictions, observed):
    """
    Return logical fidelity ``1 - mean(predictions != observed)``.

    ``predictions`` and ``observed`` are arrays of decoded vs true observable
    flips; a row counts as an error if any observable disagrees. The complement
    of the logical error rate.
    """
    predictions = np.asarray(predictions)
    observed = np.asarray(observed)
    if predictions.ndim > 1:
        mismatch = np.any(predictions != observed, axis=1)
    else:
        mismatch = predictions != observed

    return 1.0 - float(np.mean(mismatch))
