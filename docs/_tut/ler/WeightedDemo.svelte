<script lang="ts">
  // Self-contained coherent-noise shot-cost figure: owns the p/gamma/N/seed
  // sliders, the importance-weighted estimate, and the Pauli-vs-coherent shot
  // budget bars. Weighted variance scales like gamma^2, so the budget balloons.
  import Slider from "$lib/Slider.svelte";
  import { C } from "$lib/colors";
  import { repCodeLER, weightedMonteCarlo } from "./model";

  let wP = $state(0.05);
  let wGamma = $state(2.0);
  let wN = $state(4000);
  let wSeed = $state(3);
  const wTruth = $derived(repCodeLER(wP, 5));
  const wResult = $derived(weightedMonteCarlo(wTruth, wGamma, wN, wSeed));
  // shots needed to reach a target relative error, binomial vs weighted
  const targetRel = 0.1; // 10% relative error bar
  const binomShotsNeeded = $derived(
    wTruth > 0 ? Math.ceil((1 - wTruth) / (wTruth * targetRel * targetRel)) : 0,
  );
  // weighted variance ~ gamma^2 * trueLER, so shots scale by ~gamma^2
  const weightedShotsNeeded = $derived(Math.ceil(binomShotsNeeded * wGamma * wGamma));

  function pct(v: number): string {
    return `${(v * 100).toFixed(2)}%`;
  }
</script>

<div class="prose-controls">
  <Slider bind:value={wP} min={0.01} max={0.2} step={0.005} label="underlying p" format={(v) => v.toFixed(3)} />
  <Slider bind:value={wGamma} min={1} max={6} step={0.1} label="negativity γ" format={(v) => v.toFixed(1)} />
  <Slider bind:value={wN} min={200} max={40000} step={200} label="shots N" />
  <Slider bind:value={wSeed} min={1} max={40} step={1} label="seed" />
</div>
<div class="stat-strip">
  <span>true LER <b>{pct(wTruth)}</b></span>
  <span>weighted estimate <b style="color:{C.accent}">{pct(wResult.ler)}</b></span>
  <span>± stderr <b style="color:{wGamma > 2.5 ? C.bad : C.fg}">{pct(wResult.stderr)}</b></span>
</div>
<div class="cost">
  <div class="cost-bar">
    <span class="cost-lbl">Pauli (binomial)</span>
    <div class="bar"><div class="fill" style="width:{Math.min(100, (binomShotsNeeded / weightedShotsNeeded) * 100)}%; background:{C.ok}"></div></div>
    <span class="mono cost-n">{binomShotsNeeded.toLocaleString()} shots</span>
  </div>
  <div class="cost-bar">
    <span class="cost-lbl">coherent (γ={wGamma.toFixed(1)})</span>
    <div class="bar"><div class="fill" style="width:100%; background:{C.accent3}"></div></div>
    <span class="mono cost-n">{weightedShotsNeeded.toLocaleString()} shots</span>
  </div>
  <p class="cost-note">
    Shots to reach a 10% relative error bar. Weighted variance scales like
    γ², so the budget grows roughly γ²-fold.
  </p>
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
  .cost {
    margin-top: 18px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .cost-bar {
    display: grid;
    grid-template-columns: 150px 1fr auto;
    align-items: center;
    gap: 12px;
  }
  .cost-lbl {
    font-size: 13px;
    color: var(--muted);
  }
  .bar {
    height: 12px;
    border-radius: 99px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    border-radius: 99px;
    transition: width var(--dur) var(--ease-out);
  }
  .cost-n {
    font-size: 12.5px;
    color: var(--fg);
    white-space: nowrap;
  }
  .cost-note {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.5;
  }
  .mono {
    font-family: var(--font-mono);
  }
</style>
