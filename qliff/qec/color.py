from __future__ import annotations

import numpy as np

from ..circuit import Circuit
from .lattice import build_circuit

# Color-code & triangular-axis CSS families. The square families
# (qec/codes.py) live on a rectangular grid; these three live on the triangular /
# hexagonal axes the Part-A diagrams draw. All three are built on one PERIODIC
# triangular torus and are medial duals of each other, distinguished by where the
# qubits sit. "hex_color" puts qubits on the triangle FACES and a hexagonal X and Z
# stabiliser (six triangles) around every vertex -- the genuine 6.6.6 honeycomb
# color code (its faces share an edge, so X and Z commute). "triangular" puts qubits
# on the EDGES with X on the weight-6 vertex stars and Z on the weight-3 triangle
# faces -- the triangular surface code. "kagome" is the same edge lattice with the
# roles swapped (X on triangles, Z on hexagonal stars), the medial picture.
#
# Periodic boundaries avoid the open-patch logical explosion and give distance ~ L,
# as qec.codes.toric does for the square family. Stabiliser supports are validated
# to commute (Hx Hz^T = 0) and the logical operators are derived by GF(2) linear
# algebra, so every patch is a provably valid CSS code. The circuit is the shared
# Z-memory (lattice.build_circuit), exactly like the surface families.


# GF(2) linear algebra over qubit-support row vectors.


def _rref(mat: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """
    Row-reduced echelon form over GF(2); returns (reduced, pivot columns).
    """
    m = (mat.copy() % 2).astype(np.uint8)
    rows, cols = m.shape
    pivots: list[int] = []
    r = 0
    for c in range(cols):
        piv = next((i for i in range(r, rows) if m[i, c]), None)
        if piv is None:
            continue
        m[[r, piv]] = m[[piv, r]]
        for i in range(rows):
            if i != r and m[i, c]:
                m[i] ^= m[r]
        pivots.append(c)
        r += 1
        if r == rows:
            break

    return m, pivots


def _rank(mat: np.ndarray) -> int:
    """
    GF(2) rank.
    """
    if mat.size == 0:
        return 0

    return len(_rref(mat)[1])


def _kernel(mat: np.ndarray, n: int) -> np.ndarray:
    """
    Basis (rows) of the right null space {x : mat x = 0} over GF(2).
    """
    if mat.shape[0] == 0:
        return np.eye(n, dtype=np.uint8)

    reduced, pivots = _rref(mat)
    pivot_set = set(pivots)
    free = [c for c in range(n) if c not in pivot_set]
    basis = []
    for f in free:
        v = np.zeros(n, dtype=np.uint8)
        v[f] = 1
        for ri, pc in enumerate(pivots):
            if reduced[ri, f]:
                v[pc] = 1
        basis.append(v)

    return np.array(basis, dtype=np.uint8) if basis else np.zeros((0, n), np.uint8)


def _logicals(
    commute_with: np.ndarray, stabilizers: np.ndarray, n: int
) -> list[np.ndarray]:
    """
    A basis of logical operators: vectors that commute with every `commute_with`
    check (live in its kernel) yet are NOT themselves in the `stabilizers` rowspace.
    Z-logicals take commute_with=Hx, stabilizers=Hz (and X-logicals the mirror).
    """
    kernel = _kernel(commute_with, n)
    reduced: list[np.ndarray] = []
    pivots: list[int] = []

    def absorb(vec: np.ndarray) -> bool:
        # reduce vec against the running basis; return True if it added rank.
        v = (vec.copy() % 2).astype(np.uint8)
        for b, p in zip(reduced, pivots):
            if v[p]:
                v ^= b
        nz = np.nonzero(v)[0]
        if len(nz) == 0:
            return False

        reduced.append(v)
        pivots.append(int(nz[0]))

        return True

    for row in (stabilizers % 2).astype(np.uint8):
        absorb(row)

    out = []
    for v in kernel:
        if absorb(v):
            out.append((v % 2).astype(np.uint8))

    return out


def _reduce_weight(logical: np.ndarray, stabilizers: np.ndarray) -> np.ndarray:
    """
    Greedily lower a logical operator's weight by adding stabilizers that shrink its
    support -- a lighter (still equivalent) representative makes a tighter observable.
    """
    v = (logical.copy() % 2).astype(np.uint8)
    improved = True
    while improved:
        improved = False
        for s in (stabilizers % 2).astype(np.uint8):
            cand = v ^ s
            if int(cand.sum()) < int(v.sum()):
                v = cand
                improved = True

    return v


def _rows(supports: list[list[int]], n: int) -> np.ndarray:
    """
    Stack qubit-support lists into a (checks x n) GF(2) matrix.
    """
    mat = np.zeros((len(supports), n), dtype=np.uint8)
    for i, sup in enumerate(supports):
        for q in sup:
            mat[i, q] = 1

    return mat


# Geometry: one periodic triangular torus, three medial-dual codes.
#
# Everything is built on an L x L PERIODIC triangular lattice (a torus). Periodic
# boundaries avoid the open-patch logical-qubit explosion (rough edges spawn dozens
# of weight-2 logicals) and give a clean distance ~ L, exactly as qec.codes.toric
# does for the square family. The three families are medial duals on this one torus:
# qubits live on the triangle FACES (honeycomb color code), the EDGES (triangular
# surface code), or -- equivalently to the edges -- the kagome sites.


def _tri_torus(distance: int):
    """
    L x L periodic triangular lattice (L = distance). Returns (L, ups, downs):
    each unit cell (r,c) splits into an up-triangle and a down-triangle over the
    wrapped vertex indices V(r,c) = (r%L)*L + (c%L).
    """
    lat = distance

    def vert(r: int, c: int) -> int:
        return (r % lat) * lat + (c % lat)

    ups, downs = [], []
    for r in range(lat):
        for c in range(lat):
            ups.append((vert(r, c), vert(r, c + 1), vert(r + 1, c)))
            downs.append((vert(r, c + 1), vert(r + 1, c + 1), vert(r + 1, c)))

    return lat, ups, downs


def _edge_index(triangles: list[tuple[int, int, int]]):
    """
    Intern every triangle edge as a qubit site; return (num_edges, edge_of, tri_edges)
    where tri_edges[i] is triangle i's three edge-qubit indices.
    """
    edges: dict[tuple[int, int], int] = {}

    def edge(a: int, b: int) -> int:
        key = (a, b) if a < b else (b, a)
        if key not in edges:
            edges[key] = len(edges)

        return edges[key]

    tri_edges = [sorted({edge(a, b), edge(b, c), edge(a, c)}) for a, b, c in triangles]

    return len(edges), edges, tri_edges


def _stars(edges: dict[tuple[int, int], int]) -> list[list[int]]:
    """
    Vertex stars: the edge-qubits incident to each lattice vertex (weight 6 on the
    torus). On a torus every vertex borders six edges, so every star is full-weight.
    """
    incident: dict[int, set[int]] = {}
    for (a, b), eid in edges.items():
        incident.setdefault(a, set()).add(eid)
        incident.setdefault(b, set()).add(eid)

    return [sorted(s) for s in incident.values()]


def _honeycomb(distance: int) -> tuple[int, list[list[int]]]:
    """
    Honeycomb (6.6.6) color code on the torus: qubits sit on the triangle FACES (the
    honeycomb vertices); each lattice vertex's six incident triangles form a hexagon
    face that carries both an X and a Z stabiliser. Returns (num_data, hex_faces).
    """
    _lat, ups, downs = _tri_torus(distance)
    tris = ups + downs
    incident: dict[int, set[int]] = {}
    for tid, tri in enumerate(tris):
        for v in tri:
            incident.setdefault(v, set()).add(tid)

    hexes = [sorted(s) for s in incident.values()]

    return len(tris), hexes


def _triangular(distance: int) -> tuple[int, list[list[int]], list[list[int]]]:
    """
    Triangular surface code on the torus: qubits on EDGES, X on the weight-6 vertex
    stars and Z on the weight-3 triangle faces. Returns (num_data, stars, faces).
    """
    _lat, ups, downs = _tri_torus(distance)
    n, edges, faces = _edge_index(ups + downs)

    return n, _stars(edges), faces


def _kagome(distance: int) -> tuple[int, list[list[int]], list[list[int]]]:
    """
    Kagome code: the medial-dual of the triangular surface code. Same edge qubits
    (kagome sites), but X on the weight-3 corner triangles and Z on the weight-6
    hexagonal stars. Returns (num_data, triangles, hexes).
    """
    _lat, ups, downs = _tri_torus(distance)
    n, edges, faces = _edge_index(ups + downs)

    return n, faces, _stars(edges)


# Assemble a validated CSS code, then the shared Z-memory circuit.


def _assemble(
    n: int,
    x_supports: list[list[int]],
    z_supports: list[list[int]],
) -> tuple[int, list[tuple[str, list[int]]], list[tuple[str, list[int]]]]:
    """
    Validate a CSS code (X / Z supports must commute: every X-stab and Z-stab share an
    even number of qubits) and derive its logicals by GF(2). Returns the
    (num_data, stabilizers, observables) triple lattice.build_circuit consumes, with
    a Z-logical observable (weight-reduced) for the Z-memory.
    """
    hx = _rows(x_supports, n)
    hz = _rows(z_supports, n)
    if x_supports and z_supports and int(((hx @ hz.T) % 2).sum()) != 0:
        raise ValueError(
            "invalid CSS code: an X-stabilizer and Z-stabilizer anticommute"
        )

    z_logicals = [_reduce_weight(v, hz) for v in _logicals(hx, hz, n)]
    x_logicals = [_reduce_weight(v, hx) for v in _logicals(hz, hx, n)]
    if not z_logicals:
        raise ValueError("code encodes no logical qubit (patch too small)")

    stabilizers = [("X", sorted(s)) for s in x_supports] + [
        ("Z", sorted(s)) for s in z_supports
    ]
    observables = [("Z", sorted(np.nonzero(v)[0].tolist())) for v in z_logicals] + [
        ("X", sorted(np.nonzero(v)[0].tolist())) for v in x_logicals
    ]

    return n, stabilizers, observables


def _hex_supports(lat: int) -> tuple[int, list, list]:
    n, faces = _honeycomb(lat)

    return n, faces, faces


def _tri_supports(lat: int) -> tuple[int, list, list]:
    n, stars, faces = _triangular(lat)

    return n, stars, faces


def _kagome_supports(lat: int) -> tuple[int, list, list]:
    n, triangles, hexes = _kagome(lat)

    return n, triangles, hexes


def _search(supports, distance: int) -> tuple[int, list, list]:
    """
    Find the smallest torus size L >= distance that yields a VALID code (k >= 1) and
    assemble it. Some sizes are degenerate -- e.g. the honeycomb color code is only
    3-colourable, hence non-trivial, when L is a multiple of 3 -- so we step L up
    until the layout encodes a logical qubit.
    """
    last = None
    for lat in range(distance, distance + 6):
        n, x_supports, z_supports = supports(lat)
        try:
            return _assemble(n, x_supports, z_supports)
        except ValueError as exc:
            last = exc

    raise ValueError(f"no valid lattice size near distance {distance}: {last}")


def hex_color_layout(distance: int) -> tuple[int, list, list]:
    """
    6.6.6 honeycomb color code: X and Z stabiliser on every hexagonal face.
    """
    return _search(_hex_supports, distance)


def triangular_layout(distance: int) -> tuple[int, list, list]:
    """
    Triangular surface code: X on the vertex stars, Z on the triangle faces.
    """
    return _search(_tri_supports, distance)


def kagome_layout(distance: int) -> tuple[int, list, list]:
    """
    Kagome code: X on the corner triangles, Z on the hexagonal stars.
    """
    return _search(_kagome_supports, distance)


_LAYOUTS = {
    "hex_color": hex_color_layout,
    "triangular": triangular_layout,
    "kagome": kagome_layout,
}


def color_code(
    family: str,
    distance: int,
    rounds: int,
    p: float,
    channel: str = "DEPOLARIZE1",
) -> Circuit:
    """
    Build the `rounds`-round Z-memory syndrome-extraction circuit for one of the
    triangular-axis families ("hex_color" / "triangular" / "kagome") at distance
    `distance` under per-round `channel` noise of strength p. Shares
    lattice.build_circuit with the surface families.
    """
    layout = _LAYOUTS.get(family)
    if layout is None:
        raise ValueError(
            f"unknown color family {family!r}; expected one of {sorted(_LAYOUTS)}"
        )

    num_data, stabilizers, observables = layout(distance)

    return build_circuit(num_data, stabilizers, observables, rounds, channel, p)


def hex_color_code(
    distance: int, rounds: int, p: float, channel: str = "DEPOLARIZE1"
) -> Circuit:
    return color_code("hex_color", distance, rounds, p, channel)


def triangular_code(
    distance: int, rounds: int, p: float, channel: str = "DEPOLARIZE1"
) -> Circuit:
    return color_code("triangular", distance, rounds, p, channel)


def kagome_code(
    distance: int, rounds: int, p: float, channel: str = "DEPOLARIZE1"
) -> Circuit:
    return color_code("kagome", distance, rounds, p, channel)
