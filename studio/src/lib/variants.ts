// Canonical surface-code stabiliser-pattern option lists: the single source for
// the three variant selectors (the builder's ControlPanel + the square diagram).
// Each `value` is the wire contract -- it mirrors qliff/server/schema.py -- so
// edit only the display labels here, never the values.

import type { SurfacePattern, SurfaceStart, SurfaceEdge } from "$lib/schema";

// Re-export the variant unions so consumers can pull types + options from one place.
export type { SurfacePattern, SurfaceStart, SurfaceEdge };

export interface VariantOption<T> {
  value: T;
  label: string;
}

export const PATTERN_OPTIONS: VariantOption<SurfacePattern>[] = [
  { value: "css", label: "CSS" },
  { value: "xzzx", label: "XZZX" },
];

export const START_OPTIONS: VariantOption<SurfaceStart>[] = [
  { value: "Z", label: "EVEN-Z (Z-dominated)" },
  { value: "X", label: "EVEN-X (X-dominated)" },
];

export const EDGE_OPTIONS: VariantOption<SurfaceEdge>[] = [
  { value: "even", label: "Even boundary" },
  { value: "odd", label: "Odd boundary" },
];
