<script lang="ts">
  // Where the answer actually lives. Two distributions over the fault count k,
  // side by side: mass[k], the EXACT signed quasiprobability mass of the stratum
  // (the coefficients of x^k in prod(a_i + b_i x), computed, never sampled), and
  // P(k), the Poisson-binomial the |.|/gamma sampler actually draws from. Their
  // ratio is Gamma times the stratum's mean trajectory sign, which is the third
  // column -- the same identity the self-normalised estimator divides out.
  import Slider from "$lib/Slider.svelte";
  import { C } from "$lib/colors";
  import {
    location,
    massCutoff,
    meanSign,
    samplingPk,
    strataMass,
    totalGamma,
    type Kind,
  } from "./model";

  let kind = $state<Kind>("AMPLITUDE_DAMP");
  let strength = $state(0.05);
  let count = $state(9);

  const loc = $derived(location(kind, strength));
  const mass = $derived(strataMass(loc, count));
  const pk = $derived(samplingPk(loc, count));
  const bigGamma = $derived(totalGamma(loc, count));
  const rows = $derived(Math.min(massCutoff(mass, 0.9999), 13, mass.length));
  const scale = $derived(
    Math.max(...mass.slice(0, rows).map((m) => Math.abs(m)), ...pk.slice(0, rows), 1e-12),
  );
  const massSum = $derived(mass.reduce((s, m) => s + m, 0));
  const shown = $derived(mass.slice(0, rows).reduce((s, m) => s + Math.abs(m), 0));
</script>

<div class="ctl-row">
  <button class:active={kind === "AMPLITUDE_DAMP"} onclick={() => (kind = "AMPLITUDE_DAMP")}>
    amplitude damping
  </button>
  <button class:active={kind === "RZ"} onclick={() => (kind = "RZ")}>coherent RZ</button>
</div>
<div class="prose-controls">
  <Slider
    bind:value={strength}
    min={0.01}
    max={0.3}
    step={0.005}
    label={kind === "RZ" ? "angle θ (rad)" : "damping p"}
    format={(v) => v.toFixed(3)}
  />
  <Slider bind:value={count} min={1} max={60} step={1} label="noise locations A" />
</div>

<div class="scroll">
  <div class="grid">
    <span class="head">k</span>
    <span class="head">mass[k] (exact, signed)</span>
    <span class="head num">value</span>
    <span class="head">P(k) sampled</span>
    <span class="head num">value</span>
    <span class="head num">mean sign</span>
    {#each mass.slice(0, rows) as m, k (k)}
      <span class="klbl mono">{k}</span>
      <span class="track">
        <i style="width:{(Math.abs(m) / scale) * 100}%; background:{m < 0 ? C.bad : C.accent}"></i>
      </span>
      <span class="num mono" style="color:{m < 0 ? C.bad : C.fg}">{m.toFixed(6)}</span>
      <span class="track">
        <i style="width:{(pk[k] / scale) * 100}%; background:{C.muted}"></i>
      </span>
      <span class="num mono">{pk[k].toFixed(6)}</span>
      <span class="num mono">{meanSign(loc, k).toFixed(4)}</span>
    {/each}
  </div>
</div>

<div class="stat-strip">
  <span>Γ <b>{bigGamma < 1e5 ? bigGamma.toFixed(4) : bigGamma.toExponential(2)}</b></span>
  <span>Σ mass[k] <b>{massSum.toFixed(6)}</b></span>
  <span>|mass| shown <b>{(shown * 100).toFixed(3)}%</b></span>
  <span>mass at k = 0 <b style="color:{C.accent}">{(mass[0] * 100).toFixed(2)}%</b></span>
</div>
<p class="note">
  mass[k] divided by Γ · P(k) is the stratum's mean trajectory sign, the last column. The masses
  sum to 1 by trace preservation, whatever the channel; the k = 0 stratum holds exactly one
  trajectory, so its share of the answer costs one shot.
</p>

<style>
  .ctl-row {
    display: flex;
    gap: 10px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }

  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }

  .scroll {
    overflow-x: auto;
  }

  .grid {
    display: grid;
    grid-template-columns: 2.2rem minmax(90px, 1fr) 6.2rem minmax(90px, 1fr) 6.2rem 5rem;
    align-items: center;
    gap: 5px 10px;
    min-width: 560px;
  }

  .head {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    padding-bottom: 4px;
    border-bottom: 1px solid var(--line);
  }

  .klbl {
    font-size: 13px;
    color: var(--muted);
    text-align: right;
  }

  .track {
    height: 0.8rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--line) 55%, transparent);
    overflow: hidden;
  }

  .track > i {
    display: block;
    height: 100%;
    border-radius: inherit;
  }

  .num {
    font-size: 12.5px;
    text-align: right;
  }

  .stat-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin-top: 16px;
    font-size: 14px;
    color: var(--muted);
  }

  .stat-strip b {
    color: var(--fg);
    font-family: var(--font-mono);
    font-weight: 700;
  }

  .note {
    margin: 8px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.5;
  }
</style>
