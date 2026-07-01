<script lang="ts">
  // Section 4 island: real sum-product BP on a 7-bit repetition code. Scrub the
  // iteration, toggle the messages, and move the true error; the kept TannerGraph
  // renders each frame. Self-contained so its controls live beside it.
  import TannerGraph from "./TannerGraph.svelte";
  import Scrubber from "./Scrubber.svelte";
  import { repetitionCode, syndromeOf, runBp } from "./bp";

  const repP = 0.06;
  const repCode = repetitionCode(7, repP);
  let errBit = $state(3); // which single bit carries the true error
  const repTrueError = $derived(
    Array.from({ length: 7 }, (_, i) => (i === errBit ? 1 : 0)),
  );
  const repSyndrome = $derived(syndromeOf(repCode, repTrueError));
  const repBp = $derived(runBp(repCode, repSyndrome, 12));
  let repIter = $state(0);
  let showMsgs = $state(true);
  const repFrame = $derived(
    repBp.frames[Math.min(repIter, repBp.frames.length - 1)],
  );
</script>

<TannerGraph
  code={repCode}
  syndrome={repSyndrome}
  trueError={repTrueError}
  frame={repFrame}
  showMessages={showMsgs}
  height={250}
/>
<div class="dance-controls">
  <Scrubber bind:value={repIter} min={0} max={11} label="iteration" />
  <div class="dance-row">
    <label class="toggle">
      <input type="checkbox" bind:checked={showMsgs} />
      <span class="track" class:on={showMsgs}><span class="knob"></span></span>
      <span class="text">show messages</span>
    </label>
    <div class="err-pick">
      <span class="mini-label">true error on bit</span>
      {#each Array(7) as _, i (i)}
        <button class="ebtn" class:on={errBit === i} onclick={() => (errBit = i)}>
          {i}
        </button>
      {/each}
    </div>
  </div>
</div>

<style>
  .dance-controls {
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .dance-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 14px;
  }

  .err-pick {
    display: flex;
    align-items: center;
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

  /* switch, inlined from the shared Toggle control */
  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    cursor: pointer;
    user-select: none;
  }

  .toggle input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }

  .track {
    position: relative;
    width: 38px;
    height: 22px;
    border-radius: 99px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    transition: background var(--dur-fast) var(--ease-out);
    flex: none;
  }

  .track.on {
    background: var(--grad-soft);
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
  }

  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--fg);
    transition: transform var(--dur-fast) var(--ease-out);
  }

  .track.on .knob {
    transform: translateX(16px);
  }

  .text {
    font-size: 13.5px;
    color: var(--fg);
  }
</style>
