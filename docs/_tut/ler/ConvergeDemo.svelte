<script lang="ts">
  // Self-contained Monte-Carlo convergence figure: owns the p/d/N/seed sliders,
  // the derived exact LER + seeded estimate + running trace, and the stat strip.
  // All curves are $derived so no $effect ever writes the state it reads.
  import Slider from "$lib/Slider.svelte";
  import { C } from "$lib/colors";
  import ConvergePlot from "./ConvergePlot.svelte";
  import { repCodeLER, repCodeMonteCarlo, repCodeTrace } from "./model";

  let mcP = $state(0.08);
  let mcD = $state(5);
  let mcN = $state(2000);
  let mcSeed = $state(1);
  const mcTruth = $derived(repCodeLER(mcP, mcD));
  const mcResult = $derived(repCodeMonteCarlo(mcP, mcD, mcN, mcSeed));
  const mcTrace = $derived(
    repCodeTrace(mcP, mcD, mcN, mcSeed, Math.max(1, Math.floor(mcN / 120))),
  );

  function pct(v: number): string {
    return `${(v * 100).toFixed(2)}%`;
  }
</script>

<div class="prose-controls">
  <Slider bind:value={mcP} min={0.01} max={0.3} step={0.005} label="physical error p" format={(v) => v.toFixed(3)} />
  <Slider bind:value={mcD} min={3} max={11} step={2} label="code distance d" />
  <Slider bind:value={mcN} min={50} max={20000} step={50} label="shots N" />
  <Slider bind:value={mcSeed} min={1} max={40} step={1} label="seed" />
</div>
<ConvergePlot trace={mcTrace} truth={mcTruth} maxN={mcN} />
<div class="stat-strip">
  <span>exact LER <b>{pct(mcTruth)}</b></span>
  <span>estimate <b style="color:{C.accent}">{pct(mcResult.ler)}</b></span>
  <span>± stderr <b>{pct(mcResult.stderr)}</b></span>
  <span>errors seen <b>{mcResult.errors}</b> / {mcResult.shots}</span>
</div>

<style>
  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }
  .stat-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin-top: 14px;
    font-size: 14px;
    color: var(--muted);
  }
  .stat-strip b {
    color: var(--fg);
    font-family: var(--font-mono);
    font-weight: 700;
  }
</style>
