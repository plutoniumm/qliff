// Framework-agnostic editor model for the surface-code builder. The Svelte
// canvas component owns interaction (pointer/keyboard) and rendering, and calls
// into this model for every mutation. The model holds the tile array, the
// selection, a clipboard, and an undo/redo history of tile-array snapshots.
//
// Geometry note: tiles live on an integer (row, col) grid. Square tiles project
// onto a rectangular pixel grid; tri/hex tiles project onto triangular axes (two
// basis vectors at 60 degrees). We project to pixels inline here and expose
// per-tile polygon points for the SVG renderer, reusing the shared rotation
// kernel from $lib/geometry.

import type { Tile, TileKind, LatticeSpec, Boundary } from "$lib/schema";
import type { Point } from "$lib/geometry";
import { rotateOffset, getBounds } from "$lib/geometry";

// Re-export Point so existing importers of $lib/canvas (e.g. Canvas.svelte)
// keep getting it from here unchanged; the definition now lives in $lib/geometry.
export type { Point };

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Pixel size of one grid cell. Tiles are centred on grid points (col, row).
export const CELL = 48;
export const ORIGIN: Point = { x: 40, y: 40 };
// sin(60deg) = sqrt(3)/2: the y-stride of the triangular-axis basis vector e2.
const SIN60 = Math.sqrt(3) / 2;
// Rotation snaps to this increment (degrees), so 0, 30, 60, ..., 330.
const ROT_STEP = 30;

let counter = 0;

function freshId(kind: TileKind): string {
  counter += 1;

  return `${kind}-${counter}`;
}

// Representative tile kind for a family's constructor drawing. Square families
// draw a square patch; the triangular-axis families draw their patch in tri/hex
// tiles, which the renderer then lays out on the 60-degree axes.
function familyKind(family: string): TileKind {
  if (family === "triangular") {
    return "tri";
  }

  if (family === "hex_color" || family === "kagome") {
    return "hex";
  }

  return "square";
}

// Tile layout for a canonical code family at a distance, so selecting a code
// DRAWS it on the canvas (a visual "constructor") instead of an empty grid.
// repetition is a 1xd row; the surface/toric families are a dxd data patch; the
// triangular-axis families are a dxd patch of tri/hex tiles on the 60-deg axes.
export function templateTiles(family: string, distance: number): Tile[] {
  const d = Math.max(2, Math.floor(distance));
  const tiles: Tile[] = [];
  const kind = familyKind(family);

  const add = (row: number, col: number): void => {
    tiles.push({
      id: freshId(kind),
      kind,
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

// Triangular axes: e1 = (1, 0) along col, e2 = (0.5, sin60) along row, both
// scaled by CELL. So row shears the column to the right and down by 60 degrees.
export function gridToPixelTri(row: number, col: number): Point {
  return {
    x: ORIGIN.x + (col + row * 0.5) * CELL,
    y: ORIGIN.y + row * SIN60 * CELL,
  };
}

// Inverse of gridToPixelTri: invert the (e1, e2) basis, then round each axis.
export function pixelToGridTri(p: Point): { row: number; col: number } {
  const row = (p.y - ORIGIN.y) / (SIN60 * CELL);
  const col = (p.x - ORIGIN.x) / CELL - row * 0.5;

  return { row: Math.round(row), col: Math.round(col) };
}

// tri/hex tiles snap to the triangular axes; square stays on the rectangular grid.
export function isTriAxis(kind: TileKind): boolean {
  return kind === "tri" || kind === "hex";
}

// Grid -> pixel centre using the transform that matches the tile kind.
export function gridToPixelFor(kind: TileKind, row: number, col: number): Point {
  return isTriAxis(kind) ? gridToPixelTri(row, col) : gridToPixel(row, col);
}

// Pixel -> nearest grid (row, col) using the transform that matches the kind.
export function pixelToGridFor(kind: TileKind, p: Point): { row: number; col: number } {
  return isTriAxis(kind) ? pixelToGridTri(p) : pixelToGrid(p);
}

// Snap an angle (degrees) to the nearest 30-degree increment, wrapped to [0, 360).
export function snapAngle(deg: number): number {
  return (((Math.round(deg / ROT_STEP) * ROT_STEP) % 360) + 360) % 360;
}

// Vertices of a tile's polygon in pixel space, honouring kind + rotation.
// square: axis-aligned box rotated by `rotation` degrees about its centre.
// hex: flat-top hexagon, rotation adds an offset angle.
// tri: equilateral triangle, rotation 0 = pointing up, 180 = pointing down.
export function tilePolygon(t: Tile): Point[] {
  const c = gridToPixelFor(t.kind, t.row, t.col);
  const r = (CELL / 2) * 0.92;
  const rot = (t.rotation * Math.PI) / 180;

  if (t.kind === "square") {
    const base: Point[] = [
      { x: -r, y: -r },
      { x: r, y: -r },
      { x: r, y: r },
      { x: -r, y: r },
    ];

    return base.map((v) => rotateOffset(v.x, v.y, c.x, c.y, rot));
  }

  if (t.kind === "tri") {
    // 0 = up, 180 = down. Build a "pointing up" triangle then rotate.
    const base: Point[] = [
      { x: 0, y: -r },
      { x: r * 0.866, y: r * 0.5 },
      { x: -r * 0.866, y: r * 0.5 },
    ];

    return base.map((v) => rotateOffset(v.x, v.y, c.x, c.y, rot));
  }

  // hex: 6 vertices, flat-top by default.
  const pts: Point[] = [];

  for (let i = 0; i < 6; i++) {
    const a = rot + (Math.PI / 3) * i + Math.PI / 6;
    pts.push({ x: c.x + r * Math.cos(a), y: c.y + r * Math.sin(a) });
  }

  return pts;
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

// Axis-aligned box of a polygon in {x,y,w,h} form -- the same bounds getBounds
// computes, re-shaped from {minX..maxY} for the canvas hit-test rectangles.
function bbox(poly: Point[]): Rect {
  const b = getBounds(poly);

  return {
    x: b.minX,
    y: b.minY,
    w: b.maxX - b.minX,
    h: b.maxY - b.minY,
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
      rotation: snapAngle(rotation),
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
          out.push({
            a: gridToPixelFor(t.kind, t.row, t.col),
            b: gridToPixelFor(n.kind, n.row, n.col),
          });
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

  // Rotate selected tiles by one 30-degree step. Rotations stay snapped to the
  // 30-degree increments (0, 30, 60, ..., 330) for every tile kind.
  rotate(): void {
    if (this.selected.size === 0) {
      return;
    }

    this.pushHistory();

    for (const t of this.tiles) {
      if (!this.selected.has(t.id)) {
        continue;
      }

      t.rotation = snapAngle(t.rotation + ROT_STEP);
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
