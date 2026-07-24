// Palette for SVG / styles. Every value is a CSS reference -- `C.x` is the string
// "var(--x)", and withAlpha/mix/heat emit `color-mix()` -- so all colors resolve
// through the CSS custom properties defined on `.qtut` (theme.css) and follow
// VitePress' light/dark toggle automatically, with NO per-component edits. The one
// exception is <canvas>/WebGL (the three.js Bloch sphere), which can't read CSS
// vars; that file resolves these expressions to concrete colors at runtime.
//
// Import { C } and draw with C.x, C.z, ... exactly as before.

export const C = {
  bg: "var(--bg)",
  bg2: "var(--bg-2)",
  panel: "var(--panel)",
  line: "var(--line)",
  lineStrong: "var(--line-strong)",
  fg: "var(--fg)",
  muted: "var(--muted)",
  faint: "var(--faint)",
  accent: "var(--accent)",
  accent2: "var(--accent-2)",
  accent3: "var(--accent-3)",
  x: "var(--x)", // X-type stabilizer / Pauli X
  z: "var(--z)", // Z-type stabilizer / Pauli Z
  y: "var(--y)", // Pauli Y
  ok: "var(--ok)", // success / corrected
  bad: "var(--bad)", // failure / logical error
  defect: "var(--defect)", // lit detector / syndrome defect
  data: "var(--data)", // data qubit
} as const;

export type ColorKey = keyof typeof C;

function pct(t: number): string {
  return `${Math.round(Math.max(0, Math.min(1, t)) * 1000) / 10}%`;
}

// A semi-transparent version of any color expression. `color-mix` keeps it
// theme-aware (the base color can be a `var(--..)`). a in [0, 1].
export function withAlpha(color: string, a: number): string {
  return `color-mix(in srgb, ${color} ${pct(a)}, transparent)`;
}

// Linear blend between two color expressions. t in [0, 1] (0 -> a, 1 -> b).
export function mix(a: string, b: string, t: number): string {
  return `color-mix(in srgb, ${b} ${pct(t)}, ${a})`;
}

// Sequential "weight" colormap (cool -> accent -> warm) for heatmaps such as a
// belief/probability field or a tensor's entries. t in [0, 1].
export function heat(t: number): string {
  const k = Math.max(0, Math.min(1, t));

  return k < 0.5 ? mix(C.accent2, C.accent, k * 2) : mix(C.accent, C.accent3, (k - 0.5) * 2);
}
