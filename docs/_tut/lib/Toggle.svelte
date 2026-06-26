<script lang="ts">
  // Checkbox styled as a switch. <Toggle bind:checked={showWeights} label="show edge weights" />
  let { checked = $bindable(false), label = "" }: { checked?: boolean; label?: string } = $props();
</script>

<label class="toggle">
  <input type="checkbox" bind:checked />
  <span class="track" class:on={checked}><span class="knob"></span></span>
  <span class="text">{label}</span>
</label>

<style>
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
