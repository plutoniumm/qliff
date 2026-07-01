<script lang="ts">
  // Section 6 island: the degenerate trap where BP oscillates forever. Step the
  // iteration and watch the hard decision flip between e0,e1 and nothing while the
  // posteriors for e0 and e1 stay locked together. Self-contained so its scrubber
  // and status line live beside the graph + belief bars (markdown cannot hold the
  // shared Svelte state the original section drove).
  import TannerGraph from "./TannerGraph.svelte";
  import BeliefBars from "./BeliefBars.svelte";
  import Scrubber from "./Scrubber.svelte";
  import { degenerateCode, STUCK_SYNDROME, runBp, type Code } from "./bp";

  const stuckCode: Code = degenerateCode(0.08);
  const stuckSyndrome = STUCK_SYNDROME;
  const stuckBp = runBp(stuckCode, stuckSyndrome, 16);
  let stuckIter = $state(0);
  const stuckFrame = $derived(
    stuckBp.frames[Math.min(stuckIter, stuckBp.frames.length - 1)],
  );
</script>

<TannerGraph
  code={stuckCode}
  syndrome={stuckSyndrome}
  frame={stuckFrame}
  showMessages={true}
  height={250}
/>
<BeliefBars posterior={stuckFrame.posterior} hard={stuckFrame.hard} />
<div class="dance-controls">
  <Scrubber bind:value={stuckIter} min={0} max={15} label="iteration" />
  <div class="answer-status warn">
    iteration {stuckFrame.iter}: hard decision =
    <span class="mono">{stuckFrame.hard.join("")}</span>
    {#if stuckFrame.satisfied}
      (reproduces syndrome)
    {:else}
      -- does <strong>not</strong> reproduce the syndrome
      <span class="mono">{stuckSyndrome.join("")}</span>
    {/if}
  </div>
</div>

<style>
  .dance-controls {
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .answer-status {
    margin-top: 14px;
    text-align: center;
    font-size: 13.5px;
    color: var(--muted);
    line-height: 1.5;
  }

  .answer-status.warn {
    color: var(--accent-3);
  }
</style>
