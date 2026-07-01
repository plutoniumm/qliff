<script lang="ts">
  // Triangular lattice diagram (with Kagome / medial variant). All the sidebar
  // chrome + the qubit / face render loops live in DiagramShell; this file keeps
  // only the triangular-specific wiring (kagome toggle, edges + face labels).
  import { buildTri } from "./tri";
  import type { TriColorMap } from "./tri";
  import DiagramShell, { PHASE_HUES } from "./DiagramShell.svelte";

  let cols = $state(5);
  let rows = $state(4);
  let size = $state(60);
  let showFaces = $state(true);
  let showVertices = $state(true);
  let showEdges = $state(true);
  let showLabels = $state(false);
  let kagome = $state(false);

  let colors = $state<TriColorMap>({ ...PHASE_HUES });

  let lattice = $derived(buildTri(rows, cols, size, colors, kagome));
  let name = $derived(`${kagome ? "kagome" : "triangular"}_${cols}x${rows}`);
</script>

<DiagramShell
  title={kagome ? "Kagome lattice" : "Triangular lattice"}
  colorLegend="Face colors"
  viewBox={lattice.view.viewBox}
  {name}
  bind:showFaces
  bind:showVertices
  bind:showEdges
  bind:showLabels
>
  {#snippet subtitle()}{kagome ? "Medial (line) graph" : "3-colorable faces"}{/snippet}
  {#snippet controls()}
    <label>Columns<input type="number" min="1" max="20" bind:value={cols} /></label>
    <label>Rows<input type="number" min="1" max="20" bind:value={rows} /></label>
    <label>Size<input type="number" min="10" max="120" step="5" bind:value={size} /></label>
  {/snippet}
  {#snippet extraChecks()}
    <label class="chk"><input type="checkbox" bind:checked={kagome} />Kagome (medial)</label>
  {/snippet}
  {#snippet colorPickers()}
    <label class="color">A<input type="color" bind:value={colors.A} /></label>
    <label class="color">B<input type="color" bind:value={colors.B} /></label>
    <label class="color">C<input type="color" bind:value={colors.C} /></label>
  {/snippet}
  {#snippet children(qubits, faces)}
    {#if showFaces}{@render faces(lattice.faces)}{/if}
    {#if showEdges}
      {#each lattice.edges as e, i (i)}
        <line
          x1={e.p1.x}
          y1={e.p1.y}
          x2={e.p2.x}
          y2={e.p2.y}
          stroke="var(--line)"
          stroke-width="1.5"
        />
      {/each}
    {/if}
    {#if showLabels}
      {#each lattice.faces as f, i (`l-${i}`)}
        <text
          x={f.cx}
          y={f.cy}
          text-anchor="middle"
          dominant-baseline="central"
          font-size={size * 0.22}
          fill="var(--fg)"
        >{f.colorKey}</text>
      {/each}
    {/if}
    {#if showVertices}{@render qubits(lattice.vertices, size * 0.09)}{/if}
  {/snippet}
</DiagramShell>
