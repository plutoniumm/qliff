// Square surface-code lattice. Data qubits sit on the corners of an n x m grid
// of cells; each cell is a stabilizer plaquette, checkerboarded X / Z. Boundary
// half-circle "edges" mark the dangling weight-2 stabilizers on the perimeter.
// Diagram-only: parity comes from a caller-supplied (r,c) -> 0|1 function.

import { getBounds, getBBox, rotatePoint } from "$lib/geometry";
import type { Point, Bounds, ViewBox } from "$lib/geometry";

export interface Edge {
  path: string;
  type: "X" | "Z";
  fill?: string;
  cx: number;
  cy: number;
}

export interface Qubit {
  x: number;
  y: number;
  id: string;
  type?: "X" | "Z";
}

export type Parity = (r: number, c: number) => number;

// Standard checkerboard parity: 0 => Z plaquette, 1 => X plaquette.
export const defaultParity: Parity = (r, c) => (r + c) & 1; // & 1 = (r+c) mod 2

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

// Boundary half-circle markers. Z on the top/bottom rows (parity 1), X on the
// left/right columns (parity 0), matching the rotated-surface-code boundary.
export function getEdges(
  n: number,
  m: number,
  cellSize: number,
  getParity: Parity,
  showEdges: boolean,
): Edge[] {
  if (!showEdges) return [];

  const arr: Edge[] = [];
  const r = cellSize / 2;
  const height = m * cellSize;
  const width = n * cellSize;

  for (let c = 0; c < n; c++) {
    if (getParity(0, c) === 1) {
      arr.push({
        path: `M ${c * cellSize},0 A ${r},${r} 0 0,1 ${(c + 1) * cellSize},0`,
        type: "Z",
        cx: c * cellSize + r,
        cy: 0 - r / 3,
      });
    }
  }

  for (let c = 0; c < n; c++) {
    if (getParity(m - 1, c) === 1) {
      arr.push({
        path: `M ${c * cellSize},${height} A ${r},${r} 0 0,0 ${(c + 1) * cellSize},${height}`,
        type: "Z",
        cx: c * cellSize + r,
        cy: height + r / 3,
      });
    }
  }

  for (let rVal = 0; rVal < m; rVal++) {
    if (getParity(rVal, 0) === 0) {
      arr.push({
        path: `M 0,${rVal * cellSize} A ${r},${r} 0 0,0 0,${(rVal + 1) * cellSize}`,
        type: "X",
        cx: 0 - r / 3,
        cy: rVal * cellSize + r,
      });
    }
  }

  for (let rVal = 0; rVal < m; rVal++) {
    if (getParity(rVal, n - 1) === 0) {
      arr.push({
        path: `M ${width},${rVal * cellSize} A ${r},${r} 0 0,1 ${width},${(rVal + 1) * cellSize}`,
        type: "X",
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

export function getStabilizers(n: number, m: number, cellSize: number, getParity: Parity): Qubit[] {
  const arr: Qubit[] = [];

  for (let r = 0; r < m; r++) {
    for (let c = 0; c < n; c++) {
      const type = getParity(r, c) === 0 ? "Z" : "X";
      arr.push({
        x: c * cellSize,
        y: r * cellSize,
        type,
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
  getParity: Parity = defaultParity,
): RectLattice {
  const qubits = getQubits(n, m, cellSize);
  const stabilizers = getStabilizers(n, m, cellSize, getParity);
  const edges = getEdges(n, m, cellSize, getParity, showEdges);
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
