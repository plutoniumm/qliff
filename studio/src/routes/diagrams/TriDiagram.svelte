<script lang="ts">
  // Triangular lattice diagram (with Kagome / medial variant) + controls. Shares
  // the .diagram-* control chrome + mark styles with the square/hex diagrams.
  import { buildTri } from "./tri";
  import type { TriColorMap } from "./tri";
  import LatticeView from "./LatticeView.svelte";

  let cols = $state(5);
  let rows = $state(4);
  let size = $state(60);
  let showFaces = $state(true);
  let showVertices = $state(true);
  let showEdges = $state(true);
  let showLabels = $state(false);
  let kagome = $state(false);

  // shared phase-wheel palette (cyan / violet / magenta) -- matches the hex
  // color code and the square X/Z subset.
  let colors = $state<TriColorMap>({
    A: "#4cc9f0",
    B: "#8b6cff",
    C: "#ff5d8f",
  });

  let lattice = $derived(buildTri(rows, cols, size, colors, kagome));
  let name = $derived(`${kagome ? "kagome" : "triangular"}_${cols}x${rows}`);
</script>

<div class="diagram-layout">
  <aside class="diagram-sidebar glass">
    <header class="head">
      <h3 class="gradient-text">{kagome ? "Kagome lattice" : "Triangular lattice"}</h3>
      <p class="sub">{kagome ? "Medial (line) graph" : "3-colorable faces"}</p>
    </header>
    <label>Columns<input type="number" min="1" max="20" bind:value={cols} /></label>
    <label>Rows<input type="number" min="1" max="20" bind:value={rows} /></label>
    <label>Size<input type="number" min="10" max="120" step="5" bind:value={size} /></label>
    <label class="chk"><input type="checkbox" bind:checked={showFaces} />Faces</label>
    <label class="chk"><input type="checkbox" bind:checked={showVertices} />Data qubits</label>
    <label class="chk"><input type="checkbox" bind:checked={showEdges} />Edges</label>
    <label class="chk"><input type="checkbox" bind:checked={showLabels} />Labels</label>
    <label class="chk"><input type="checkbox" bind:checked={kagome} />Kagome (medial)</label>
    <fieldset class="colors">
      <legend>Face colors</legend>
      <label class="color">A<input type="color" bind:value={colors.A} /></label>
      <label class="color">B<input type="color" bind:value={colors.B} /></label>
      <label class="color">C<input type="color" bind:value={colors.C} /></label>
    </fieldset>
  </aside>

  <LatticeView viewBox={lattice.view.viewBox} {name}>
    {#if showFaces}
      {#each lattice.faces as f, i (i)}
        <polygon
          class="diagram-face"
          points={f.pointsString}
          fill={f.color}
          fill-opacity="0.28"
          stroke={f.color}
          stroke-width="1"
        />
      {/each}
    {/if}
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
    {#if showVertices}
      {#each lattice.vertices as v (v.id)}
        <circle class="diagram-qubit" cx={v.x} cy={v.y} r={size * 0.09} fill="var(--fg)" />
      {/each}
    {/if}
  </LatticeView>
</div>
