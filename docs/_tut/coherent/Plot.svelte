<script lang="ts">
  // A small, self-contained line plot in an SVG viewBox. Each series is a list of
  // [x, y] points already in DATA coordinates; we map them into the box given the
  // shared x/y domain. An optional vertical marker (the current slider value) and
  // a dot per series at that x make it feel live. No deps -- keeps the page light.
  import { withAlpha } from "$lib/colors";

  export interface Series {
    pts: [number, number][];
    color: string;
    label?: string;
    dash?: boolean;
  }

  let {
    series,
    xmin,
    xmax,
    ymin,
    ymax,
    marker = null,
    xlabel = "",
    ylabel = "",
    height = 180,
  }: {
    series: Series[];
    xmin: number;
    xmax: number;
    ymin: number;
    ymax: number;
    marker?: number | null;
    xlabel?: string;
    ylabel?: string;
    height?: number;
  } = $props();

  const W = 100;
  const ml = 9;
  const mr = 3;
  const mt = 4;
  const mb = 9;

  function sx(x: number): number {
    return ml + ((x - xmin) / (xmax - xmin || 1)) * (W - ml - mr);
  }

  function sy(y: number): number {
    return mt + (1 - (y - ymin) / (ymax - ymin || 1)) * (height - mt - mb);
  }

  function path(pts: [number, number][]): string {
    return pts.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p[0]).toFixed(2)} ${sy(p[1]).toFixed(2)}`).join(" ");
  }

  // y at a given x for a series, by linear interpolation (for the marker dot).
  function yAt(pts: [number, number][], x: number): number | null {
    if (pts.length === 0) {
      return null;
    }
    if (x <= pts[0][0]) {
      return pts[0][1];
    }
    for (let i = 1; i < pts.length; i++) {
      if (x <= pts[i][0]) {
        const [x0, y0] = pts[i - 1];
        const [x1, y1] = pts[i];
        const t = (x - x0) / (x1 - x0 || 1);

        return y0 + t * (y1 - y0);
      }
    }

    return pts[pts.length - 1][1];
  }
</script>

<svg viewBox="0 0 {W} {height}" class="plot" preserveAspectRatio="none" role="img" aria-label={ylabel || "plot"}>
  <!-- axes -->
  <line x1={ml} y1={mt} x2={ml} y2={height - mb} stroke="var(--line)" stroke-width="0.3" />
  <line x1={ml} y1={height - mb} x2={W - mr} y2={height - mb} stroke="var(--line)" stroke-width="0.3" />

  {#if marker !== null && marker >= xmin && marker <= xmax}
    <line
      x1={sx(marker)}
      y1={mt}
      x2={sx(marker)}
      y2={height - mb}
      stroke="var(--muted)"
      stroke-width="0.3"
      stroke-dasharray="1 1"
      opacity="0.7"
    />
  {/if}

  {#each series as s (s.label ?? s.color)}
    <path
      d={path(s.pts)}
      fill="none"
      stroke={s.color}
      stroke-width="0.8"
      stroke-linejoin="round"
      stroke-dasharray={s.dash ? "1.6 1.4" : undefined}
    />
    {#if marker !== null}
      {@const yv = yAt(s.pts, marker)}
      {#if yv !== null && marker >= xmin && marker <= xmax}
        <circle cx={sx(marker)} cy={sy(yv)} r="1.1" fill={s.color} stroke={withAlpha("#000000", 0.3)} stroke-width="0.2" />
      {/if}
    {/if}
  {/each}

  {#if xlabel}
    <text x={(ml + W - mr) / 2} y={height - 1.5} class="ax" text-anchor="middle">{xlabel}</text>
  {/if}
  {#if ylabel}
    <text x={2} y={mt + 2} class="ax" text-anchor="start">{ylabel}</text>
  {/if}
</svg>

<style>
  .plot {
    width: 100%;
    /* viewBox is 0 0 100 H; cap the rendered height so a wide panel can't
       stretch the chart past a laptop fold. preserveAspectRatio="none" means
       this clamp just compresses vertically -- the curves stay readable. */
    max-height: 340px;
    display: block;
  }

  .ax {
    font-size: 3.4px;
    fill: var(--muted);
  }
</style>
