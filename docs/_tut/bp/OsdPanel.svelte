<script lang="ts">
  // Section 7 island: OSD applied to BP's stuck output. Columns are listed
  // most-reliable-first (heat bars = |LLR| from BP's final posterior); the pivot
  // core is solved exactly to force a syndrome-matching recovery. Computed once
  // from the degenerate trap -- kept as an island so the reliability bars and the
  // solved-recovery readout survive the move to markdown.
  import {
    degenerateCode,
    STUCK_SYNDROME,
    runBp,
    runOsd,
    syndromeOf,
    type Code,
  } from "./bp";
  import { heat, withAlpha } from "$lib/colors";

  const stuckCode: Code = degenerateCode(0.08);
  const stuckSyndrome = STUCK_SYNDROME;
  const stuckBp = runBp(stuckCode, stuckSyndrome, 16);
  // Feed BP's final (oscillating) posterior into OSD.
  const osd = runOsd(stuckCode, stuckSyndrome, stuckBp.finalPosterior, 7);
  const osdSyndromeOk =
    syndromeOf(stuckCode, osd.solution).join("") === stuckSyndrome.join("");
</script>

<div class="osd-grid">
  <div class="osd-col">
    <div class="osd-h">1 &middot; reliability order</div>
    <div class="rel-row">
      {#each osd.order as m, rank (m)}
        {@const isPivot = osd.pivots.includes(m)}
        <div class="rel-cell" class:pivot={isPivot}>
          <span class="mono">e{m}</span>
          <span class="rel-bar">
            <span
              class="rel-fill"
              style="height:{Math.min(100, (Math.abs(stuckBp.finalPosterior[m]) / 5) * 100).toFixed(0)}%;
                     background:{withAlpha(heat(Math.min(1, Math.abs(stuckBp.finalPosterior[m]) / 5)), 0.9)}"
            ></span>
          </span>
          <span class="rel-tag">{isPivot ? "pivot" : "free"}</span>
        </div>
      {/each}
    </div>
  </div>
  <div class="osd-col">
    <div class="osd-h">2 &middot; solved recovery</div>
    <div class="osd-sol">
      <div class="sol-line">
        <span class="sol-label">order-0 (free = 0):</span>
        <span class="mono sol-vec">{osd.osd0.join("")}</span>
        <span class="sol-w">weight {osd.osd0Weight}</span>
      </div>
      <div class="sol-line best">
        <span class="sol-label">after order-7 search:</span>
        <span class="mono sol-vec">{osd.solution.join("")}</span>
        <span class="sol-w">weight {osd.solutionWeight}</span>
      </div>
      <div class="sol-verdict" class:ok={osdSyndromeOk}>
        {#if osdSyndromeOk}
          &#10003; reproduces syndrome <span class="mono">{stuckSyndrome.join("")}</span> --
          BP+OSD recovers <span class="mono">e0</span> where plain BP spun forever.
        {:else}
          residual <span class="mono">{osd.residual.join("")}</span>
        {/if}
      </div>
    </div>
  </div>
</div>

<style>
  .osd-grid {
    display: grid;
    grid-template-columns: 1fr 1.3fr;
    gap: 24px;
  }

  .osd-h {
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--faint);
    margin-bottom: 12px;
  }

  .rel-row {
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }

  .rel-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    padding: 6px;
    border-radius: var(--r-sm, 8px);
    border: 1px solid transparent;
  }

  .rel-cell.pivot {
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
    background: var(--grad-soft);
  }

  .rel-bar {
    width: 14px;
    height: 60px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    display: flex;
    align-items: flex-end;
    overflow: hidden;
  }

  .rel-fill {
    width: 100%;
    transition: height 0.2s ease;
  }

  .rel-tag {
    font-size: 9.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--faint);
  }

  .rel-cell.pivot .rel-tag {
    color: var(--accent);
  }

  .osd-sol {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .sol-line {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 13.5px;
    color: var(--muted);
  }

  .sol-line.best {
    color: var(--fg);
  }

  .sol-label {
    min-width: 150px;
  }

  .sol-vec {
    font-size: 16px;
    letter-spacing: 0.18em;
    color: var(--fg);
  }

  .sol-w {
    font-size: 12px;
    color: var(--faint);
  }

  .sol-verdict {
    margin-top: 6px;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.5;
  }

  .sol-verdict.ok {
    color: var(--ok);
  }

  @media (max-width: 720px) {
    .osd-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
