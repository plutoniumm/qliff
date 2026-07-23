<script lang="ts">
  // Reproducibility as a design point. The frame sampler splits `shots` into
  // FIXED-size chunks (FRAME_CHUNK = 1024) and derives each chunk's RNG seed from
  // its INDEX via splitmix64 (chunk_seed in tableau.rs), never from the core that
  // runs it. So moving work between cores (the cores control) only recolours the
  // grid -- the seed column, and therefore every sampled bit, is invariant. The
  // output digest folds the per-chunk seeds in index order, so it too is fixed. All
  // $derived; no $effect writes state.
  import Slider from "$lib/Slider.svelte";
  import { C } from "$lib/colors";
  import { FRAME_CHUNK, planChunks, shortHex } from "./model";

  let shots = $state(8192);
  let seed = $state(7);
  let cores = $state(4);

  const chunks = $derived(planChunks(shots, seed, cores));
  const palette = [C.accent, C.accent2, C.accent3, C.x, C.z, C.y, C.ok, C.data];

  // A schedule-independent fold of the per-chunk seeds (index order), standing in
  // for "the concatenated sample output": it depends only on (seed, shots), so it
  // does not move when cores changes.
  const digest = $derived.by(() => {
    const M = (1n << 64n) - 1n;
    let acc = 0x1234_5678n;

    for (const c of chunks) {
      acc = ((acc * 0x0100_0000_01b3n) ^ c.seed) & M;
    }

    return shortHex(acc);
  });
</script>

<div class="prose-controls">
  <Slider bind:value={shots} min={1024} max={24576} step={1024} label="shots" />
  <Slider bind:value={seed} min={1} max={99} step={1} label="seed" />
  <Slider bind:value={cores} min={1} max={8} step={1} label="cores (rayon workers)" />
</div>

<div class="grid">
  {#each chunks as c (c.index)}
    <div class="chunk" style="--c:{palette[c.core % palette.length]}">
      <div class="idx">chunk {c.index}</div>
      <div class="core">core {c.core}</div>
      <div class="seed mono">{shortHex(c.seed)}</div>
      <div class="shots">{c.shots} shots</div>
    </div>
  {/each}
</div>

<div class="stat-strip">
  <span>chunks <b>{chunks.length}</b></span>
  <span>chunk size <b>{FRAME_CHUNK}</b></span>
  <span>cores in use <b style="color:{C.accent}">{Math.min(cores, chunks.length)}</b></span>
  <span>output digest <b>{digest}</b></span>
</div>
<p class="note">
  Colour is the core a chunk runs on; the mono value is its splitmix64 seed, derived
  from the chunk INDEX. Drag <b>cores</b>: the colours reshuffle but no seed changes
  and the <b>output digest</b> holds -- the sample is byte-identical whether rayon
  spreads it over 1 worker or 8. Verified in the source at 1 vs 8 threads. The
  per-shot tableau sampler (BATCH_CHUNK = 256) and the importance estimator
  (EST_CHUNK = 256) chunk the same way, for the same reason.
</p>

<style>
  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
    gap: 8px;
  }

  .chunk {
    border: 1px solid var(--line);
    border-left: 4px solid var(--c);
    border-radius: 7px;
    padding: 7px 10px;
    background: color-mix(in srgb, var(--c) 7%, transparent);
  }

  .idx {
    font-size: 12px;
    font-weight: 700;
    color: var(--fg);
  }

  .core {
    font-size: 11px;
    color: var(--c);
    font-weight: 600;
  }

  .seed {
    font-size: 12.5px;
    color: var(--fg);
    margin-top: 3px;
    letter-spacing: 0.04em;
  }

  .shots {
    font-size: 10.5px;
    color: var(--faint);
    margin-top: 1px;
  }

  .mono {
    font-family: var(--font-mono);
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
    margin: 10px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.55;
  }
</style>
