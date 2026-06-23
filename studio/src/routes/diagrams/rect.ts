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

export interface Qubit {
  x: number;
  y: number;
  id: string;
  type?: FaceType;
}

export type Parity = (r: number, c: number) => number;

// Standard checkerboard parity: 0 => Z plaquette, 1 => X plaquette.
export const defaultParity: Parity = (r, c) => (r + c) & 1; // & 1 = (r+c) mod 2

// The plaquette face type at cell (r,c). xzzx makes every face the one mixed type;
// otherwise EVEN-Z (start="Z") puts Z on (r+c) even and EVEN-X is its X<->Z dual.
export function faceType(
  r: number,
  c: number,
  pattern: DiagramPattern,
  start: DiagramStart,
): FaceType {
  if (pattern === "xzzx") {
    return "XZZX";
  }

  const even = ((r + c) & 1) === 0;

  return even === (start === "Z") ? "Z" : "X";
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

// Boundary half-circle markers for the dangling weight-2 checks. EVEN-Z puts Z on
// the top/bottom rows and X on the left/right columns; EVEN-X is the X<->Z dual, and
// the `edge` mode picks the other alternating set. The single-type XZZX code has no
// separable boundary, so it draws none.
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

  // EVEN-X inverts the checkerboard, and the odd edge mode shifts the marked set;
  // both flip the parity test. The marker types follow the colouring.
  const offset = (start === "X" ? 1 : 0) ^ (edge === "odd" ? 1 : 0);
  const parity = (rr: number, cc: number): number => (rr + cc + offset) & 1;
  const rowType: FaceType = start === "X" ? "X" : "Z";
  const colType: FaceType = start === "X" ? "Z" : "X";

  const arr: Edge[] = [];
  const r = cellSize / 2;
  const height = m * cellSize;
  const width = n * cellSize;

  for (let c = 0; c < n; c++) {
    if (parity(0, c) === 1) {
      arr.push({
        path: `M ${c * cellSize},0 A ${r},${r} 0 0,1 ${(c + 1) * cellSize},0`,
        type: rowType,
        cx: c * cellSize + r,
        cy: 0 - r / 3,
      });
    }
  }

  for (let c = 0; c < n; c++) {
    if (parity(m - 1, c) === 1) {
      arr.push({
        path: `M ${c * cellSize},${height} A ${r},${r} 0 0,0 ${(c + 1) * cellSize},${height}`,
        type: rowType,
        cx: c * cellSize + r,
        cy: height + r / 3,
      });
    }
  }

  for (let rVal = 0; rVal < m; rVal++) {
    if (parity(rVal, 0) === 0) {
      arr.push({
        path: `M 0,${rVal * cellSize} A ${r},${r} 0 0,0 0,${(rVal + 1) * cellSize}`,
        type: colType,
        cx: 0 - r / 3,
        cy: rVal * cellSize + r,
      });
    }
  }

  for (let rVal = 0; rVal < m; rVal++) {
    if (parity(rVal, n - 1) === 0) {
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

export function getQubits(n: number, m: number, cellSize: number): Qubit[] {
  const arr: Qubit[] = [];

  for (let r = 0; r <= m; r++) {
    for (let c = 0; c <= n; c++) {
      arr.push({
        x: c * cellSize,
        y: r * cellSize,
        id: `D-${r}-${c}`,
      });
    }
  }

  return arr;
}

export function getStabilizers(
  n: number,
  m: number,
  cellSize: number,
  pattern: DiagramPattern,
  start: DiagramStart,
): Qubit[] {
  const arr: Qubit[] = [];

  for (let r = 0; r < m; r++) {
    for (let c = 0; c < n; c++) {
      arr.push({
        x: c * cellSize,
        y: r * cellSize,
        type: faceType(r, c, pattern, start),
        id: `S-${r}-${c}`,
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
  const qubits = getQubits(n, m, cellSize);
  const stabilizers = getStabilizers(n, m, cellSize, pattern, start);
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
