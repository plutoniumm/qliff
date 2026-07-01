<script lang="ts">
  // Honeycomb (color-code) lattice diagram. Three face colors are user-adjustable;
  // edges inherit the third color (color-code structure); data qubits sit on the
  // hexagon corners. All the sidebar chrome + the qubit / face render loops live in
  // DiagramShell; this file keeps only the honeycomb-specific wiring.
  import { Grid } from "./hex";
  import type { ColorMap, LabelMap } from "./hex";
  import DiagramShell, { PHASE_HUES } from "./DiagramShell.svelte";

  let cols = $state(5);
  let rows = $state(4);
  let size = $state(40);
  let showFaces = $state(true);
  let showVertices = $state(true);
  let showEdges = $state(true);
  let showLabels = $state(false);

  let colors = $state<ColorMap>({ ...PHASE_HUES });
  const labels: LabelMap = {
    A: "A",
    B: "B",
    C: "C",
  };

  let grid = $derived(Grid(rows, cols, size, colors, labels));
  let name = $derived(`color_code_${cols}x${rows}`);
</script>

<DiagramShell
  title="Hexagonal color code"
  colorLegend="Face colors"
  viewBox={grid.view.viewBox}
  {name}
  bind:showFaces
  bind:showVertices
  bind:showEdges
  bind:showLabels
>
  {#snippet subtitle()}3-colorable honeycomb &middot; CSS{/snippet}
  {#snippet controls()}
    <label>Columns<input type="number" min="1" max="20" bind:value={cols} /></label>
    <label>Rows<input type="number" min="1" max="20" bind:value={rows} /></label>
    <label>Size<input type="number" min="10" max="80" step="5" bind:value={size} /></label>
  {/snippet}
  {#snippet colorPickers()}
    <label class="color">A<input type="color" bind:value={colors.A} /></label>
    <label class="color">B<input type="color" bind:value={colors.B} /></label>
    <label class="color">C<input type="color" bind:value={colors.C} /></label>
  {/snippet}
  {#snippet children(qubits, faces)}
    {#if showFaces}{@render faces(grid.hexes)}{/if}
    {#if showEdges}
      {#each grid.edges as e, i (i)}
        <line x1={e.p1.x} y1={e.p1.y} x2={e.p2.x} y2={e.p2.y} stroke={e.color} stroke-width="2.5" />
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
    {#if showVertices}{@render qubits(grid.vertices, size * 0.09)}{/if}
  {/snippet}
</DiagramShell>
