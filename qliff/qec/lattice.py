from __future__ import annotations

from ..circuit import Circuit
from ..noise.channel import NOISE_FACTORIES

# Two-qubit channels act on target pairs; PAULI_CHANNEL_1 wants a (px, py, pz)
# vector arg. Everything else is a scalar-arg single-qubit channel on the data.
_TWO_QUBIT_CHANNELS = {"DEPOLARIZE2"}
_VECTOR_CHANNELS = {"PAULI_CHANNEL_1"}


def _apply_data_noise(c: Circuit, channel: str, num_data: int, p: float) -> None:
    """
    Emit the per-round data noise for `channel` at strength p (or theta). 1Q
    scalar channels hit every data qubit; PAULI_CHANNEL_1 spreads p evenly over
    (px, py, pz); DEPOLARIZE2 acts on adjacent data pairs.
    """
    if channel in _VECTOR_CHANNELS:
        arg = (p / 3.0, p / 3.0, p / 3.0)
        for q in range(num_data):
            c.append(channel, [q], arg)

        return

    if channel in _TWO_QUBIT_CHANNELS:
        for q in range(0, num_data - 1, 2):
            c.append(channel, [q, q + 1], p)

        return

    for q in range(num_data):
        c.append(channel, [q], p)


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
    carries the topology, so it only validates here.
    """
    if boundary not in ("open", "periodic"):
        raise ValueError(f"boundary must be 'open' or 'periodic', got {boundary!r}")
    if noise_channel not in NOISE_FACTORIES:
        raise ValueError(f"unsupported noise channel {noise_channel!r}")

    z_checks = [(i, q) for i, (k, q) in enumerate(stabilizers) if k.upper() == "Z"]
    x_checks = [(i, q) for i, (k, q) in enumerate(stabilizers) if k.upper() == "X"]
    order = z_checks + x_checks
    width = len(order)
    anc_of = {orig: num_data + slot for slot, (orig, _q) in enumerate(order)}
    c = Circuit()

    for r in range(rounds):
        _apply_data_noise(c, noise_channel, num_data, p)

        for slot, (orig, touch) in enumerate(order):
            anc = anc_of[orig]
            is_x = slot >= len(z_checks)
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

    for q in range(num_data):
        c.append("M", [q])
    for slot, (_orig, touch) in enumerate(z_checks):
        recs = [-num_data + d for d in touch]
        prev = -num_data - width + slot
        c.detector(*recs, prev)

    index = 0
    for kind, support in observables:
        if kind.upper() != "Z":
            continue
        c.observable(index, *[-num_data + d for d in support])
        index += 1

    return c


def _square_patch(rows: int, cols: int) -> tuple[int, list, list]:
    """
    Build a rotated-surface-code patch over a `rows` x `cols` data grid: weight-4
    bulk plaquettes plus weight-2 boundary checks, with a Z column logical and an
    X row logical. Returns (num_data, stabilizers, observables).
    """
    data = {}
    for r in range(rows):
        for col in range(cols):
            data[(r, col)] = len(data)

    stabilizers = []
    for r in range(-1, rows):
        for col in range(-1, cols):
            kind = "Z" if (r + col) % 2 == 0 else "X"
            corners = [(r, col), (r, col + 1), (r + 1, col), (r + 1, col + 1)]
            touch = sorted(data[d] for d in corners if d in data)

            if len(touch) == 4:
                stabilizers.append((kind, touch))
                continue
            if len(touch) != 2:
                continue

            on_row = r < 0 or r >= rows - 1
            keep = (kind == "Z" and on_row) or (kind == "X" and not on_row)
            if keep:
                stabilizers.append((kind, touch))

    logical_z = [data[(r, 0)] for r in range(rows)]
    logical_x = [data[(0, col)] for col in range(cols)]
    observables = [("Z", logical_z), ("X", logical_x)]

    return len(data), stabilizers, observables


def resolve_tiles(
    tiles: list[dict],
) -> tuple[int, list[tuple[str, list[int]]], list[tuple[str, list[int]]]]:
    """
    Map a list of square studio tiles to a rotated-surface-code patch. Each tile
    {"kind":"square","row":r,"col":c,"rotation":deg} is a unit data site; the
    bounding box of the tiles sets the patch dimensions. "tri"/"hex" tiles are
    diagram-only and raise NotImplementedError. Returns
    (num_data, stabilizers, observables).
    """
    if not tiles:
        raise ValueError("resolve_tiles needs at least one tile")

    for tile in tiles:
        kind = tile.get("kind", "square")
        if kind in ("tri", "hex"):
            raise NotImplementedError(
                f"{kind!r} tiles are diagram-only; no stabilizer mapping yet"
            )
        if kind != "square":
            raise ValueError(f"unknown tile kind {kind!r}")

    rows_seen = [int(tile["row"]) for tile in tiles]
    cols_seen = [int(tile["col"]) for tile in tiles]
    rows = max(rows_seen) - min(rows_seen) + 1
    cols = max(cols_seen) - min(cols_seen) + 1

    return _square_patch(rows, cols)
