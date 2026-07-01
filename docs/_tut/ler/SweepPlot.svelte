<script lang="ts">
  // A sweep of LER vs p for ONE code: a smooth analytic curve plus seeded
  // Monte-Carlo points with binomial error bars (the real (p, ler, stderr)
  // triples that qliff's `sweep` yields). Log y-axis so sub-threshold suppression
  // is visible; linear x in p. The curve is a shared-wrapper series; a draw hook
  // adds the MC points and their +/- stderr error-bar caps.
  import { C, withAlpha } from "$lib/colors";
  import LinePlot, { type DrawKit, type PlotSeries } from "$shared/LinePlot.svelte";

  export interface MCPoint {
    p: number;
    ler: number;
    stderr: number;
  }

  let {
    curve,
    points,
    pMin,
    pMax,
    lerMin = 1e-5,
    lerMax = 1,
    height = 380,
  }: {
    curve: { p: number; ler: number }[];
    points: MCPoint[];
    pMin: number;
    pMax: number;
    lerMin?: number;
    lerMax?: number;
    height?: number;
  } = $props();

  const clamp = (v: number): number => Math.max(lerMin, Math.min(lerMax, v));

  const plotSeries = $derived<PlotSeries[]>([
    {
      pts: curve
        .filter((pt) => pt.p >= pMin && pt.p <= pMax)
        .map((pt) => [pt.p, clamp(pt.ler)] as [number, number]),
      color: withAlpha(C.accent2, 0.85),
      width: 2.2,
    },
  ]);

  const annotate = $derived.by(() => {
    const pts = points;
    const lo = lerMin;
    const hi = lerMax;

    return (k: DrawKit) => {
      const { ctx, x, y, color, pxr } = k;
      const cl = (v: number) => Math.max(lo, Math.min(hi, v));
      const accent = color(C.accent);
      const bg = color(C.bg);
      ctx.save();
      ctx.strokeStyle = accent;
      ctx.lineWidth = 1.5 * pxr;
      for (const pt of pts) {
        const px = x(pt.p);
        const yhi = y(cl(pt.ler + pt.stderr));
        const ylo = y(cl(pt.ler - pt.stderr));
        ctx.beginPath();
        ctx.moveTo(px, yhi);
        ctx.lineTo(px, ylo);
        ctx.moveTo(px - 4 * pxr, yhi);
        ctx.lineTo(px + 4 * pxr, yhi);
        ctx.moveTo(px - 4 * pxr, ylo);
        ctx.lineTo(px + 4 * pxr, ylo);
        ctx.stroke();
      }
      for (const pt of pts) {
        ctx.beginPath();
        ctx.arc(x(pt.p), y(cl(pt.ler)), 3.4 * pxr, 0, Math.PI * 2);
        ctx.fillStyle = accent;
        ctx.fill();
        ctx.lineWidth = 1 * pxr;
        ctx.strokeStyle = bg;
        ctx.stroke();
      }
      ctx.restore();
    };
  });
</script>

<LinePlot
  series={plotSeries}
  xScale="lin"
  yScale="log"
  xRange={[pMin, pMax]}
  yRange={[lerMin, lerMax]}
  xLabel="physical error rate p (probability per bit)"
  yLabel="logical error rate P_L (log scale)"
  xFmt={(v) => v.toFixed(3)}
  {height}
  {annotate}
/>
