<script lang="ts">
  // What survives self-normalisation: the signs. Inside one stratum every
  // trajectory carries the same weight MAGNITUDE, so the estimate of the stratum's
  // conditional error rate is the ratio sum(sign * wrong) / sum(sign). Draw the
  // stratum here and watch that ratio: stable while the signs lean one way, wild
  // once they cancel. The mean sign is r^k exactly, r = b / gfault per faulty
  // location, so raising the fault count k walks the stratum toward the cliff.
  import Slider from "$lib/Slider.svelte";
  import { C, withAlpha } from "$lib/colors";
  import { location, meanSign, sampleStratum } from "./model";

  let strength = $state(0.05);
  let faults = $state(2);
  let shots = $state(120);
  let failRate = $state(0.25);
  let seed = $state(11);

  const loc = $derived(location("AMPLITUDE_DAMP", strength));
  const expected = $derived(meanSign(loc, faults));
  const tally = $derived(sampleStratum(loc.r, faults, shots, failRate, seed));
  const observed = $derived(shots > 0 ? tally.signSum / shots : 0);
  // A stratum is uninformative when its signed total is within sampling noise of
  // zero: the ratio's denominator is then a small difference of large tallies.
  const fragile = $derived(Math.abs(tally.signSum) < Math.sqrt(shots));
</script>

<div class="prose-controls">
  <Slider
    bind:value={strength}
    min={0.01}
    max={0.5}
    step={0.005}
    label="damping p"
    format={(v) => v.toFixed(3)}
  />
  <Slider bind:value={faults} min={0} max={14} step={1} label="fault count k" />
  <Slider bind:value={shots} min={10} max={240} step={10} label="trajectories in stratum" />
  <Slider
    bind:value={failRate}
    min={0}
    max={1}
    step={0.05}
    label="true F_k"
    format={(v) => v.toFixed(2)}
  />
  <Slider bind:value={seed} min={1} max={60} step={1} label="seed" />
</div>

<div class="cells">
  {#each tally.signs as s, i (i)}
    <span
      class="cell"
      class:wrong={tally.wrong[i]}
      style="--c:{s > 0 ? C.ok : C.bad}; --bgc:{withAlpha(s > 0 ? C.ok : C.bad, 0.16)}"
      title={`trajectory ${i + 1}: sign ${s > 0 ? "+1" : "-1"}, ${tally.wrong[i] ? "logical error" : "decoded ok"}`}
    >{s > 0 ? "+" : "-"}</span>
  {/each}
</div>

<div class="stat-strip">
  <span>signs <b style="color:{C.ok}">{tally.plus} plus</b> / <b style="color:{C.bad}">{tally.minus} minus</b></span>
  <span>sum(sign) <b class:bad={fragile}>{tally.signSum}</b></span>
  <span>sum(sign · wrong) <b>{tally.hitSum}</b></span>
  <span>
    ratio estimate of F<sub>k</sub>
    <b style="color:{C.accent}">{tally.fHat === null ? "undefined" : tally.fHat.toFixed(3)}</b>
  </span>
  <span>± <b>{tally.stderr === null ? "--" : tally.stderr.toFixed(3)}</b></span>
</div>
<div class="stat-strip">
  <span>per-fault mean sign r <b>{loc.r.toFixed(4)}</b></span>
  <span>expected mean sign r<sup>k</sup> <b>{expected.toFixed(4)}</b></span>
  <span>measured mean sign <b>{observed.toFixed(4)}</b></span>
</div>

{#if tally.fHat === null}
  <p class="warn">
    The signs cancelled exactly: sum(sign) = 0, the ratio has no denominator, and qliff skips this
    stratum for the round. Its mass is simply missing from that estimate.
  </p>
{:else if fragile}
  <p class="warn">
    sum(sign) is inside the sampling noise of zero, so the ratio is a small difference of large
    tallies: the estimate is technically defined and practically worthless. Either spend more
    trajectories here or accept that this stratum carries no information.
  </p>
{:else}
  <p class="note">
    The signs lean one way, so the denominator is well away from zero and the ratio tracks the true
    F<sub>k</sub> = {failRate.toFixed(2)}. Notice that Γ appears nowhere in this readout: it
    divided out of numerator and denominator before any number was formed.
  </p>
{/if}

<style>
  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }

  .cells {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    max-width: 760px;
    margin-inline: auto;
  }

  .cell {
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 700;
    border-radius: 5px;
    border: 1.5px solid var(--c);
    color: var(--c);
    background: transparent;
  }

  .cell.wrong {
    background: var(--bgc);
    box-shadow: inset 0 0 0 2px var(--bgc);
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

  .stat-strip b.bad {
    color: var(--bad);
  }

  .note,
  .warn {
    margin: 12px 0 0;
    font-size: 13px;
    line-height: 1.55;
    color: var(--faint);
  }

  .warn {
    color: var(--bad);
  }
</style>
