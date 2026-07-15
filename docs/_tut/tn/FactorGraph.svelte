<script lang="ts">
  // SVG factor-graph for a repetition-code DEM: round COPY tensors (one per
  // error mechanism, carrying [1-p, p]), square PARITY tensors (detectors,
  // pinned to the syndrome bit) and a triangular OPEN observable tensor. Legs
  // are drawn as edges. Click a detector to flip its syndrome bit and watch the
  // parity tensor re-pin. Purely presentational: it takes the graph + syndrome
  // and emits syndrome changes; no decoding happens here.
  import type { FactorGraph } from "./decoder";

  let {
    fg,
    syndrome,
    p,
    highlightMechs = [],
    onFlip,
  }: {
    fg: FactorGraph;
    syndrome: number[];
    p: number;
    highlightMechs?: number[];
    onFlip?: (d: number) => void;
  } = $props();

  const W = 720;
  const H = 300;
  const detY = 70;
  const copyY = 165;
  const obsY = 262;

  const copyX = $derived.by(() => {
    const n = fg.copies.length;
    const span = W - 120;

    return fg.copies.map((_, i) => 60 + (span * (i + 0.5)) / n);
  });
  const detX = $derived.by(() => {
    const n = fg.detectors.length;
    const span = W - 160;

    return fg.detectors.map((_, i) => 80 + (span * (i + 0.5)) / Math.max(1, n));
  });
  const obsX = $derived(W / 2);

  function flipDet(d: number): void {
    onFlip?.(d);
  }

  function legPath(x1: number, y1: number, x2: number, y2: number): string {
    const my = (y1 + y2) / 2;

    return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`;
  }
</script>

<svg viewBox="0 0 {W} {H}" class="fg" role="img" aria-label="decoding factor graph">
  <!-- legs first, under the nodes -->
  {#each fg.copies as node, m}
    {#each node.legs as leg}
      {#if leg.kind === "det"}
        <path
          class="leg"
          class:hot={highlightMechs.includes(m)}
          d={legPath(copyX[m], copyY, detX[leg.idx], detY)}
        />
      {:else}
        <path
          class="leg"
          class:hot={highlightMechs.includes(m)}
          d={legPath(copyX[m], copyY, obsX, obsY)}
        />
      {/if}
    {/each}
  {/each}

  <!-- detector parity tensors -->
  {#each fg.detectors as det}
    <g
      class="det"
      class:lit={syndrome[det.d] === 1}
      role="button"
      tabindex="0"
      onclick={() => flipDet(det.d)}
      onkeydown={(e) => (e.key === "Enter" || e.key === " ") && flipDet(det.d)}
    >
      <rect x={detX[det.d] - 16} y={detY - 16} width="32" height="32" rx="6" />
      <text x={detX[det.d]} y={detY + 5} class="node-label">{syndrome[det.d]}</text>
    </g>
    <text x={detX[det.d]} y={detY - 26} class="cap">check {det.d}</text>
  {/each}

  <!-- copy tensors (mechanisms) -->
  {#each fg.copies as node, m}
    <g class="copy" class:hot={highlightMechs.includes(m)}>
      <circle cx={copyX[m]} cy={copyY} r="15" />
      <text x={copyX[m]} y={copyY + 4} class="node-label small">{node.label}</text>
    </g>
    <text x={copyX[m]} y={copyY + 33} class="cap">[{(1 - p).toFixed(2)}, {p.toFixed(2)}]</text>
  {/each}

  <!-- observable parity tensor with the open leg -->
  {#each fg.observables as obs}
    <g class="obs">
      <polygon
        points="{obsX},{obsY - 16} {obsX - 16},{obsY + 12} {obsX + 16},{obsY + 12}"
      />
      <line class="open" x1={obsX + 26} y1={obsY} x2={obsX + 70} y2={obsY} />
      <circle class="open-dot" cx={obsX + 70} cy={obsY} r="4" />
      <text x={obsX + 78} y={obsY + 4} class="cap open-cap">predicted flip (open)</text>
    </g>
  {/each}

  <!-- legend ticks -->
  <text x={detX[0] - 40} y={detY + 4} class="side">checks</text>
  <text x={20} y={copyY + 4} class="side">mechanisms</text>
  <text x={20} y={obsY + 4} class="side">observable</text>
</svg>

<style>
  .fg {
    width: 100%;
    height: auto;
    /* viewBox is 720x300; cap rendered height so the graph always fits a laptop
       viewport (preserveAspectRatio letterboxes, so no distortion). */
    max-height: 320px;
    display: block;
    user-select: none;
  }

  .leg {
    fill: none;
    stroke: var(--line);
    stroke-width: 1.4;
  }

  .leg.hot {
    stroke: var(--accent);
    stroke-width: 2.4;
  }

  .det rect {
    fill: color-mix(in srgb, var(--z) 14%, transparent);
    stroke: var(--z);
    stroke-width: 1.6;
    cursor: pointer;
    transition: fill 130ms ease, stroke 130ms ease;
  }

  .det.lit rect {
    fill: color-mix(in srgb, var(--defect) 75%, transparent);
    stroke: var(--defect);
  }

  .det:hover rect {
    stroke-width: 2.4;
  }

  .det:focus {
    outline: none;
  }

  .det:focus rect {
    stroke-width: 2.6;
  }

  .copy circle {
    fill: color-mix(in srgb, var(--accent) 16%, transparent);
    stroke: var(--accent);
    stroke-width: 1.6;
  }

  .copy.hot circle {
    fill: color-mix(in srgb, var(--accent) 40%, transparent);
    stroke-width: 2.6;
  }

  .obs polygon {
    fill: color-mix(in srgb, var(--accent-2) 16%, transparent);
    stroke: var(--accent-2);
    stroke-width: 1.6;
  }

  .obs .open {
    stroke: var(--accent-2);
    stroke-width: 1.8;
    stroke-dasharray: 4 3;
  }

  .obs .open-dot {
    fill: var(--accent-2);
  }

  .node-label {
    fill: var(--fg);
    font:
      600 14px/1 ui-monospace,
      monospace;
    text-anchor: middle;
  }

  .node-label.small {
    font-size: 11px;
  }

  .cap {
    fill: var(--faint);
    font:
      11px/1 ui-monospace,
      monospace;
    text-anchor: middle;
  }

  .open-cap {
    text-anchor: start;
    fill: var(--accent-2);
  }

  .side {
    fill: var(--muted);
    font:
      600 11px/1 ui-sans-serif,
      sans-serif;
    text-anchor: start;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
</style>
