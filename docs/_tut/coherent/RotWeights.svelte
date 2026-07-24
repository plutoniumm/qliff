<script lang="ts">
  // Section-04 cluster: the signed quasiprobability mix for RZ(theta). One slider
  // drives BOTH the Bloch rotation and the signed weight bars, plus a live ledger of
  // the four branch weights and the running totals (sum w = 1, sum |w| = gamma).
  import { C } from "$lib/colors";
  import Bloch from "./Bloch.svelte";
  import WeightBars from "./WeightBars.svelte";
  import Range from "./Range.svelte";
  import { rotationBranches, totalWeight, gamma } from "./channel";
  import { applyRz, type Vec3 } from "./bloch";

  const fmtAngle = (v: number) => `${v.toFixed(2)} rad`;
  // print a signed weight, e.g. "+0.847" / "-0.077".
  const sgn = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(3);

  let thetaDec = $state(0.6);
  const rotBranches = $derived(rotationBranches(thetaDec));
  const rotSum = $derived(totalWeight(rotBranches));
  const rotGamma = $derived(gamma(rotBranches));
  const rotHasNeg = $derived(rotBranches.some((b) => b.weight < 0));

  // Bloch view for the decomposition: a |+> vector rotated by thetaDec.
  const decBase: Vec3 = [1, 0, 0];
  const decLive = $derived(applyRz(thetaDec, decBase));
</script>

<div class="panel">
  <div class="stage small">
    <Bloch vec={decLive} ghost={decBase} sweep={thetaDec} label="RZ rotation on the Bloch sphere" />
  </div>
  <div class="controls">
    <WeightBars branches={rotBranches} max={1.2} height={210} />
    <Range bind:value={thetaDec} min={0} max={2 * Math.PI} step={0.01} label="rotation angle θ" format={fmtAngle} />
    <div class="ledger mono">
      <span>w<sub>I</sub> = {sgn(rotBranches[0].weight)}</span>
      <span class:neg={rotBranches[1].weight < 0}>w<sub>Z</sub> = {sgn(rotBranches[1].weight)}</span>
      <span class:neg={rotBranches[2].weight < 0}>w<sub>S</sub> = {sgn(rotBranches[2].weight)}</span>
      <span class:neg={rotBranches[3].weight < 0}>w<sub>S†</sub> = {sgn(rotBranches[3].weight)}</span>
    </div>
    <div class="totals">
      <span>Σ w = <strong style="color:{C.ok}">{rotSum.toFixed(3)}</strong> (always 1)</span>
      <span>Σ |w| = γ = <strong style="color:{rotHasNeg ? C.bad : C.fg}">{rotGamma.toFixed(3)}</strong></span>
    </div>
  </div>
</div>

<style>
  .panel {
    display: grid;
    grid-template-columns: minmax(280px, 1fr) minmax(300px, 1fr);
    gap: 22px;
    align-items: center;
  }

  @media (max-width: 760px) {
    .panel {
      grid-template-columns: 1fr;
    }
  }

  .stage {
    height: 360px;
    max-height: 50vh;
    border-radius: var(--r-md);
    background:
      radial-gradient(120% 120% at 50% 0%, color-mix(in srgb, var(--accent) 8%, transparent), transparent 70%);
  }

  .stage.small {
    height: 320px;
  }

  .controls {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .ledger {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    font-size: 13px;
    color: var(--fg);
  }

  .ledger .neg {
    color: var(--bad);
  }

  .totals {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
    font-size: 13px;
    color: var(--muted);
    padding-top: 4px;
    border-top: 1px solid var(--line);
  }
</style>
