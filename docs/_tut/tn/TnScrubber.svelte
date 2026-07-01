<script lang="ts">
  // Local step controller for walking an algorithm frame by frame (contraction
  // order here). Two-way binds `value`; optional play button auto-advances and
  // stops at max. Self-contained (no shared-lib dependency).
  import { onDestroy } from "svelte";

  let {
    value = $bindable(0),
    min = 0,
    max = 10,
    label = "step",
    playable = true,
    intervalMs = 700,
  }: {
    value?: number;
    min?: number;
    max?: number;
    label?: string;
    playable?: boolean;
    intervalMs?: number;
  } = $props();

  let timer: ReturnType<typeof setInterval> | null = $state(null);

  function stop(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function play(): void {
    if (timer !== null) {
      stop();

      return;
    }
    if (value >= max) {
      value = min;
    }
    timer = setInterval(() => {
      if (value >= max) {
        stop();

        return;
      }
      value += 1;
    }, intervalMs);
  }

  function step(delta: number): void {
    stop();
    value = Math.max(min, Math.min(max, value + delta));
  }

  onDestroy(stop);
</script>

<div class="scrubber">
  {#if playable}
    <button class="play" class:on={timer !== null} onclick={play} aria-label="play / pause">
      {timer !== null ? "❚❚" : "▶"}
    </button>
  {/if}
  <button onclick={() => step(-1)} disabled={value <= min} aria-label="previous">‹</button>
  <input type="range" {min} {max} step="1" bind:value oninput={stop} />
  <button onclick={() => step(1)} disabled={value >= max} aria-label="next">›</button>
  <span class="readout mono">{label} {value}/{max}</span>
</div>

<style>
  .scrubber {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .scrubber input[type="range"] {
    flex: 1;
  }

  .play.on {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-soft);
  }

  .readout {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    min-width: 84px;
    text-align: right;
  }

  button {
    padding: 6px 11px;
  }
</style>
