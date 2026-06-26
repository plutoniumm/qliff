<script lang="ts">
  // Labeled range control with a live numeric readout. Two-way bound:
  //   <Slider bind:value={p} min={0} max={0.2} step={0.001} label="physical error p" />
  let {
    value = $bindable(0),
    min = 0,
    max = 1,
    step = 0.01,
    label = "",
    unit = "",
    format,
  }: {
    value?: number;
    min?: number;
    max?: number;
    step?: number;
    label?: string;
    unit?: string;
    format?: (v: number) => string;
  } = $props();

  const shown = $derived(format ? format(value) : `${value}${unit ? ` ${unit}` : ""}`);
</script>

<label class="slider">
  <span class="row">
    <span class="label">{label}</span>
    <span class="value mono">{shown}</span>
  </span>
  <input type="range" {min} {max} {step} bind:value />
</label>

<style>
  .slider {
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

  .label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .value {
    font-size: 13px;
    color: var(--fg);
  }
</style>
