<script lang="ts">
  // Live LER plot. Physical error rate p on the (linear) x-axis, logical error
  // rate on a log10 y-axis, with a shaded +/- one-stderr band. Points stream in
  // during a run. This is now a thin adapter over the shared uPlot wrapper -- it
  // just shapes the run points into a banded series and passes an explicit color.
  import LinePlot, { type PlotSeries } from "$shared/LinePlot.svelte";
  import type { LerPoint } from "$lib/schema";

  interface Props {
    points: LerPoint[];
  }

  let { points }: Props = $props();

  // Non-positive LER / band edges are NaN so they drop out of the log axis.
  const plotSeries = $derived.by<PlotSeries[]>(() => {
    const sorted = [...points].sort((a, b) => a.p - b.p);

    return [
      {
        pts: sorted.map((q) => [q.p, q.ler > 0 ? q.ler : NaN] as [number, number]),
        color: "#8b6cff",
        label: "LER",
        width: 2,
        showPoints: true,
        band: {
          lo: sorted.map((q) => (q.ler - q.stderr > 0 ? q.ler - q.stderr : NaN)),
          hi: sorted.map((q) => (q.ler + q.stderr > 0 ? q.ler + q.stderr : NaN)),
        },
        bandColor: "rgba(139, 108, 255, 0.16)",
      },
    ];
  });
</script>

<div class="plot-wrap">
  <LinePlot
    series={plotSeries}
    xScale="lin"
    yScale="log"
    xLabel="physical error rate p"
    yLabel="logical error rate"
    height={320}
    legend={true}
  />
  {#if points.length === 0}
    <p class="empty">No data yet — configure noise + run parameters and hit Run.</p>
  {/if}
</div>

<style>
  .plot-wrap {
    position: relative;
  }
  .empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 13px;
    pointer-events: none;
  }
</style>
