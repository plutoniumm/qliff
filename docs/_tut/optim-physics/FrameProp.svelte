<script lang="ts">
  // The Pauli frame sampler, one Z-parity check wide. 64 shots ride the same
  // instruction stream as a bit-packed cohort: X faults land on the two data
  // qubits, copy forward through CX into the ancilla frame (fx[a] = fx[q0] XOR
  // fx[q1]), and the deterministic measurement records reference XOR fx[a] for the
  // whole word at once. Flip the final measurement to a random basis and the frame
  // method has no coin to model -> the sampler falls back to a per-shot tableau.
  // Everything is a $derived of the controls; no $effect writes state.
  import Slider from "$lib/Slider.svelte";
  import Toggle from "$lib/Toggle.svelte";
  import { C, withAlpha } from "$lib/colors";
  import { frameGrid } from "./model";

  let phi = $state(0.08);
  let shots = $state(64);
  let deterministic = $state(true);
  let seed = $state(5);

  const grid = $derived(frameGrid(phi, shots, seed));
  const rows = $derived([
    {
      label: "fx  data q0",
      bits: grid.q0,
      color: C.x,
    },
    {
      label: "fx  data q1",
      bits: grid.q1,
      color: C.x,
    },
    {
      label: "record  M(anc) = ref XOR fx[a]",
      bits: grid.record,
      color: C.defect,
    },
  ]);
</script>

<div class="prose-controls">
  <Slider
    bind:value={phi}
    min={0}
    max={0.4}
    step={0.01}
    label="per-qubit fault rate"
    format={(v) => v.toFixed(2)}
  />
  <Slider bind:value={shots} min={8} max={64} step={8} label="shots in the word" />
  <Slider bind:value={seed} min={1} max={40} step={1} label="seed" />
</div>
<div class="toggle-row">
  <Toggle bind:checked={deterministic} label="final measurement is a deterministic Z parity" />
</div>

{#if deterministic}
  <div class="grid">
    {#each rows as r (r.label)}
      <span class="rlbl mono">{r.label}</span>
      <span class="word">
        {#each r.bits as on, s (s)}
          <span
            class="bit"
            class:on
            style="--c:{r.color}; --bgc:{withAlpha(r.color, 0.9)}"
            title={`shot ${s}: ${on ? "1" : "0"}`}
          ></span>
        {/each}
      </span>
    {/each}
  </div>
  <div class="stat-strip">
    <span>frame path <b style="color:{C.ok}">active</b></span>
    <span>shots touched by a fault <b>{grid.touched} / {shots}</b></span>
    <span>tableau runs <b>1</b> (the noiseless reference)</span>
    <span>gate work per shot <b>0</b></span>
  </div>
  <p class="note">
    The recorded syndrome word is the XOR of the two fault words, formed in one pass over the
    cohort: fx[a] ^= fx[q0] then fx[a] ^= fx[q1], and record = reference XOR fx[a] with the
    reference bit 0. No tableau is touched per shot; the only full simulation was the one noiseless
    reference run that fixed those reference bits.
  </p>
{:else}
  <div class="fallback">
    <div class="fallback-title">frame path unavailable -> per-shot tableau</div>
    <p>
      A measurement in a random basis is a genuine coin: its outcome is not reference XOR frame, so
      a sign-free frame cannot reproduce it. frame_reference returns None the moment it hits a
      random measurement, and CompiledSampler.sample falls back to sample_batch, which builds and
      runs a full tableau for every one of the {shots} shots. Correct, but this is exactly the cost
      the frame path exists to avoid.
    </p>
  </div>
{/if}

<style>
  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px 26px;
    margin-bottom: 14px;
  }

  .toggle-row {
    margin-bottom: 18px;
  }

  .grid {
    display: grid;
    grid-template-columns: max-content 1fr;
    align-items: center;
    gap: 10px 14px;
    overflow-x: auto;
  }

  .rlbl {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }

  .word {
    display: flex;
    gap: 3px;
    flex-wrap: wrap;
  }

  .bit {
    width: 13px;
    height: 13px;
    border-radius: 3px;
    border: 1px solid var(--line);
    background: color-mix(in srgb, var(--line) 40%, transparent);
  }

  .bit.on {
    border-color: var(--c);
    background: var(--bgc);
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

  .fallback {
    border: 1px solid color-mix(in srgb, var(--bad) 45%, transparent);
    border-radius: 10px;
    padding: 16px 18px;
    background: color-mix(in srgb, var(--bad) 8%, transparent);
  }

  .fallback-title {
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--bad);
    margin-bottom: 8px;
  }

  .fallback p {
    margin: 0;
    font-size: 13.5px;
    line-height: 1.6;
    color: var(--faint);
  }

  .note {
    margin: 12px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.55;
  }
</style>
