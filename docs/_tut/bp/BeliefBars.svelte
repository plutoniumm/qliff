<script lang="ts">
  // A row of per-mechanism belief gauges. Each bar shows the posterior LLR: it
  // grows left (toward "error", red) when the LLR is negative and right (toward
  // "no error", calm) when positive. The fill colour uses heat() on the
  // *magnitude* so a confident belief is warm and a near-zero (undecided)
  // belief is washed out. Pure render of props.
  import { C, withAlpha, heat } from "$lib/colors";

  let {
    posterior,
    hard = [],
    trueError = [],
    labels,
    scale = 6,
  }: {
    posterior: number[];
    hard?: number[];
    trueError?: number[];
    labels?: string[];
    scale?: number; // LLR magnitude that maps to a full half-bar
  } = $props();

  function frac(llr: number): number {
    return Math.min(1, Math.abs(llr) / scale);
  }
</script>

<div class="bars">
  {#each posterior as llr, m (m)}
    {@const f = frac(llr)}
    {@const err = llr < 0}
    {@const fired = (hard[m] ?? (err ? 1 : 0)) === 1}
    {@const isTrue = (trueError[m] ?? 0) === 1}
    <div class="bar" class:istrue={isTrue}>
      <div class="head">
        <span class="name mono">{labels?.[m] ?? `e${m}`}</span>
        <span class="llr mono" class:err>{llr >= 0 ? "+" : ""}{llr.toFixed(2)}</span>
      </div>
      <div class="track">
        <div class="mid"></div>
        <div
          class="fill"
          class:left={err}
          style="width:{(f * 50).toFixed(1)}%; background:{withAlpha(
            err ? C.bad : heat(f),
            0.85,
          )}"
        ></div>
      </div>
      <div class="verdict" style="color:{fired ? C.bad : C.muted}">
        {fired ? "error" : "no error"}
      </div>
    </div>
  {/each}
</div>

<!-- shared x-axis: what the bar direction and the number mean -->
<div class="axis">
  <span class="end err">← error (ℓ &lt; 0)</span>
  <span class="unit mono">posterior LLR ℓ (nats), full bar at |ℓ| = {scale}</span>
  <span class="end ok">no error (ℓ &gt; 0) →</span>
</div>

<style>
  .bars {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: center;
  }

  .bar {
    flex: 1 1 90px;
    min-width: 84px;
    max-width: 150px;
  }

  .bar.istrue .name {
    color: var(--accent-2);
  }

  .head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 4px;
  }

  .name {
    font-size: 12px;
    color: var(--fg);
    font-weight: 600;
  }

  .llr {
    font-size: 11.5px;
    color: var(--muted);
  }

  .llr.err {
    color: var(--bad);
  }

  .track {
    position: relative;
    height: 12px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    overflow: hidden;
  }

  .mid {
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--line-strong);
  }

  .fill {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 50%;
    transition:
      width 0.25s ease,
      background 0.25s ease;
  }

  .fill.left {
    left: auto;
    right: 50%;
  }

  .verdict {
    margin-top: 4px;
    font-size: 10.5px;
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .axis {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 6px 16px;
    margin-top: 12px;
    padding-top: 9px;
    border-top: 1px solid var(--line);
    font-size: 11px;
    color: var(--faint);
  }

  .axis .end {
    font-weight: 600;
  }

  .axis .end.err {
    color: var(--bad);
  }

  .axis .end.ok {
    color: var(--muted);
  }

  .axis .unit {
    color: var(--faint);
  }
</style>
