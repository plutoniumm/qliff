<script lang="ts">
  // Self-contained threshold-crossing figure: owns the p_th / prefactor sliders
  // and the distance chips, and builds one phenomenological LER(p,d) curve per
  // selected distance. The crossing at p_th emerges from the ceil(d/2) exponent.
  import Slider from "$lib/Slider.svelte";
  import { C } from "$lib/colors";
  import ThresholdPlot from "./ThresholdPlot.svelte";
  import { surfaceModelCurve } from "./model";

  let pTh = $state(0.1);
  let modelA = $state(0.5);
  let dSet = $state<number[]>([3, 5, 7, 9]);
  const distanceColors = [C.accent2, C.accent, C.accent3, C.defect, C.ok];
  const thPMin = 1e-3;
  const thPMax = 0.5;
  const thCurves = $derived(
    dSet.map((d, i) => ({
      d,
      color: distanceColors[i % distanceColors.length],
      points: surfaceModelCurve(d, pTh, modelA, thPMin, thPMax, 160),
    })),
  );
  function toggleD(d: number): void {
    dSet = dSet.includes(d)
      ? dSet.filter((x) => x !== d).sort((a, b) => a - b)
      : [...dSet, d].sort((a, b) => a - b);
  }
  const allD = [3, 5, 7, 9, 11];
</script>

<div class="prose-controls">
  <Slider bind:value={pTh} min={0.02} max={0.25} step={0.005} label="threshold p_th (model)" format={(v) => v.toFixed(3)} />
  <Slider bind:value={modelA} min={0.1} max={1.5} step={0.05} label="prefactor A (model)" format={(v) => v.toFixed(2)} />
</div>
<div class="dchips">
  <span class="dchips-lbl">distances:</span>
  {#each allD as d}
    <button
      class="chip"
      class:on={dSet.includes(d)}
      style="--cc:{distanceColors[Math.max(0, dSet.indexOf(d)) % distanceColors.length]}"
      onclick={() => toggleD(d)}
    >d={d}</button>
  {/each}
</div>
<ThresholdPlot curves={thCurves} {pTh} pMin={thPMin} pMax={thPMax} lerMin={1e-6} lerMax={1} />

<style>
  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }
  .dchips {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
  }
  .dchips-lbl {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .chip {
    font-family: var(--font-mono);
    font-size: 13px;
    padding: 5px 12px;
    opacity: 0.5;
  }
  .chip.on {
    opacity: 1;
    border-color: var(--cc);
    color: var(--cc);
    box-shadow: inset 0 0 0 1px var(--cc);
  }
</style>
