<script lang="ts">
  // Self-contained LER-vs-p sweep for one distance: owns the d/shots/seed sliders,
  // the analytic curve, and nine seeded Monte-Carlo points with binomial
  // error bars -- the (p, ler, stderr) triples qliff's sweep yields.
  import Slider from "$lib/Slider.svelte";
  import SweepPlot from "./SweepPlot.svelte";
  import { repCodeCurve, repCodeMonteCarlo } from "./model";

  let swD = $state(5);
  let swShots = $state(3000);
  let swSeed = $state(11);
  const swPMin = 0.01;
  const swPMax = 0.18;
  const swCurve = $derived(repCodeCurve(swD, swPMin, swPMax, 120, false));
  const swPoints = $derived(
    Array.from({ length: 9 }, (_, i) => {
      const p = swPMin + ((swPMax - swPMin) * i) / 8;
      const mc = repCodeMonteCarlo(p, swD, swShots, swSeed + i);

      return { p, ler: mc.ler, stderr: mc.stderr };
    }),
  );
</script>

<div class="prose-controls">
  <Slider bind:value={swD} min={3} max={11} step={2} label="code distance d" />
  <Slider
    bind:value={swShots}
    min={200}
    max={20000}
    step={200}
    label="shots per point"
  />
  <Slider bind:value={swSeed} min={1} max={40} step={1} label="seed" />
</div>
<SweepPlot curve={swCurve} points={swPoints} pMin={swPMin} pMax={swPMax} />

<style>
  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }
</style>
