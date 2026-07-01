// Pure geometry helpers shared by the passive lattice diagram generators
// (square / triangular / hexagonal). Layout maths for SVG only -- bounding
// boxes, viewBox fitting, point rotation, dedupe keys; no simulation.

export interface Point {
  x: number;
  y: number;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface ViewBox {
  viewBox: string;
  bWidth: number;
  bHeight: number;
  bMax: number;
  viewW: number;
  viewH: number;
}

// Tight axis-aligned bounds over a point cloud (empty => origin).
export function getBounds(points: Point[]): Bounds {
  if (points.length === 0) {
    return {
      minX: 0,
      minY: 0,
      maxX: 0,
      maxY: 0,
    };
  }

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const p of points) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }

  return {
    minX,
    minY,
    maxX,
    maxY,
  };
}

// Pad the bounds, optionally growing to a centred square so the diagram never
// distorts when the SVG is laid out with preserveAspectRatio.
export function getBBox(bounds: Bounds, padding: number, square: boolean): ViewBox {
  const bWidth = Math.max(0, bounds.maxX - bounds.minX) + padding * 2;
  const bHeight = Math.max(0, bounds.maxY - bounds.minY) + padding * 2;
  const bMax = Math.max(bWidth, bHeight);
  const viewW = square ? bMax : bWidth;
  const viewH = square ? bMax : bHeight;

  if (!square) {
    const x = bounds.minX - padding;
    const y = bounds.minY - padding;

    return {
      viewBox: `${x} ${y} ${bWidth} ${bHeight}`,
      bWidth,
      bHeight,
      bMax,
      viewW,
      viewH,
    };
  }

  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  const half = bMax / 2;

  return {
    viewBox: `${cx - half} ${cy - half} ${bMax} ${bMax}`,
    bWidth,
    bHeight,
    bMax,
    viewW,
    viewH,
  };
}

// Apply the 2x2 rotation matrix to an offset (dx,dy) by rad radians, translated
// to centre (cx,cy). Shared kernel for rotatePoint (below) and the canvas tile
// rotation, so the rotation maths lives in exactly one place.
export function rotateOffset(dx: number, dy: number, cx: number, cy: number, rad: number): Point {
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);

  return { x: cx + dx * cos - dy * sin, y: cy + dx * sin + dy * cos };
}

// Rotate p about (cx,cy) by deg degrees (SVG coords: +y down, so clockwise).
export function rotatePoint(p: Point, cx: number, cy: number, deg: number): Point {
  const rad = (Math.PI / 180) * deg;

  return rotateOffset(p.x - cx, p.y - cy, cx, cy, rad);
}

// Serialise a point cloud to an SVG "x,y x,y ..." string for polygon/polyline
// points (and the same path format the diagram builders emit). Single source so
// the stringifier is not re-spelled at each call site.
export function pointsToString(points: Point[]): string {
  return points.map((p) => `${p.x},${p.y}`).join(" ");
}

// Quantise to 1/100 so floating-point jitter does not break dedupe keys.
const round = (v: number) => Math.round(v * 100);

export function ptKey(x: number, y: number): string {
  return `${round(x)}:${round(y)}`;
}

// Order-independent key for an undirected edge between two points.
export function edgeKey(p1: Point, p2: Point): string {
  const k1 = ptKey(p1.x, p1.y);
  const k2 = ptKey(p2.x, p2.y);

  return k1 < k2 ? `${k1}-${k2}` : `${k2}-${k1}`;
}
