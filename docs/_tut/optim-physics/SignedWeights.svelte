<script lang="ts">
  // The signed quasiprobability importance estimator (estimate_chunk in
  // src/tableau.rs). For non-Pauli noise each trajectory picks ONE branch per
  // location with probability |w| / gamma, multiplies its weight by sign(w) * gamma,
  // and reads <O> on the final tableau. Every weight has the same magnitude Gamma =
  // prod gamma, so the whole payload is a sign; the estimate is mean(sign * <O>)
  // times Gamma. The ledger shows the per-location branch picks; the readout shows
  // the estimate converging to the truth with a noise floor that scales with Gamma.
  import Slider from "$lib/Slider.svelte";
  import { C, withAlpha } from "$lib/colors";
  import { location, runEstimate, type Kind } from "./model";

  let kind = $state<Kind>("AMPLITUDE_DAMP");
  let strength = $state(0.15);
  let count = $state(8);
  let shots = $state(4000);
  let truth = $state(0.3);
  let seed = $state(9);

  const loc = $derived(location(kind, strength));
  const run = $derived(runEstimate(loc, count, shots, truth, seed));
  const ledger = $derived(run.trajectories.slice(0, 8));

  function chip(p: string): string {
    if (p === "I") {
      return C.muted;
    }

    return p === "-" ? C.bad : C.ok;
  }
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
    min={0.02}
    max={0.4}
    step={0.01}
    label={kind === "RZ" ? "angle theta (rad)" : "damping p"}
    format={(v) => v.toFixed(2)}
  />
  <Slider bind:value={count} min={1} max={20} step={1} label="noise locations A" />
  <Slider bind:value={shots} min={500} max={20000} step={500} label="trajectories" />
  <Slider bind:value={truth} min={-1} max={1} step={0.05} label="true <O>" format={(v) => v.toFixed(2)} />
  <Slider bind:value={seed} min={1} max={40} step={1} label="seed" />
</div>

<div class="ledger">
  <div class="lhead mono">first 8 trajectories: branch pick per location, then the weight sign</div>
  {#each ledger as t, i (i)}
    <div class="lrow">
      <span class="picks">
        {#each t.picks as p, j (j)}
          <span class="chip" style="--c:{chip(p)}; --bgc:{withAlpha(chip(p), 0.2)}">{p}</span>
        {/each}
      </span>
      <span class="wt mono" style="color:{t.sign > 0 ? C.ok : C.bad}">
        {t.sign > 0 ? "+" : "-"}Gamma
      </span>
      <span class="obs mono">&lt;O&gt; = {t.obs > 0 ? "+1" : "-1"}</span>
    </div>
  {/each}
</div>

<div class="stat-strip">
  <span>gamma per location <b>{loc.gamma.toFixed(5)}</b></span>
  <span>Gamma = gamma^A <b style="color:{C.accent}">{run.gamma < 1e4 ? run.gamma.toFixed(4) : run.gamma.toExponential(2)}</b></span>
  <span>every |weight| <b>{run.gamma < 1e4 ? run.gamma.toFixed(4) : run.gamma.toExponential(2)}</b></span>
</div>
<div class="stat-strip">
  <span>estimate &lt;O&gt; <b style="color:{C.accent}">{run.estimate.toFixed(4)}</b></span>
  <span>+/- <b>{run.stderr.toFixed(4)}</b></span>
  <span>truth <b>{run.truth.toFixed(2)}</b></span>
</div>
<p class="note">
  Every trajectory weight is {run.gamma < 1e4 ? run.gamma.toFixed(3) : run.gamma.toExponential(1)} in
  magnitude; only the sign differs, set by how many negative fault branches (red chips) it hit. The
  estimate is that Gamma times the mean of sign times &lt;O&gt;, and its error bar carries the same
  Gamma factor -- which is why the noise floor climbs with the circuit even though the answer stays
  in [-1, 1]. The reset branch R of amplitude damping is opcode 9 in the core's branch stream.
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
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }

  .ledger {
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 12px 14px;
    overflow-x: auto;
  }

  .lhead {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 10px;
  }

  .lrow {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 3px 0;
    min-width: 460px;
  }

  .picks {
    display: flex;
    gap: 4px;
    flex: 1;
  }

  .chip {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 700;
    border-radius: 4px;
    border: 1px solid var(--c);
    color: var(--c);
    background: var(--bgc);
  }

  .wt {
    font-weight: 700;
    width: 4.5rem;
    text-align: right;
  }

  .obs {
    font-size: 12.5px;
    color: var(--muted);
    width: 6rem;
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
    margin: 12px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.55;
  }
</style>
