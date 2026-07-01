<script lang="ts">
  // Section 5 island -- greedy pairwise contraction of the live code. Scrub the
  // merge order: each step joins two tensors over their shared legs; the running
  // "tensors left" and "largest intermediate" track the cost, and the final
  // tensor is the per-class weight whose argmax is the correction. Flip detector
  // buttons to re-pin the syndrome. Self-contained: owns its own distance / p /
  // syndrome / scrub state (was coupled to the factor-graph figure in the old
  // page component), all derived -- no $effect writes back into shared state.
  import TnSlider from "./TnSlider.svelte";
  import TnScrubber from "./TnScrubber.svelte";
  import { C } from "$lib/colors";
  import { repetitionDem, buildFactorGraph, decode, minWeightPick, type Dem } from "./decoder";

  let dataQubits = $state(4); // distance of the live code
  let p = $state(0.15); // physical error probability
  const demLive: Dem = $derived(repetitionDem(dataQubits, p));
  const fgLive = $derived(buildFactorGraph(demLive));
  let synLive = $state<number[]>([1, 0, 0]);

  // length-fit the syndrome to the current distance with a pure derived (no effect).
  const synFitted = $derived.by(() => {
    const n = demLive.numDetectors;
    const out = new Array<number>(n).fill(0);
    for (let i = 0; i < Math.min(n, synLive.length); i += 1) {
      out[i] = synLive[i] & 1;
    }

    return out;
  });

  const detIndices = $derived(
    Array.from({ length: demLive.numDetectors }, (_, i) => i),
  );
  const decoded = $derived(decode(demLive, fgLive, synFitted));
  const mwLive = $derived(minWeightPick(demLive, synFitted));

  function bitsToClass(bits: number[]): number {
    return bits.reduce((acc, b) => (acc << 1) | b, 0);
  }

  const liveDisagree = $derived(
    mwLive.logical !== null && mwLive.logical !== bitsToClass(decoded.prediction),
  );

  // contraction scrubber over the greedy steps.
  let contractStep = $state(0);
  const nSteps = $derived(decoded.steps.length);
  const stepClamped = $derived(Math.min(contractStep, nSteps));

  // a description of the network state after `stepClamped` merges.
  const tensorsRemaining = $derived.by(() => {
    if (stepClamped === 0) {
      // initial count: copies (nonzero legs) + observables + detectors.
      const copies = fgLive.copies.filter((c) => c.legs.length > 0).length;

      return copies + fgLive.observables.length + fgLive.detectors.length;
    }

    return decoded.steps[stepClamped - 1].workRanksAfter.length;
  });
  const currentMaxRank = $derived.by(() => {
    if (stepClamped === 0) {
      return Math.max(
        ...fgLive.copies.map((c) => c.legs.length),
        ...fgLive.detectors.map((d) => d.legs.length),
        ...fgLive.observables.map((o) => o.legs.length + 1),
        0,
      );
    }

    return decoded.steps[stepClamped - 1].maxRank;
  });
  const stepInfo = $derived(stepClamped > 0 ? decoded.steps[stepClamped - 1] : null);

  function setSynLive(d: number): void {
    const next = synFitted.slice();
    next[d] = next[d] ? 0 : 1;
    synLive = next;
  }

  function classLabel(c: number): string {
    return c === 0 ? "I (no logical flip)" : "L (logical flip)";
  }
</script>

<div class="ctrl-row">
  <TnSlider bind:value={dataQubits} min={3} max={6} step={1} label="code distance (data qubits)" />
  <TnSlider bind:value={p} min={0.02} max={0.45} step={0.01} label="physical error p" />
</div>

<div class="ctrl-row">
  {#each detIndices as d (d)}
    <button class="syn-btn" class:lit={synFitted[d] === 1} onclick={() => setSynLive(d)}
      >flip det {d}</button
    >
  {/each}
  <span class="mono syn-read">syndrome = ({synFitted.join(", ")})</span>
</div>

<TnScrubber bind:value={contractStep} min={0} max={nSteps} label="merge" />

<div class="contract-stats">
  <div class="stat">
    <div class="stat-k mono">tensors left</div>
    <div class="stat-v">{tensorsRemaining}</div>
  </div>
  <div class="stat">
    <div class="stat-k mono">largest intermediate</div>
    <div class="stat-v">
      {currentMaxRank} legs = 2<sup>{currentMaxRank}</sup> = {2 ** currentMaxRank} entries
    </div>
  </div>
  <div class="stat">
    <div class="stat-k mono">this merge</div>
    <div class="stat-v">
      {#if stepInfo}
        sum over {stepInfo.sharedLegs.length} leg{stepInfo.sharedLegs.length === 1 ? "" : "s"} →
        rank {stepInfo.resultRank}
      {:else}
        -- (start)
      {/if}
    </div>
  </div>
</div>

{#if stepClamped === nSteps}
  <div class="result">
    <div class="result-title mono">per-class weights → argmax</div>
    <div class="class-bars">
      {#each decoded.classWeights as w, k}
        {@const total = decoded.classWeights.reduce((s, x) => s + x, 0) || 1}
        {@const win = k === bitsToClass(decoded.prediction)}
        <div class="cbar" class:win>
          <div class="cbar-name mono" style="color:{k === 0 ? C.ok : C.accent3}">
            {classLabel(k)}{win ? "  ◀ argmax" : ""}
          </div>
          <div class="cbar-track">
            <div
              class="cbar-fill"
              style="width:{((w / total) * 100).toFixed(1)}%; background:{k === 0
                ? C.ok
                : C.accent3}"
            ></div>
          </div>
          <div class="mono cbar-val">{w.toExponential(3)}</div>
        </div>
      {/each}
    </div>
    <div class="verdict mono">
      TN decision:
      <b style="color:{bitsToClass(decoded.prediction) === 0 ? C.ok : C.accent3}"
        >{classLabel(bitsToClass(decoded.prediction))}</b
      >
      · naïve min-weight:
      <b style="color:{mwLive.logical === 0 ? C.ok : C.accent3}"
        >{mwLive.logical === null ? "--" : classLabel(mwLive.logical)}</b
      >
      {#if liveDisagree}
        <span class="disagree">-- they disagree, and the TN answer is the optimal one.</span>
      {:else}
        <span class="agree"
          >-- they agree on this 1-D chain; the TN weight is still the exact summed likelihood of
          each class.</span
        >
      {/if}
    </div>
  </div>
{/if}

<style>
  .ctrl-row {
    display: flex;
    flex-wrap: wrap;
    gap: 18px 28px;
    align-items: center;
    margin-bottom: 14px;
  }

  .syn-btn {
    padding: 6px 12px;
    font-size: 13px;
  }

  .syn-btn.lit {
    border-color: color-mix(in srgb, var(--defect) 70%, transparent);
    background: color-mix(in srgb, var(--defect) 16%, transparent);
    color: var(--fg);
  }

  .syn-read {
    font-size: 13px;
    color: var(--muted);
  }

  .contract-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin: 16px 0;
  }

  .stat {
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: color-mix(in srgb, var(--bg-2) 55%, transparent);
  }

  .stat-k {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--faint);
    margin-bottom: 4px;
  }

  .stat-v {
    font-size: 15px;
    color: var(--fg);
  }

  .result {
    margin-top: 8px;
    padding: 16px;
    border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    border-radius: var(--r-md);
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  .result-title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 12px;
  }

  .class-bars {
    display: flex;
    flex-direction: column;
    gap: 9px;
  }

  .cbar {
    display: grid;
    grid-template-columns: 180px 1fr 96px;
    align-items: center;
    gap: 12px;
  }

  .cbar-name {
    font-size: 13px;
    font-weight: 600;
  }

  .cbar.win .cbar-name {
    text-shadow: 0 0 12px currentColor;
  }

  .cbar-track {
    height: 16px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    overflow: hidden;
  }

  .cbar-fill {
    height: 100%;
    border-radius: 6px;
    transition: width 200ms var(--ease-out);
  }

  .cbar-val {
    font-size: 12px;
    color: var(--muted);
    text-align: right;
  }

  .verdict {
    margin-top: 14px;
    font-size: 13.5px;
    color: var(--fg);
  }

  .disagree {
    color: var(--accent);
    font-weight: 600;
  }

  .agree {
    color: var(--muted);
  }
</style>
