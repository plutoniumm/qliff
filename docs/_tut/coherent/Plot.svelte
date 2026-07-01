<script lang="ts" module>
  // Series shape consumed by Coherent.svelte. Each series is a list of [x, y]
  // points in DATA coordinates, drawn as one line (optionally dashed).
  export interface Series {
    pts: [number, number][];
    color: string;
    label?: string;
    dash?: boolean;
  }
</script>

<script lang="ts">
  // A compact line plot: the shared uPlot wrapper draws the lines/axes; a draw
  // hook adds the live slider MARKER (a vertical line) plus an interpolated dot
  // per series at that x, so the figure tracks the slider.
  import { C } from "$lib/colors";
  import LinePlot, { type DrawKit } from "$shared/LinePlot.svelte";

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

  // New closure whenever marker/series change, so the wrapper redraws the overlay.
  const annotate = $derived.by(() => {
    const m = marker;
    const ser = series;
    const lo = xmin;
    const hi = xmax;

    return (k: DrawKit) => {
      if (m === null || m < lo || m > hi) {
        return;
      }
      const { ctx, x, y, bbox, color, pxr } = k;
      const mx = x(m);
      ctx.save();
      ctx.beginPath();
      ctx.setLineDash([4 * pxr, 4 * pxr]);
      ctx.strokeStyle = color(C.muted);
      ctx.lineWidth = 1 * pxr;
      ctx.globalAlpha = 0.7;
      ctx.moveTo(mx, bbox.top);
      ctx.lineTo(mx, bbox.top + bbox.height);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
      for (const s of ser) {
        const yv = yAt(s.pts, m);
        if (yv === null) {
          continue;
        }
        ctx.beginPath();
        ctx.arc(mx, y(yv), 3 * pxr, 0, Math.PI * 2);
        ctx.fillStyle = color(s.color);
        ctx.fill();
        ctx.lineWidth = 1 * pxr;
        ctx.strokeStyle = "rgba(0,0,0,0.35)";
        ctx.stroke();
      }
      ctx.restore();
    };
  });
</script>

<LinePlot
  {series}
  xRange={[xmin, xmax]}
  yRange={[ymin, ymax]}
  xLabel={xlabel}
  yLabel={ylabel}
  {height}
  {annotate}
/>
