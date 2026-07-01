<script lang="ts">
  // Watch a Monte-Carlo estimate of the LER converge as shots accumulate. The
  // running estimate (a seeded trace) jitters around the true value; the shaded
  // +/- stderr band narrows like 1/sqrt(N). x-axis is log in N so the 1/sqrt(N)
  // shrink reads as a steady taper. The line + band are a shared-wrapper series;
  // a draw hook adds the "true LER" reference line.
  import { C } from "$lib/colors";
  import LinePlot, { type DrawKit, type PlotSeries } from "$shared/LinePlot.svelte";

  let {
    trace,
    truth,
    maxN,
    height = 320,
  }: {
    trace: { n: number; ler: number; stderr: number }[];
    truth: number;
    maxN: number;
    height?: number;
  } = $props();

  // y-range: pad around the true value and the trace spread.
  const yMax = $derived(
    Math.max(truth * 2.2, ...trace.map((t) => t.ler + t.stderr), truth + 1e-9) * 1.05,
  );

  // Running estimate as one line with a +/- stderr band (lo clamped at 0 for the
  // linear y-axis). N is pinned at >= 1 so the log x-axis has no zero.
  const plotSeries = $derived<PlotSeries[]>([
    {
      pts: trace.map((t) => [Math.max(1, t.n), t.ler] as [number, number]),
      color: C.accent,
      width: 2,
      band: {
        lo: trace.map((t) => Math.max(0, t.ler - t.stderr)),
        hi: trace.map((t) => t.ler + t.stderr),
      },
    },
  ]);

  const annotate = $derived.by(() => {
    const tr = trace;
    const tru = truth;

    return (k: DrawKit) => {
      const { ctx, x, y, bbox, color, pxr } = k;
      ctx.save();
      const ty = y(tru);
      ctx.beginPath();
      ctx.setLineDash([6 * pxr, 4 * pxr]);
      ctx.strokeStyle = color(C.ok);
      ctx.lineWidth = 1.6 * pxr;
      ctx.moveTo(bbox.left, ty);
      ctx.lineTo(bbox.left + bbox.width, ty);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = `bold ${11 * pxr}px ui-monospace, monospace`;
      ctx.textAlign = "right";
      ctx.textBaseline = "alphabetic";
      ctx.fillStyle = color(C.ok);
      ctx.fillText("true LER", bbox.left + bbox.width - 4 * pxr, ty - 6 * pxr);
      if (tr.length > 1) {
        const last = tr[tr.length - 1];
        ctx.fillStyle = color(C.accent);
        ctx.fillText("±1σ band", x(Math.max(1, last.n)) - 6 * pxr, y(last.ler + last.stderr) - 5 * pxr);
      }
      ctx.restore();
    };
  });
</script>

<LinePlot
  series={plotSeries}
  xScale="log"
  yScale="lin"
  xRange={[1, maxN]}
  yRange={[0, yMax]}
  xLabel="shots N (log scale, dimensionless count)"
  yLabel="LER estimate (% of shots)"
  yFmt={(v) => `${(v * 100).toFixed(2)}%`}
  {height}
  {annotate}
/>
