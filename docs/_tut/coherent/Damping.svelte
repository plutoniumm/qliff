<script lang="ts">
  // Section-06 cluster: amplitude damping. One loss-probability slider p drives BOTH
  // the damping figure (Bloch pull toward |0> + signed weight bars + ledger) AND the
  // negativity gamma(p) curve below it, whose marker tracks the same p. The two
  // figures share p, so they stay ONE island (the page's tightly-coupled cluster).
  import { C } from "$lib/colors";
  import Bloch from "./Bloch.svelte";
  import WeightBars from "./WeightBars.svelte";
  import Plot, { type Series } from "./Plot.svelte";
  import Range from "./Range.svelte";
  import { dampingBranches, totalWeight, gamma, dampingGamma } from "./channel";
  import { applyDamping, norm, type Vec3 } from "./bloch";

  const sgn = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(3);

  let pDamp = $state(0.3);
  const dampBranches = $derived(dampingBranches(pDamp));
  const dampSum = $derived(totalWeight(dampBranches));
  const dampGamma = $derived(gamma(dampBranches));

  // damping Bloch: pull a |+> state toward |0>.
  const dampBase: Vec3 = [1, 0, 0];
  const dampLive = $derived(applyDamping(pDamp, dampBase));

  const dampGammaCurve: Series[] = (() => {
    const exact: [number, number][] = [];
    const approx: [number, number][] = [];
    for (let i = 0; i <= 80; i++) {
      const p = i / 80;
      exact.push([p, dampingGamma(p)]);
      approx.push([p, 1 + p / 2]);
    }

    return [
      { pts: exact, color: C.accent, label: "γ exact" },
      { pts: approx, color: C.muted, label: "1 + p/2", dash: true },
    ];
  })();
</script>

<div class="panel">
  <div class="stage small">
    <Bloch vec={dampLive} label="amplitude damping on the Bloch sphere" />
  </div>
  <div class="controls">
    <WeightBars branches={dampBranches} max={1} height={200} />
    <Range bind:value={pDamp} min={0} max={0.99} step={0.01} label="loss probability p" format={(v) => v.toFixed(2)} />
    <div class="ledger mono">
      <span>q<sub>I</sub> = {sgn(dampBranches[0].weight)}</span>
      <span class="neg">q<sub>Z</sub> = {sgn(dampBranches[1].weight)}</span>
      <span>q<sub>R</sub> = {sgn(dampBranches[2].weight)}</span>
    </div>
    <div class="totals">
      <span>Σ q = <strong style="color:{C.ok}">{dampSum.toFixed(3)}</strong></span>
      <span>γ = <strong style="color:{C.accent}">{dampGamma.toFixed(3)}</strong></span>
      <span>|r| = <strong>{norm(dampLive).toFixed(3)}</strong> (state purity)</span>
    </div>
  </div>
</div>

<div class="plotwrap gammawrap">
  <Plot
    series={dampGammaCurve}
    xmin={0}
    xmax={1}
    ymin={1}
    ymax={1.8}
    marker={pDamp}
    xlabel="loss probability p"
    ylabel="γ"
    height={150}
  />
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

  .plotwrap {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .gammawrap {
    margin-top: 22px;
  }
</style>
