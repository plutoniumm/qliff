// Framework-agnostic editor model for the surface-code builder. The Svelte
// canvas component owns interaction (pointer/keyboard) and rendering, and calls
// into this model for every mutation. The model holds the tile array, the
// selection, a clipboard, and an undo/redo history of tile-array snapshots.
//
// Geometry note: tiles live on an integer (row, col) grid. We project to pixels
// inline here (no dependency on $lib/geometry, which a sibling agent still
// owns) and expose per-tile polygon points for the SVG renderer.

import type { Tile, TileKind, LatticeSpec, Boundary } from "$lib/schema";

export interface Point {
  x: number;
  y: number;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Pixel size of one grid cell. Tiles are centred on grid points (col, row).
export const CELL = 48;
export const ORIGIN: Point = { x: 40, y: 40 };

let counter = 0;

function freshId(kind: TileKind): string {
  counter += 1;

  return `${kind}-${counter}`;
}

// Square-tile layout for a canonical code family at a distance, so selecting a
// code DRAWS it on the canvas (a visual "constructor") instead of an empty grid.
// repetition is a 1xd row; the surface/toric families are a dxd data patch.
export function templateTiles(family: string, distance: number): Tile[] {
  const d = Math.max(2, Math.floor(distance));
  const tiles: Tile[] = [];

  const add = (row: number, col: number): void => {
    tiles.push({
      id: freshId("square"),
      kind: "square",
      row,
      col,
      rotation: 0,
    });
  };

  if (family === "repetition") {
    for (let c = 0; c < d; c++) {
      add(0, c);
    }

    return tiles;
  }

  for (let r = 0; r < d; r++) {
    for (let c = 0; c < d; c++) {
      add(r, c);
    }
  }

  return tiles;
}

// Grid (col, row) -> pixel centre.
export function gridToPixel(row: number, col: number): Point {
  return { x: ORIGIN.x + col * CELL, y: ORIGIN.y + row * CELL };
}

// Pixel -> nearest grid (row, col), snapping to integers.
export function pixelToGrid(p: Point): { row: number; col: number } {
  return {
    row: Math.round((p.y - ORIGIN.y) / CELL),
    col: Math.round((p.x - ORIGIN.x) / CELL),
  };
}

// Vertices of a tile's polygon in pixel space, honouring kind + rotation.
// square: axis-aligned box rotated by `rotation` degrees about its centre.
// hex: flat-top hexagon, rotation adds an offset angle.
// tri: equilateral triangle, rotation 0 = pointing up, 180 = pointing down.
export function tilePolygon(t: Tile): Point[] {
  const c = gridToPixel(t.row, t.col);
  const r = (CELL / 2) * 0.92;
  const rot = (t.rotation * Math.PI) / 180;

  if (t.kind === "square") {
    const base: Point[] = [
      { x: -r, y: -r },
      { x: r, y: -r },
      { x: r, y: r },
      { x: -r, y: r },
    ];

    return base.map((v) => rotateAbout(v, rot, c));
  }

  if (t.kind === "tri") {
    // 0 = up, 180 = down. Build a "pointing up" triangle then rotate.
    const base: Point[] = [
      { x: 0, y: -r },
      { x: r * 0.866, y: r * 0.5 },
      { x: -r * 0.866, y: r * 0.5 },
    ];

    return base.map((v) => rotateAbout(v, rot, c));
  }

  // hex: 6 vertices, flat-top by default.
  const pts: Point[] = [];

  for (let i = 0; i < 6; i++) {
    const a = rot + (Math.PI / 3) * i + Math.PI / 6;
    pts.push({ x: c.x + r * Math.cos(a), y: c.y + r * Math.sin(a) });
  }

  return pts;
}

function rotateAbout(v: Point, rot: number, c: Point): Point {
  const cos = Math.cos(rot);
  const sin = Math.sin(rot);

  return {
    x: c.x + v.x * cos - v.y * sin,
    y: c.y + v.x * sin + v.y * cos,
  };
}

// Even-odd point-in-polygon for hit-testing tiles under the pointer.
function pointInPolygon(p: Point, poly: Point[]): boolean {
  let inside = false;

  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    const intersect =
      a.y > p.y !== b.y > p.y &&
      p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x;

    if (intersect) {
      inside = !inside;
    }
  }

  return inside;
}

function bbox(poly: Point[]): Rect {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const v of poly) {
    minX = Math.min(minX, v.x);
    minY = Math.min(minY, v.y);
    maxX = Math.max(maxX, v.x);
    maxY = Math.max(maxY, v.y);
  }

  return {
    x: minX,
    y: minY,
    w: maxX - minX,
    h: maxY - minY,
  };
}

function rectIntersects(a: Rect, b: Rect): boolean {
  return (
    a.x < b.x + b.w &&
    a.x + a.w > b.x &&
    a.y < b.y + b.h &&
    a.y + a.h > b.y
  );
}

// Normalise a drag rectangle (any drag direction) to positive width/height.
export function normalizeRect(a: Point, b: Point): Rect {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(a.x - b.x),
    h: Math.abs(a.y - b.y),
  };
}

// A drawn link between two edge-adjacent tile centres (for the canvas overlay).
export interface Link {
  a: Point;
  b: Point;
}

// Live summary of the drawn lattice, shown in the canvas HUD + control panel.
export interface CanvasStats {
  count: number; // tiles placed
  groups: number; // connected components (edge adjacency)
  rows: number; // bounding-box height in cells
  cols: number; // bounding-box width in cells
  kinds: Record<TileKind, number>;
}

export class CanvasModel {
  tiles: Tile[] = [];
  selected: Set<string> = new Set();
  boundary: Boundary = "open";

  private clipboard: Tile[] = [];
  private undoStack: Tile[][] = [];
  private redoStack: Tile[][] = [];

  private snapshot(): Tile[] {
    return this.tiles.map((t) => ({ ...t }));
  }

  private pushHistory(): void {
    this.undoStack.push(this.snapshot());

    if (this.undoStack.length > 200) {
      this.undoStack.shift();
    }

    this.redoStack = [];
  }

  undo(): void {
    const prev = this.undoStack.pop();

    if (prev === undefined) {
      return;
    }

    this.redoStack.push(this.snapshot());
    this.tiles = prev;
    this.pruneSelection();
  }

  redo(): void {
    const next = this.redoStack.pop();

    if (next === undefined) {
      return;
    }

    this.undoStack.push(this.snapshot());
    this.tiles = next;
    this.pruneSelection();
  }

  private pruneSelection(): void {
    const ids = new Set(this.tiles.map((t) => t.id));

    for (const id of [...this.selected]) {
      if (!ids.has(id)) {
        this.selected.delete(id);
      }
    }
  }

  addTile(kind: TileKind, row: number, col: number, rotation = 0): Tile {
    this.pushHistory();
    const tile: Tile = {
      id: freshId(kind),
      kind,
      row,
      col,
      rotation,
    };
    this.tiles.push(tile);

    return tile;
  }

  // Topmost tile under a pixel point, or null on empty space.
  hitTest(p: Point): string | null {
    for (let i = this.tiles.length - 1; i >= 0; i--) {
      if (pointInPolygon(p, tilePolygon(this.tiles[i]))) {
        return this.tiles[i].id;
      }
    }

    return null;
  }

  select(id: string, additive = false): void {
    if (!additive) {
      this.selected.clear();
    }

    this.selected.add(id);
  }

  toggle(id: string): void {
    if (this.selected.has(id)) {
      this.selected.delete(id);
    } else {
      this.selected.add(id);
    }
  }

  clearSelection(): void {
    this.selected.clear();
  }

  selectAll(): void {
    this.selected = new Set(this.tiles.map((t) => t.id));
  }

  // Marquee select: every tile whose bounding box overlaps the rectangle.
  // `base` (when given) is the selection to start from, so a live marquee can be
  // re-evaluated every pointer move without losing a prior additive selection.
  selectInRect(marquee: Rect, additive = false, base?: Set<string>): void {
    this.selected = additive && base ? new Set(base) : new Set();

    for (const t of this.tiles) {
      if (rectIntersects(bbox(tilePolygon(t)), marquee)) {
        this.selected.add(t.id);
      }
    }
  }

  // Edge-adjacent tile pairs (|Δrow|+|Δcol| == 1), as centre-to-centre links for
  // the canvas overlay so the user can see which tiles actually touch.
  links(): Link[] {
    const at = new Map<string, Tile>();

    for (const t of this.tiles) {
      at.set(`${t.row},${t.col}`, t);
    }

    const out: Link[] = [];

    for (const t of this.tiles) {
      // only +row / +col neighbours, so each pair is emitted once.
      for (const [dr, dc] of [
        [1, 0],
        [0, 1],
      ]) {
        const n = at.get(`${t.row + dr},${t.col + dc}`);

        if (n !== undefined) {
          out.push({ a: gridToPixel(t.row, t.col), b: gridToPixel(n.row, n.col) });
        }
      }
    }

    return out;
  }

  // Tile count, connected-component count (edge adjacency), bounding box, and a
  // per-kind tally. Drives the live "Surface" readout.
  stats(): CanvasStats {
    const kinds: Record<TileKind, number> = {
      square: 0,
      tri: 0,
      hex: 0,
    };

    for (const t of this.tiles) {
      kinds[t.kind] += 1;
    }

    if (this.tiles.length === 0) {
      return {
        count: 0,
        groups: 0,
        rows: 0,
        cols: 0,
        kinds,
      };
    }

    const rowsSeen = this.tiles.map((t) => t.row);
    const colsSeen = this.tiles.map((t) => t.col);

    // connected components over occupied cells via flood fill (edge adjacency).
    const occupied = new Set(this.tiles.map((t) => `${t.row},${t.col}`));
    const seen = new Set<string>();
    let groups = 0;

    for (const cell of occupied) {
      if (seen.has(cell)) {
        continue;
      }

      groups += 1;
      const stack = [cell];

      while (stack.length > 0) {
        const cur = stack.pop() as string;

        if (seen.has(cur)) {
          continue;
        }

        seen.add(cur);
        const [r, c] = cur.split(",").map(Number);

        for (const [dr, dc] of [
          [1, 0],
          [-1, 0],
          [0, 1],
          [0, -1],
        ]) {
          const k = `${r + dr},${c + dc}`;

          if (occupied.has(k) && !seen.has(k)) {
            stack.push(k);
          }
        }
      }
    }

    return {
      count: this.tiles.length,
      groups,
      rows: Math.max(...rowsSeen) - Math.min(...rowsSeen) + 1,
      cols: Math.max(...colsSeen) - Math.min(...colsSeen) + 1,
      kinds,
    };
  }

  private selectedTiles(): Tile[] {
    return this.tiles.filter((t) => this.selected.has(t.id));
  }

  // Move every selected tile by (drow, dcol) grid cells. Already grid-snapped
  // since tiles store integer row/col.
  move(drow: number, dcol: number): void {
    if (this.selected.size === 0 || (drow === 0 && dcol === 0)) {
      return;
    }

    this.pushHistory();

    for (const t of this.tiles) {
      if (this.selected.has(t.id)) {
        t.row += drow;
        t.col += dcol;
      }
    }
  }

  // Rotate selected tiles. square +90, hex +60, tri flips 0<->180.
  rotate(): void {
    if (this.selected.size === 0) {
      return;
    }

    this.pushHistory();

    for (const t of this.tiles) {
      if (!this.selected.has(t.id)) {
        continue;
      }

      if (t.kind === "square") {
        t.rotation = (t.rotation + 90) % 360;
      } else if (t.kind === "hex") {
        t.rotation = (t.rotation + 60) % 360;
      } else {
        t.rotation = t.rotation === 0 ? 180 : 0;
      }
    }
  }

  delete(): void {
    if (this.selected.size === 0) {
      return;
    }

    this.pushHistory();
    this.tiles = this.tiles.filter((t) => !this.selected.has(t.id));
    this.selected.clear();
  }

  copy(): void {
    this.clipboard = this.selectedTiles().map((t) => ({ ...t }));
  }

  // Paste the clipboard offset by one cell down/right; new ids; select pasted.
  paste(): void {
    if (this.clipboard.length === 0) {
      return;
    }

    this.pushHistory();
    const pasted: Tile[] = this.clipboard.map((t) => ({
      ...t,
      id: freshId(t.kind),
      row: t.row + 1,
      col: t.col + 1,
    }));
    this.tiles.push(...pasted);
    this.selected = new Set(pasted.map((t) => t.id));
  }

  // Produce the wire LatticeSpec from the drawn tiles. Stabilizers/observables
  // are left empty here; the server resolves them from the tile geometry.
  toSpec(): LatticeSpec {
    return {
      tiles: this.tiles.map((t) => ({ ...t })),
      stabilizers: [],
      observables: [],
      boundary: this.boundary,
    };
  }

  // Replace the canvas with a canonical code's drawn tiles (a visual construct
  // of the selected family/distance). The run still uses the template path; this
  // is the "code constructor" view that's shown for every selected code.
  loadTemplate(family: string, distance: number): void {
    this.pushHistory();
    this.tiles = templateTiles(family, distance);
    this.boundary = family === "toric" ? "periodic" : "open";
    this.selected.clear();
  }

  clear(): void {
    if (this.tiles.length === 0) {
      return;
    }

    this.pushHistory();
    this.tiles = [];
    this.selected.clear();
  }

  fromSpec(spec: LatticeSpec): void {
    this.pushHistory();
    this.tiles = (spec.tiles ?? []).map((t) => ({ ...t }));
    this.boundary = spec.boundary ?? "open";
    this.selected.clear();

    // Keep id counter ahead of any loaded ids to avoid future collisions.
    for (const t of this.tiles) {
      const n = Number(t.id.split("-").pop());

      if (Number.isFinite(n) && n > counter) {
        counter = n;
      }
    }
  }
}
