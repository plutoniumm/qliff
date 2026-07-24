<script lang="ts">
  // Log-log plot of LER vs physical rate p, one curve per code distance d. The
  // whole point is the CROSSING at the threshold p_th: below it larger d pushes
  // the LER down, above it larger d pushes it up. The curves are shared-wrapper
  // series; a draw hook adds the dashed vertical p_th marker, the dotted break-
  // even diagonal LER = p, and a d= label at the left edge of each curve.
  import { C, withAlpha } from "$lib/colors";
  import LinePlot, { type DrawKit, type PlotSeries } from "$lib/LinePlot.svelte";

  export interface Curve {
    d: number;
    color: string;
    points: { p: number; ler: number }[];
  }

  let {
    curves,
    pTh,
    pMin = 1e-3,
    pMax = 0.5,
    lerMin = 1e-6,
    lerMax = 1,
    height = 420,
    showBreakeven = true,
  }: {
    curves: Curve[];
    pTh: number;
    pMin?: number;
    pMax?: number;
    lerMin?: number;
    lerMax?: number;
    height?: number;
    showBreakeven?: boolean;
  } = $props();

  const clamp = (v: number): number => Math.max(lerMin, Math.min(lerMax, v));

  const plotSeries = $derived<PlotSeries[]>(
    curves.map((c) => ({
      pts: c.points
        .filter((pt) => pt.p >= pMin && pt.p <= pMax)
        .map((pt) => [pt.p, clamp(pt.ler)] as [number, number]),
      color: c.color,
      width: 2.4,
      label: `d=${c.d}`,
    })),
  );

  const annotate = $derived.by(() => {
    const crv = curves;
    const pth = pTh;
    const pmn = pMin;
    const pmx = pMax;
    const lmn = lerMin;
    const lmx = lerMax;
    const be = showBreakeven;

    return (k: DrawKit) => {
      const { ctx, x, y, bbox, color, pxr } = k;
      const cl = (v: number) => Math.max(lmn, Math.min(lmx, v));
      ctx.save();
      if (be) {
        ctx.beginPath();
        ctx.setLineDash([2 * pxr, 4 * pxr]);
        ctx.strokeStyle = color(withAlpha(C.muted, 0.55));
        ctx.lineWidth = 1.5 * pxr;
        ctx.moveTo(x(pmn), y(cl(pmn)));
        ctx.lineTo(x(pmx), y(cl(pmx)));
        ctx.stroke();
        ctx.setLineDash([]);
      }
      if (pth >= pmn && pth <= pmx) {
        const tx = x(pth);
        ctx.beginPath();
        ctx.setLineDash([5 * pxr, 4 * pxr]);
        ctx.strokeStyle = color(C.defect);
        ctx.lineWidth = 1.5 * pxr;
        ctx.moveTo(tx, bbox.top);
        ctx.lineTo(tx, bbox.top + bbox.height);
        ctx.stroke();
        ctx.setLineDash([]);
        const near = tx > bbox.left + bbox.width * 0.6;
        ctx.font = `bold ${11 * pxr}px ui-monospace, monospace`;
        ctx.fillStyle = color(C.defect);
        ctx.textAlign = near ? "right" : "left";
        ctx.textBaseline = "alphabetic";
        ctx.fillText("p_th = threshold (curves cross)", tx + (near ? -6 : 6) * pxr, bbox.top + 12 * pxr);
      }
      ctx.font = `bold ${12 * pxr}px ui-monospace, monospace`;
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      for (const c of crv) {
        const first = c.points.find((pt) => pt.p >= pmn);
        if (!first) {
          continue;
        }
        ctx.fillStyle = color(c.color);
        ctx.fillText(`d=${c.d}`, x(first.p) + 5 * pxr, y(cl(first.ler)) - 5 * pxr);
      }
      ctx.restore();
    };
  });
</script>

<LinePlot
  series={plotSeries}
  xScale="log"
  yScale="log"
  xRange={[pMin, pMax]}
  yRange={[lerMin, lerMax]}
  xLabel="physical error rate p (probability per qubit, log scale)"
  yLabel="logical error rate P_L (log scale)"
  {height}
  {annotate}
/>
