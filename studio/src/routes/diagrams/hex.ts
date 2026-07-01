// Honeycomb (color-code) lattice. Pointy-flat hexagons tiled in offset columns,
// 3-coloured so each face gets one of {A,B,C}. Every interior edge is shared by
// two faces; its colour is the third one (3 - a - b), giving the colour-code
// edge structure. Diagram-only -- colours/labels are caller-supplied.

import { getBounds, getBBox, edgeKey, ptKey } from "$lib/geometry";
import type { Point, Bounds, ViewBox } from "$lib/geometry";

export type ColorKey = "A" | "B" | "C";
export type ColorMap = Record<ColorKey, string>;
export type LabelMap = Record<ColorKey, string>;

export interface Hexagon {
  col: number;
  row: number;
  x: number;
  y: number;
  points: Point[];
  pointsString: string;
  color: string;
  label: string;
  colorKey: ColorKey;
}

export interface HexEdge {
  p1: Point;
  p2: Point;
  colorKey: ColorKey;
  color: string;
}

export interface HexResize {
  hexHeight: number;
  xSpacing: number;
  padding: number;
}

export interface HexGrid {
  hexes: Hexagon[];
  edges: HexEdge[];
  vertices: Point[]; // data-qubit sites: the deduplicated hexagon corners
  bounds: Bounds;
  view: ViewBox;
}

const colorKeys: ColorKey[] = ["A", "B", "C"];

export function resize(size: number): HexResize {
  const hexHeight = Math.sqrt(3) * size;
  const xSpacing = size * 1.5;
  const padding = Math.max(10, size * 0.6);

  return {
    hexHeight,
    xSpacing,
    padding,
  };
}

// 3-colouring on the triangular dual: shift to axial coords then take a residue.
function colorIndexAt(col: number, row: number): number {
  const aq = col;
  const ar = row - Math.floor(col / 2);

  return (((2 * aq + ar) % 3) + 3) % 3;
}

// The six neighbour (dcol,drow) offsets in face order, by column parity.
function neighborOffsets(col: number): [number, number][] {
  return col % 2 === 0
    ? [
        [1, 0],
        [0, 1],
        [-1, 0],
        [-1, -1],
        [0, -1],
        [1, -1],
      ]
    : [
        [1, 1],
        [0, 1],
        [-1, 1],
        [-1, 0],
        [0, -1],
        [1, 0],
      ];
}

export function Grid(
  R: number,
  C: number,
  size: number,
  colors: ColorMap,
  labels: LabelMap,
): HexGrid {
  const { hexHeight, xSpacing } = resize(size);
  const hexes: Hexagon[] = [];

  for (let col = 0; col < C; col++) {
    for (let row = 0; row < R; row++) {
      const x = size + col * xSpacing;
      const y = hexHeight / 2 + row * hexHeight + (col % 2 === 1 ? hexHeight / 2 : 0);
      const points: Point[] = [];

      for (let i = 0; i < 6; i++) {
        const a = (Math.PI / 180) * (60 * i);
        points.push({ x: x + size * Math.cos(a), y: y + size * Math.sin(a) });
      }

      const colorKey = colorKeys[colorIndexAt(col, row)];
      hexes.push({
        col,
        row,
        x,
        y,
        points,
        pointsString: points.map((p) => `${p.x},${p.y}`).join(" "),
        color: colors[colorKey],
        label: labels[colorKey],
        colorKey,
      });
    }
  }

  const edges = new Map<string, HexEdge>();

  for (const hex of hexes) {
    const offsets = neighborOffsets(hex.col);
    const a = colorIndexAt(hex.col, hex.row);

    for (let i = 0; i < 6; i++) {
      const p1 = hex.points[i];
      const p2 = hex.points[(i + 1) % 6];
      const key = edgeKey(p1, p2);

      if (edges.has(key)) continue;

      const [dc, dr] = offsets[i];
      const b = colorIndexAt(hex.col + dc, hex.row + dr);
      const colorKey = colorKeys[3 - a - b];
      edges.set(key, {
        p1,
        p2,
        colorKey,
        color: colors[colorKey],
      });
    }
  }

  const all: Point[] = [];

  for (const hex of hexes) all.push(...hex.points);

  // Data qubits live on the hexagon corners; corners are shared between faces,
  // so dedupe on a quantized key to get one site per physical vertex.
  const vseen = new Map<string, Point>();

  for (const p of all) {
    const key = ptKey(p.x, p.y);

    if (!vseen.has(key)) vseen.set(key, p);
  }

  const bounds = getBounds(all);
  const view = getBBox(bounds, resize(size).padding, true);

  return {
    hexes,
    edges: Array.from(edges.values()),
    vertices: Array.from(vseen.values()),
    bounds,
    view,
  };
}
