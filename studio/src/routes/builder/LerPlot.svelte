<script lang="ts">
  // Live LER plot. Physical error rate p on the (linear) x-axis, logical error
  // rate on a log10 y-axis. A shaded band shows +/- one stderr around each LER.
  // Points stream in during a run; we rebuild the uPlot series each update
  // (point counts are small, so this is cheap and avoids partial-update bugs).
  import { onMount, onDestroy } from "svelte";
  import uPlot from "uplot";
  import "uplot/dist/uPlot.min.css";
  import type { LerPoint } from "$lib/schema";

  interface Props {
    points: LerPoint[];
  }

  let { points }: Props = $props();

  let host: HTMLDivElement | null = $state(null);
  let plot: uPlot | null = null;

  function dataFromPoints(pts: LerPoint[]): uPlot.AlignedData {
    const sorted = [...pts].sort((a, b) => a.p - b.p);
    const xs = sorted.map((q) => q.p);
    const ler = sorted.map((q) => (q.ler > 0 ? q.ler : NaN));
    const lo = sorted.map((q) =>
      q.ler - q.stderr > 0 ? q.ler - q.stderr : NaN,
    );
    const hi = sorted.map((q) => (q.ler + q.stderr > 0 ? q.ler + q.stderr : NaN));

    return [xs, lo, hi, ler];
  }

  function makeOpts(width: number): uPlot.Options {
    return {
      width,
      height: 320,
      scales: {
        x: { time: false },
        y: { distr: 3 }, // log scale
      },
      axes: [
        {
          label: "physical error rate p",
          stroke: "#98a2c0",
          grid: { stroke: "rgba(150, 170, 235, 0.16)" },
          ticks: { stroke: "rgba(150, 170, 235, 0.16)" },
        },
        {
          label: "logical error rate",
          stroke: "#98a2c0",
          grid: { stroke: "rgba(150, 170, 235, 0.16)" },
          ticks: { stroke: "rgba(150, 170, 235, 0.16)" },
        },
      ],
      series: [
        {},
        {
          label: "−σ",
          stroke: "transparent",
          fill: "rgba(139, 108, 255, 0.16)",
          points: { show: false },
        },
        {
          label: "+σ",
          stroke: "transparent",
          fill: "rgba(139, 108, 255, 0.16)",
          points: { show: false },
        },
        {
          label: "LER",
          stroke: "#8b6cff",
          width: 2,
          points: {
            show: true,
            size: 6,
            stroke: "#8b6cff",
            fill: "#8b6cff",
          },
        },
      ],
      // Band fills between the −σ (series 1) and +σ (series 2) lines.
      bands: [{ series: [1, 2], fill: "rgba(139, 108, 255, 0.16)" }],
      legend: { show: true },
    };
  }

  onMount(() => {
    if (host === null) {
      return;
    }

    const width = host.clientWidth || 600;
    plot = new uPlot(makeOpts(width), dataFromPoints(points), host);
  });

  onDestroy(() => {
    plot?.destroy();
    plot = null;
  });

  // Push new data whenever the points prop changes.
  $effect(() => {
    if (plot !== null) {
      plot.setData(dataFromPoints(points));
    }
  });
</script>

<div class="plot-wrap">
  <div class="plot-host" bind:this={host}></div>
  {#if points.length === 0}
    <p class="empty">No data yet — configure noise + run parameters and hit Run.</p>
  {/if}
</div>

<style>
  .plot-wrap {
    position: relative;
  }
  .plot-host {
    width: 100%;
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
  /* keep uPlot legend/axes legible on the dark theme */
  .plot-wrap :global(.u-legend) {
    color: var(--fg);
    font-size: 12px;
  }
</style>
