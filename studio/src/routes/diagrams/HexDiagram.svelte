<script lang="ts">
  // Honeycomb (color-code) lattice diagram + controls. Three face colors are
  // user-adjustable; edges inherit the third color (color-code structure); data
  // qubits sit on the hexagon corners. Shares the .diagram-* control chrome +
  // mark styles with the square/triangular diagrams.
  import { Grid } from "./hex";
  import type { ColorMap, LabelMap } from "./hex";
  import LatticeView from "./LatticeView.svelte";

  let cols = $state(5);
  let rows = $state(4);
  let size = $state(40);
  let showFaces = $state(true);
  let showVertices = $state(true);
  let showEdges = $state(true);
  let showLabels = $state(false);

  // shared phase-wheel palette (cyan / violet / magenta) -- matches the
  // triangular color code and the square X/Z subset.
  let colors = $state<ColorMap>({
    A: "#4cc9f0",
    B: "#8b6cff",
    C: "#ff5d8f",
  });
  const labels: LabelMap = {
    A: "A",
    B: "B",
    C: "C",
  };

  let grid = $derived(Grid(rows, cols, size, colors, labels));
  let name = $derived(`color_code_${cols}x${rows}`);
</script>

<div class="diagram-layout">
  <aside class="diagram-sidebar glass">
    <header class="head">
      <h3 class="gradient-text">Hexagonal color code</h3>
      <p class="sub">3-colorable honeycomb &middot; CSS</p>
    </header>
    <label>Columns<input type="number" min="1" max="20" bind:value={cols} /></label>
    <label>Rows<input type="number" min="1" max="20" bind:value={rows} /></label>
    <label>Size<input type="number" min="10" max="80" step="5" bind:value={size} /></label>
    <label class="chk"><input type="checkbox" bind:checked={showFaces} />Faces</label>
    <label class="chk"><input type="checkbox" bind:checked={showVertices} />Data qubits</label>
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
          class="diagram-face"
          points={hx.pointsString}
          fill={hx.color}
          fill-opacity="0.28"
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
    {#if showVertices}
      {#each grid.vertices as v, i (i)}
        <circle class="diagram-qubit" cx={v.x} cy={v.y} r={size * 0.09} fill="var(--fg)" />
      {/each}
    {/if}
  </LatticeView>
</div>
