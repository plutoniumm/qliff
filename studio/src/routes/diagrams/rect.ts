// Square surface-code lattice. Data qubits sit on the corners of an n x m grid
// of cells; each cell is a stabilizer plaquette, checkerboarded X / Z. Boundary
// half-circle "edges" mark the dangling weight-2 stabilizers on the perimeter.
// Diagram-only: parity comes from a caller-supplied (r,c) -> 0|1 function.

import { getBounds, getBBox, rotatePoint } from "$lib/geometry";
import type { Point, Bounds, ViewBox } from "$lib/geometry";

// Stabiliser face type: X / Z plaquettes for the CSS colourings, or the single mixed
// "XZZX" face shared by every plaquette in the XZZX code.
export type FaceType = "X" | "Z" | "XZZX";

// Diagram stabiliser-pattern knobs, mirroring the runnable surface variants:
// pattern (css vs single-type xzzx), start (the X/Z colouring: EVEN-Z puts Z on
// (r+c) even, EVEN-X is its dual), edge (which alternating boundary set is marked).
export type DiagramPattern = "css" | "xzzx";
export type DiagramStart = "Z" | "X";
export type DiagramEdge = "even" | "odd";

export interface Edge {
  path: string;
  type: FaceType;
  fill?: string;
  cx: number;
  cy: number;
}

// One conic-gradient sector of an XZZX plaquette: a corner "kite" (centre -> edge
// midpoint -> corner -> next edge midpoint), coloured by that corner's measured Pauli.
export interface Wedge {
  path: string;
  pauli: "X" | "Z";
}

export interface Qubit {
  x: number;
  y: number;
  id: string;
  type?: FaceType;
  pauli?: "X" | "Z";
  wedges?: Wedge[];
}

// ONE parity function drives every glyph (faces + boundary half-circles), exactly
// like surfacepro: faces and edges read the same checkerboard, so they can never
// disagree (no same-colour neighbours). `edge` (even/odd) shifts the whole board by
// one cell -- surfacepro's "mode A/B"; `start` (Z/X) is a pure relabel -- its "flip".
export function rectParity(r: number, c: number, edge: DiagramEdge): number {
  const offset = edge === "odd" ? 1 : 0;

  return (r + c + offset) & 1; // & 1 = mod 2
}

// EVEN-X (start="X") relabels X<->Z everywhere; EVEN-Z leaves it. Applied uniformly
// to faces and edges so the relabel can't introduce a clash.
function flipType(t: "X" | "Z", start: DiagramStart): "X" | "Z" {
  if (start !== "X") return t;

  return t === "X" ? "Z" : "X";
}

// The Pauli a single data qubit carries in the XZZX code: its corners checkerboard
// X/Z by site parity, so each plaquette reads X-Z-Z-X around its four corners. Shared
// corners agree because the value is a function of the absolute site, not the cell.
export function qubitPauli(
  qr: number,
  qc: number,
  start: DiagramStart,
): "X" | "Z" {
  return flipType(((qr + qc) & 1) === 0 ? "X" : "Z", start);
}

// The plaquette face type at cell (r,c). xzzx makes every face the one mixed type
// (its X/Z structure is carried by the per-qubit labels instead); otherwise the cell
// is Z on the even sublattice, X on the odd -- relabelled by `start`, shifted by `edge`.
export function faceType(
  r: number,
  c: number,
  pattern: DiagramPattern,
  start: DiagramStart,
  edge: DiagramEdge,
): FaceType {
  if (pattern === "xzzx") {
    return "XZZX";
  }

  return flipType(rectParity(r, c, edge) === 0 ? "Z" : "X", start);
}

export function getRectBounds(n: number, m: number, cellSize: number, rotated: boolean): Bounds {
  const width = n * cellSize;
  const height = m * cellSize;
  const corners: Point[] = [
    { x: 0, y: 0 },
    { x: width, y: 0 },
    { x: width, y: height },
    { x: 0, y: height },
  ];

  if (!rotated) return getBounds(corners);

  const cx = width / 2;
  const cy = height / 2;

  return getBounds(corners.map((p) => rotatePoint(p, cx, cy, 45)));
}

// Boundary half-circle markers for the dangling weight-2 checks. Read off the SAME
// parity as the faces (surfacepro's getEdges): top/bottom carry the row type where
// parity is 1, left/right the column type where parity is 0 -- so each marker lands
// opposite the face it touches and never beside a same-type sibling. `start` relabels
// both marker families with the faces. The single-type XZZX code has no separable
// boundary, so it draws none.
export function getEdges(
  n: number,
  m: number,
  cellSize: number,
  pattern: DiagramPattern,
  start: DiagramStart,
  edge: DiagramEdge,
  showEdges: boolean,
): Edge[] {
  if (!showEdges || pattern === "xzzx") return [];

  const rowType = flipType("Z", start);
  const colType = flipType("X", start);

  const arr: Edge[] = [];
  const r = cellSize / 2;
  const height = m * cellSize;
  const width = n * cellSize;

  for (let c = 0; c < n; c++) {
    if (rectParity(0, c, edge) === 1) {
      arr.push({
        path: `M ${c * cellSize},0 A ${r},${r} 0 0,1 ${(c + 1) * cellSize},0`,
        type: rowType,
        cx: c * cellSize + r,
        cy: 0 - r / 3,
      });
    }
  }

  for (let c = 0; c < n; c++) {
    if (rectParity(m - 1, c, edge) === 1) {
      arr.push({
        path: `M ${c * cellSize},${height} A ${r},${r} 0 0,0 ${(c + 1) * cellSize},${height}`,
        type: rowType,
        cx: c * cellSize + r,
        cy: height + r / 3,
      });
    }
  }

  for (let rVal = 0; rVal < m; rVal++) {
    if (rectParity(rVal, 0, edge) === 0) {
      arr.push({
        path: `M 0,${rVal * cellSize} A ${r},${r} 0 0,0 0,${(rVal + 1) * cellSize}`,
        type: colType,
        cx: 0 - r / 3,
        cy: rVal * cellSize + r,
      });
    }
  }

  for (let rVal = 0; rVal < m; rVal++) {
    if (rectParity(rVal, n - 1, edge) === 0) {
      arr.push({
        path: `M ${width},${rVal * cellSize} A ${r},${r} 0 0,1 ${width},${(rVal + 1) * cellSize}`,
        type: colType,
        cx: width + r / 3,
        cy: rVal * cellSize + r,
      });
    }
  }

  return arr;
}

// XZZX carries its X/Z structure on the qubits, so tag each data site with the Pauli
// it would hold; CSS leaves them untyped (the colour lives on the faces instead).
export function getQubits(
  n: number,
  m: number,
  cellSize: number,
  pattern: DiagramPattern,
  start: DiagramStart,
): Qubit[] {
  const arr: Qubit[] = [];

  for (let r = 0; r <= m; r++) {
    for (let c = 0; c <= n; c++) {
      arr.push({
        x: c * cellSize,
        y: r * cellSize,
        id: `D-${r}-${c}`,
        pauli: pattern === "xzzx" ? qubitPauli(r, c, start) : undefined,
      });
    }
  }

  return arr;
}

// The four corner wedges of the XZZX plaquette (r,c). Each kite runs centre -> edge
// midpoint -> corner -> adjacent edge midpoint, tiling the square into a conic
// red/blue pinwheel whose sectors are the corner data qubits' Paulis.
export function xzzxWedges(
  r: number,
  c: number,
  cellSize: number,
  start: DiagramStart,
): Wedge[] {
  const x = c * cellSize;
  const y = r * cellSize;
  const h = cellSize / 2;
  const ctr = `${x + h},${y + h}`;
  const tm = `${x + h},${y}`;
  const rm = `${x + cellSize},${y + h}`;
  const bm = `${x + h},${y + cellSize}`;
  const lm = `${x},${y + h}`;
  const tl = `${x},${y}`;
  const tr = `${x + cellSize},${y}`;
  const br = `${x + cellSize},${y + cellSize}`;
  const bl = `${x},${y + cellSize}`;

  return [
    { path: `M ${ctr} L ${tm} L ${tl} L ${lm} Z`, pauli: qubitPauli(r, c, start) },
    { path: `M ${ctr} L ${tm} L ${tr} L ${rm} Z`, pauli: qubitPauli(r, c + 1, start) },
    { path: `M ${ctr} L ${rm} L ${br} L ${bm} Z`, pauli: qubitPauli(r + 1, c + 1, start) },
    { path: `M ${ctr} L ${bm} L ${bl} L ${lm} Z`, pauli: qubitPauli(r + 1, c, start) },
  ];
}

export function getStabilizers(
  n: number,
  m: number,
  cellSize: number,
  pattern: DiagramPattern,
  start: DiagramStart,
  edge: DiagramEdge,
): Qubit[] {
  const arr: Qubit[] = [];

  for (let r = 0; r < m; r++) {
    for (let c = 0; c < n; c++) {
      arr.push({
        x: c * cellSize,
        y: r * cellSize,
        type: faceType(r, c, pattern, start, edge),
        id: `S-${r}-${c}`,
        wedges: pattern === "xzzx" ? xzzxWedges(r, c, cellSize, start) : undefined,
      });
    }
  }

  return arr;
}

export interface RectLattice {
  qubits: Qubit[];
  stabilizers: Qubit[];
  edges: Edge[];
  bounds: Bounds;
  view: ViewBox;
}

// Assemble everything the view needs in one call (keeps the Svelte side thin).
export function buildRect(
  n: number,
  m: number,
  cellSize: number,
  showEdges: boolean,
  rotated: boolean,
  pattern: DiagramPattern = "css",
  start: DiagramStart = "Z",
  edge: DiagramEdge = "even",
): RectLattice {
  const qubits = getQubits(n, m, cellSize, pattern, start);
  const stabilizers = getStabilizers(n, m, cellSize, pattern, start, edge);
  const edges = getEdges(n, m, cellSize, pattern, start, edge, showEdges);
  const bounds = getRectBounds(n, m, cellSize, rotated);
  const view = getBBox(bounds, cellSize * 0.6, true);

  return {
    qubits,
    stabilizers,
    edges,
    bounds,
    view,
  };
}
