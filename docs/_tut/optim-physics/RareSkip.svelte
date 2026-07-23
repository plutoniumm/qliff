<script lang="ts">
  // Rare-error noise by geometric skips. A noise location that fires with per-shot
  // probability phi lands on geometrically spaced shots, so the sampler jumps
  // straight to the next faulty shot -- skip = floor(ln(1-U) / ln(1-phi)) -- and
  // never visits the quiet ones in between. The grid lights the shots that faulted;
  // the readout compares the work done (one branch draw per faulty shot) against
  // the naive per-shot loop. At QEC rates phi ~ 1e-3 the win is ~ 1/phi.
  import Slider from "$lib/Slider.svelte";
  import { C, withAlpha } from "$lib/colors";
  import { geometricSkips } from "./model";

  let phi = $state(0.05);
  let shots = $state(256);
  let seed = $state(3);

  const run = $derived(geometricSkips(phi, shots, seed));
  const faultySet = $derived(new Set(run.faulty));
  const naive = $derived(shots);
  const saved = $derived(run.faulty.length > 0 ? shots / run.faulty.length : Infinity);
</script>

<div class="prose-controls">
  <Slider
    bind:value={phi}
    min={0}
    max={0.2}
    step={0.005}
    label="per-shot fault probability phi"
    format={(v) => v.toFixed(3)}
  />
  <Slider bind:value={shots} min={64} max={512} step={64} label="shots in the block" />
  <Slider bind:value={seed} min={1} max={40} step={1} label="seed" />
</div>

<div class="cells">
  {#each Array(shots) as _, s (s)}
    <span
      class="cell"
      class:hit={faultySet.has(s)}
      style="--bgc:{withAlpha(C.defect, 0.95)}"
      title={`shot ${s}${faultySet.has(s) ? ": faulted" : ""}`}
    ></span>
  {/each}
</div>

<div class="stat-strip">
  <span>shots that faulted <b style="color:{C.defect}">{run.faulty.length}</b></span>
  <span>uniform draws spent <b>{run.draws}</b></span>
  <span>naive per-shot visits <b>{naive}</b></span>
  <span>work ratio <b style="color:{C.accent}">{Number.isFinite(saved) ? saved.toFixed(1) + "x" : "--"}</b></span>
</div>
<p class="note">
  Each faulty shot costs one geometric skip and one branch draw; the quiet shots cost nothing. The
  work ratio is shots / faults, which tracks 1 / phi. At phi = 0 the location is skipped outright
  (no fault mass); at phi = 1 every shot faults and the skips are all zero.
</p>

<style>
  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }

  .cells {
    display: grid;
    grid-template-columns: repeat(auto-fill, 12px);
    gap: 3px;
    justify-content: center;
  }

  .cell {
    width: 12px;
    height: 12px;
    border-radius: 3px;
    border: 1px solid var(--line);
    background: color-mix(in srgb, var(--line) 30%, transparent);
  }

  .cell.hit {
    border-color: var(--defect);
    background: var(--bgc);
  }

  .stat-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin-top: 18px;
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
