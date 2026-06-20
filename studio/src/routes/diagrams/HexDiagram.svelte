<script lang="ts">
  // Honeycomb (color-code) lattice diagram + controls. Three face colors are
  // user-adjustable; edges inherit the third color (color-code structure).
  import { Grid } from "./hex";
  import type { ColorMap, LabelMap } from "./hex";
  import LatticeView from "./LatticeView.svelte";

  let cols = $state(5);
  let rows = $state(4);
  let size = $state(40);
  let showFaces = $state(true);
  let showEdges = $state(true);
  let showLabels = $state(false);

  let colors = $state<ColorMap>({
    A: "#5aa0ff",
    B: "#ff6b6b",
    C: "#4cc9f0",
  });
  const labels: LabelMap = {
    A: "A",
    B: "B",
    C: "C",
  };

  let grid = $derived(Grid(rows, cols, size, colors, labels));
  let name = $derived(`color_code_${cols}x${rows}`);
</script>

<div class="layout">
  <aside class="sidebar glass">
    <header class="head">
      <h3 class="gradient-text">Hexagonal color code</h3>
      <p class="sub">3-colorable honeycomb &middot; CSS</p>
    </header>
    <label>Columns<input type="number" min="1" max="20" bind:value={cols} /></label>
    <label>Rows<input type="number" min="1" max="20" bind:value={rows} /></label>
    <label>Size<input type="number" min="10" max="80" step="5" bind:value={size} /></label>
    <label class="chk"><input type="checkbox" bind:checked={showFaces} />Faces</label>
    <label class="chk"><input type="checkbox" bind:checked={showEdges} />Edges</label>
    <label class="chk"><input type="checkbox" bind:checked={showLabels} />Labels</label>
    <fieldset class="colors">
      <legend>Face colors</legend>
      <label class="color">A<input type="color" bind:value={colors.A} /></label>
      <label class="color">B<input type="color" bind:value={colors.B} /></label>
      <label class="color">C<input type="color" bind:value={colors.C} /></label>
    </fieldset>
  </aside>

  <LatticeView viewBox={grid.view.viewBox} {name}>
    {#if showFaces}
      {#each grid.hexes as hx (`${hx.col}-${hx.row}`)}
        <polygon
          class="face"
          points={hx.pointsString}
          fill={hx.color}
          fill-opacity="0.3"
          stroke={hx.color}
          stroke-width="1"
        />
      {/each}
    {/if}
    {#if showEdges}
      {#each grid.edges as e, i (i)}
        <line
          x1={e.p1.x}
          y1={e.p1.y}
          x2={e.p2.x}
          y2={e.p2.y}
          stroke={e.color}
          stroke-width="2.5"
        />
      {/each}
    {/if}
    {#if showLabels}
      {#each grid.hexes as hx (`l-${hx.col}-${hx.row}`)}
        <text
          x={hx.x}
          y={hx.y}
          text-anchor="middle"
          dominant-baseline="central"
          font-size={size * 0.4}
          fill="var(--fg)"
        >{hx.label}</text>
      {/each}
    {/if}
  </LatticeView>
</div>

<style>
  .layout {
    display: flex;
    gap: 18px;
    align-items: stretch;
    height: 100%;
  }

  .sidebar {
    width: 232px;
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 18px;
    overflow-y: auto;
  }

  .head {
    margin-bottom: 2px;
  }

  .sidebar h3 {
    margin: 0;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.01em;
  }

  .sub {
    margin: 3px 0 0;
    font-size: 11.5px;
    color: var(--faint);
    letter-spacing: 0.02em;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 5px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }

  label.chk {
    flex-direction: row;
    align-items: center;
    gap: 9px;
    text-transform: none;
    letter-spacing: 0.01em;
    font-size: 13px;
    font-weight: 400;
    color: var(--fg);
  }

  .colors {
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    padding: 10px 12px 12px;
    margin: 2px 0 0;
    background: color-mix(in srgb, var(--bg-2) 45%, transparent);
  }

  .colors legend {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    padding: 0 6px;
  }

  label.color {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    text-transform: none;
    letter-spacing: 0.01em;
    font-size: 13px;
    font-weight: 400;
    color: var(--fg);
  }

  input[type="color"] {
    width: 40px;
    height: 24px;
    padding: 0;
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    background: transparent;
  }

  .face {
    transition:
      fill-opacity var(--dur-fast) var(--ease-out),
      filter var(--dur-fast) var(--ease-out);
  }

  .face:hover {
    fill-opacity: 0.5;
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--accent) 55%, transparent));
  }
</style>
