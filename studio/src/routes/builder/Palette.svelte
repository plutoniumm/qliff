<script lang="ts">
  // Tile palette. Click a kind to arm it (next empty-canvas click drops one), or
  // drag a swatch onto the canvas. The Canvas component handles the drop; here
  // we just emit selection + provide HTML5 drag data.
  import type { TileKind } from "$lib/schema";

  interface Props {
    armed: TileKind | null;
    onarm: (kind: TileKind | null) => void;
  }

  let { armed, onarm }: Props = $props();

  const kinds: { kind: TileKind; label: string }[] = [
    { kind: "square", label: "Square" },
    { kind: "tri", label: "Triangle" },
    { kind: "hex", label: "Hex" },
  ];

  function dragStart(ev: DragEvent, kind: TileKind): void {
    ev.dataTransfer?.setData("application/x-tile-kind", kind);

    if (ev.dataTransfer) {
      ev.dataTransfer.effectAllowed = "copy";
    }
  }
</script>

<div class="palette">
  <div class="hd">Tiles</div>
  <div class="swatches">
    {#each kinds as k (k.kind)}
      <button
        class="swatch"
        class:active={armed === k.kind}
        draggable="true"
        ondragstart={(e) => dragStart(e, k.kind)}
        onclick={() => onarm(armed === k.kind ? null : k.kind)}
        title={`Click to arm, or drag onto the canvas (${k.label})`}
      >
        <svg viewBox="-20 -20 40 40" width="34" height="34">
          {#if k.kind === "square"}
            <rect x="-14" y="-14" width="28" height="28" />
          {:else if k.kind === "tri"}
            <polygon points="0,-16 14,12 -14,12" />
          {:else}
            <polygon points="16,0 8,14 -8,14 -16,0 -8,-14 8,-14" />
          {/if}
        </svg>
        <span>{k.label}</span>
      </button>
    {/each}
  </div>
  <p class="hint">
    Click a tile to arm, then click empty canvas to place. Or drag a swatch onto
    the canvas.
  </p>
</div>

<style>
  .palette {
    border-top: 1px solid var(--line);
    padding-top: 14px;
  }

  .hd {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 10px;
  }

  .hd::before {
    content: "";
    width: 2px;
    height: 12px;
    border-radius: 2px;
    background: var(--grad-phase);
  }

  .swatches {
    display: flex;
    gap: 8px;
  }

  .swatch {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding: 9px 6px;
    flex: 1;
    font-size: 11px;
    background: color-mix(in srgb, var(--bg-2) 55%, transparent);
    border-radius: var(--r-md);
  }

  .swatch svg {
    fill: var(--z);
    stroke: var(--fg);
    stroke-width: 1.5;
    transition: filter var(--dur-fast) var(--ease-out);
  }

  .swatch.active {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-phase-soft);
    box-shadow: var(--glow-accent);
  }

  .swatch.active svg {
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--z) 55%, transparent));
  }

  .hint {
    font-size: 11px;
    color: var(--faint);
    line-height: 1.5;
    margin: 10px 0 0;
  }
</style>
