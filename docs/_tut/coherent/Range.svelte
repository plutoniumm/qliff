<script lang="ts">
  // Minimal labeled range control with a live numeric readout. Self-contained so
  // the coherent islands do not depend on the shared $lib prose wrappers (removed
  // after the markdown migration). Two-way bound via bind:value.
  let {
    value = $bindable(0),
    min = 0,
    max = 1,
    step = 0.01,
    label = "",
    format,
  }: {
    value?: number;
    min?: number;
    max?: number;
    step?: number;
    label?: string;
    format?: (v: number) => string;
  } = $props();

  const shown = $derived(format ? format(value) : `${value}`);
</script>

<label class="rng">
  <span class="row">
    <span class="lbl">{label}</span>
    <span class="val mono">{shown}</span>
  </span>
  <input type="range" {min} {max} {step} bind:value />
</label>

<style>
  .rng {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }

  .lbl {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .val {
    font-size: 13px;
    color: var(--fg);
  }

  input[type="range"] {
    width: 100%;
  }
</style>
