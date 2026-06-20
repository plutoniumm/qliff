// Triangular lattice (NEW for studio). The plane is tiled with up- and
// down-pointing equilateral triangles arranged in rows; data sites sit on the
// triangle vertices and the faces are 3-coloured. A Kagome variant exposes the
// medial lattice: corner-sharing triangles around hexagonal holes, with sites
// on the edge-midpoints of the parent triangular lattice. Diagram-only -- no
// simulation; faces are coloured purely for visual structure.

import { getBounds, getBBox } from "$lib/geometry";
import type { Point, Bounds, ViewBox } from "$lib/geometry";

export type TriColorKey = "A" | "B" | "C";
export type TriColorMap = Record<TriColorKey, string>;

export interface TriVertex {
  x: number;
  y: number;
  id: string;
}

// A face is a closed polygon (triangle or hexagonal hole) over vertex indices.
export interface TriFace {
  verts: number[]; // indices into the vertex array
  points: Point[];
  pointsString: string;
  up: boolean; // up-pointing triangle (false => down, or hole in Kagome)
  hole: boolean; // true only for Kagome hexagonal holes
  colorKey: TriColorKey;
  color: string;
  cx: number;
  cy: number;
}

export interface TriEdge {
  p1: Point;
  p2: Point;
}

export interface TriLattice {
  vertices: TriVertex[];
  faces: TriFace[];
  edges: TriEdge[];
  bounds: Bounds;
  view: ViewBox;
}

const colorKeys: TriColorKey[] = ["A", "B", "C"];

function polyString(points: Point[]): string {
  return points.map((p) => `${p.x},${p.y}`).join(" ");
}

function centroid(points: Point[]): Point {
  let x = 0;
  let y = 0;

  for (const p of points) {
    x += p.x;
    y += p.y;
  }

  return { x: x / points.length, y: y / points.length };
}

// Vertex grid: `rows`+1 horizontal rows of vertices, each row offset by size/2
// from its neighbour so the columns interleave into equilateral triangles.
// `cols` counts triangles across, so each vertex row has cols+1 sites.
function triVertices(rows: number, cols: number, size: number): TriVertex[] {
  const h = (size * Math.sqrt(3)) / 2;
  const verts: TriVertex[] = [];

  for (let r = 0; r <= rows; r++) {
    const offset = (r % 2) * (size / 2);

    for (let c = 0; c <= cols; c++) {
      verts.push({
        x: offset + c * size,
        y: r * h,
        id: `V-${r}-${c}`,
      });
    }
  }

  return verts;
}

// 3-colour the up/down triangle faces. Up-triangles get a base colour by
// column; the down-triangle nestled to its right takes the next colour.
function buildTriangular(
  rows: number,
  cols: number,
  size: number,
  colors: TriColorMap,
): { vertices: TriVertex[]; faces: TriFace[]; edges: TriEdge[] } {
  const verts = triVertices(rows, cols, size);
  const stride = cols + 1;
  const at = (r: number, c: number) => verts[r * stride + c];

  const faces: TriFace[] = [];

  for (let r = 0; r < rows; r++) {
    const even = r % 2 === 0;

    for (let c = 0; c < cols; c++) {
      // Up-pointing triangle: apex on the row whose offset is smaller.
      let upPts: Point[];
      let upIdx: number[];
      let dnPts: Point[];
      let dnIdx: number[];

      if (even) {
        // top row offset 0, bottom row offset +size/2.
        const tl = at(r, c);
        const tr = at(r, c + 1);
        const bl = at(r + 1, c);
        // up triangle points up: bottom-left vertex sits between tl and tr.
        upPts = [tl, tr, bl];
        upIdx = [r * stride + c, r * stride + c + 1, (r + 1) * stride + c];
        // down triangle: tr, bl, and bottom-right.
        const br = at(r + 1, c + 1);
        dnPts = [tr, br, bl];
        dnIdx = [r * stride + c + 1, (r + 1) * stride + c + 1, (r + 1) * stride + c];
      } else {
        // top row offset +size/2, bottom row offset 0.
        const tl = at(r, c);
        const bl = at(r + 1, c);
        const br = at(r + 1, c + 1);
        upPts = [tl, br, bl];
        upIdx = [r * stride + c, (r + 1) * stride + c + 1, (r + 1) * stride + c];
        const tr = at(r, c + 1);
        dnPts = [tl, tr, br];
        dnIdx = [r * stride + c, r * stride + c + 1, (r + 1) * stride + c + 1];
      }

      const upKey = colorKeys[(r + c) % 3];
      const upC = centroid(upPts);
      faces.push({
        verts: upIdx,
        points: upPts,
        pointsString: polyString(upPts),
        up: true,
        hole: false,
        colorKey: upKey,
        color: colors[upKey],
        cx: upC.x,
        cy: upC.y,
      });
      const dnKey = colorKeys[(r + c + 1) % 3];
      const dnC = centroid(dnPts);
      faces.push({
        verts: dnIdx,
        points: dnPts,
        pointsString: polyString(dnPts),
        up: false,
        hole: false,
        colorKey: dnKey,
        color: colors[dnKey],
        cx: dnC.x,
        cy: dnC.y,
      });
    }
  }

  // Edges: dedupe via index pairs (vertex indices are exact, no jitter).
  const seen = new Set<string>();
  const edges: TriEdge[] = [];

  for (const f of faces) {
    for (let i = 0; i < f.verts.length; i++) {
      const a = f.verts[i];
      const b = f.verts[(i + 1) % f.verts.length];
      const key = a < b ? `${a}-${b}` : `${b}-${a}`;

      if (seen.has(key)) continue;

      seen.add(key);
      edges.push({ p1: verts[a], p2: verts[b] });
    }
  }

  return {
    vertices: verts,
    faces,
    edges,
  };
}

// The Kagome lattice is the medial of the triangular lattice: sites sit at the
// midpoints of the triangular edges. Each triangular face becomes a small
// triangle (joining its three edge-midpoints) and the gaps form hexagonal
// holes. We build it from the triangular faces directly so the small triangles
// inherit up/down orientation and a 3-colouring.
function buildKagome(
  rows: number,
  cols: number,
  size: number,
  colors: TriColorMap,
): { vertices: TriVertex[]; faces: TriFace[]; edges: TriEdge[] } {
  const base = buildTriangular(rows, cols, size, colors);

  // Intern edge-midpoints as the Kagome sites (one per parent edge).
  const verts: TriVertex[] = [];
  const index = new Map<string, number>();
  const round = (v: number) => Math.round(v * 100);
  const key = (p: Point) => `${round(p.x)}:${round(p.y)}`;

  const intern = (p: Point): number => {
    const k = key(p);
    const hit = index.get(k);

    if (hit !== undefined) return hit;

    const id = verts.length;
    index.set(k, id);
    verts.push({
      x: p.x,
      y: p.y,
      id: `K-${id}`,
    });

    return id;
  };

  const mid = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

  const faces: TriFace[] = [];
  const seen = new Set<string>();
  const edges: TriEdge[] = [];

  const addEdge = (a: number, b: number) => {
    const k = a < b ? `${a}-${b}` : `${b}-${a}`;

    if (seen.has(k)) return;

    seen.add(k);
    edges.push({ p1: verts[a], p2: verts[b] });
  };

  for (const f of base.faces) {
    const [p0, p1, p2] = f.points;
    const m01 = mid(p0, p1);
    const m12 = mid(p1, p2);
    const m20 = mid(p2, p0);
    const i0 = intern(m01);
    const i1 = intern(m12);
    const i2 = intern(m20);
    const pts = [verts[i0], verts[i1], verts[i2]];
    const c = centroid(pts);
    faces.push({
      verts: [i0, i1, i2],
      points: pts,
      pointsString: polyString(pts),
      up: f.up,
      hole: false,
      colorKey: f.colorKey,
      color: f.color,
      cx: c.x,
      cy: c.y,
    });
    addEdge(i0, i1);
    addEdge(i1, i2);
    addEdge(i2, i0);
  }

  return {
    vertices: verts,
    faces,
    edges,
  };
}

export function buildTri(
  rows: number,
  cols: number,
  size: number,
  colors: TriColorMap,
  kagome: boolean,
): TriLattice {
  const { vertices, faces, edges } = kagome
    ? buildKagome(rows, cols, size, colors)
    : buildTriangular(rows, cols, size, colors);
  const bounds = getBounds(vertices);
  const view = getBBox(bounds, size * 0.6, true);

  return {
    vertices,
    faces,
    edges,
    bounds,
    view,
  };
}
