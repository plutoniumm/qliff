<script lang="ts">
  // Section 5 island: posterior belief bars for the repetition-code run. Scrub the
  // iteration and move the true error to watch BP converge; the status line reports
  // whether the hard decision reproduces the syndrome. Self-contained -- it owns
  // its own iteration + true-error controls (the original drove these bars from the
  // section-4 panel, which markdown cannot share across two islands).
  import BeliefBars from "./BeliefBars.svelte";
  import Scrubber from "./Scrubber.svelte";
  import { repetitionCode, syndromeOf, runBp } from "./bp";

  const repP = 0.06;
  const repCode = repetitionCode(7, repP);
  let errBit = $state(3);
  const repTrueError = $derived(
    Array.from({ length: 7 }, (_, i) => (i === errBit ? 1 : 0)),
  );
  const repSyndrome = $derived(syndromeOf(repCode, repTrueError));
  const repBp = $derived(runBp(repCode, repSyndrome, 12));
  let repIter = $state(0);
  const repFrame = $derived(
    repBp.frames[Math.min(repIter, repBp.frames.length - 1)],
  );
  // Decoded vs. true, at the current frame.
  const repCorrect = $derived(
    repFrame.satisfied && repFrame.hard.every((b, i) => b === repTrueError[i]),
  );
</script>

<BeliefBars
  posterior={repFrame.posterior}
  hard={repFrame.hard}
  trueError={repTrueError}
/>
<div class="controls">
  <Scrubber bind:value={repIter} min={0} max={11} label="iteration" />
  <div class="err-pick">
    <span class="mini-label">true error on bit</span>
    {#each Array(7) as _, i (i)}
      <button class="ebtn" class:on={errBit === i} onclick={() => (errBit = i)}>
        {i}
      </button>
    {/each}
  </div>
</div>
<div class="answer-status" class:ok={repCorrect}>
  {#if repFrame.satisfied}
    {#if repCorrect}
      &#10003; converged at iteration {repFrame.iter}: decoded error reproduces the
      syndrome and matches the true error.
    {:else}
      &#10003; syndrome reproduced at iteration {repFrame.iter} (a valid, if degenerate,
      explanation).
    {/if}
  {:else}
    ... still settling: the hard decision doesn't yet reproduce the syndrome.
  {/if}
</div>

<style>
  .controls {
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .err-pick {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
  }

  .mini-label {
    font-size: 11.5px;
    color: var(--muted);
    margin-right: 4px;
  }

  .ebtn {
    width: 26px;
    height: 26px;
    padding: 0;
    font-size: 12px;
    border-radius: 6px;
    border: 1px solid var(--line);
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
    color: var(--muted);
  }

  .ebtn.on {
    border-color: color-mix(in srgb, var(--accent-2) 60%, transparent);
    background: color-mix(in srgb, var(--accent-2) 16%, transparent);
    color: var(--fg);
  }

  .answer-status {
    margin-top: 14px;
    text-align: center;
    font-size: 13.5px;
    color: var(--muted);
    line-height: 1.5;
  }

  .answer-status.ok {
    color: var(--ok);
  }
</style>
