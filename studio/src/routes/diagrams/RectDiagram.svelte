<script lang="ts">
  // Square surface-code lattice diagram. Shares the sidebar chrome + the data-qubit
  // render loop with the triangular / hex diagrams via DiagramShell; keeps its own
  // marks (boundary half-circles, CSS/XZZX plaquettes + wedges) since those have no
  // counterpart in the other two. The face polygons + face labels are drawn here,
  // wrapped in the optional 45-degree rotation group.
  import { buildRect } from "./rect";
  import type {
    DiagramPattern,
    DiagramStart,
    DiagramEdge,
    FaceType,
  } from "./rect";
  import { PATTERN_OPTIONS, START_OPTIONS, EDGE_OPTIONS } from "$lib/variants";
  import DiagramShell, { PHASE_HUES } from "./DiagramShell.svelte";

  let cols = $state(5);
  let rows = $state(5);
  let cellSize = $state(60);
  let showFaces = $state(true);
  let showQubits = $state(true);
  let showEdges = $state(true);
  let showLabels = $state(false);
  let rotated = $state(false);
  // Stabiliser-pattern knobs, mirroring the runnable surface variants: the CSS vs
  // XZZX type, the EVEN-Z / EVEN-X colouring, and the boundary edge set.
  let pattern = $state<DiagramPattern>("css");
  let start = $state<DiagramStart>("Z");
  let edge = $state<DiagramEdge>("even");

  // X/Z stabilizer colours, the Z / X ends of the shared phase-wheel palette (Z = the
  // A/cyan hue, X = the C/magenta hue). XZZX reuses the same two: each plaquette is a
  // conic pinwheel of X (magenta) / Z (cyan) corner wedges.
  let colors = $state({
    Z: PHASE_HUES.A,
    X: PHASE_HUES.C,
  });

  function colorOf(type: FaceType | undefined): string {
    if (type === "X") return colors.X;

    return colors.Z;
  }

  let lattice = $derived(
    buildRect(cols, rows, cellSize, showEdges, rotated, pattern, start, edge),
  );
  let groupTransform = $derived(
    rotated
      ? `rotate(45 ${(cols * cellSize) / 2} ${(rows * cellSize) / 2})`
      : "",
  );
  let name = $derived(`surface_code_${pattern}_${start}_${edge}_${cols}x${rows}`);
</script>

<DiagramShell
  title="Square surface code"
  colorLegend="Stabilizer colors"
  viewBox={lattice.view.viewBox}
  {name}
  bind:showFaces
  bind:showVertices={showQubits}
  bind:showEdges
  bind:showLabels
>
  {#snippet subtitle()}CSS planar code &middot; X/Z plaquettes{/snippet}
  {#snippet controls()}
    <label
      >Stabiliser type
      <select bind:value={pattern}>
        {#each PATTERN_OPTIONS as v (v.value)}
          <option value={v.value}>{v.label}</option>
        {/each}
      </select>
    </label>
    <label
      >Colouring
      <select bind:value={start}>
        {#each START_OPTIONS as v (v.value)}
          <option value={v.value}>{v.label}</option>
        {/each}
      </select>
    </label>
    {#if pattern === "css"}
      <label
        >Boundary
        <select bind:value={edge}>
          {#each EDGE_OPTIONS as v (v.value)}
            <option value={v.value}>{v.label}</option>
          {/each}
        </select>
      </label>
    {/if}
    <label>Columns (n)<input type="number" min="1" max="20" bind:value={cols} /></label>
    <label>Rows (m)<input type="number" min="1" max="20" bind:value={rows} /></label>
    <label>Cell size<input type="number" min="10" max="120" step="5" bind:value={cellSize} /></label>
  {/snippet}
  {#snippet extraChecks()}
    <label class="chk"><input type="checkbox" bind:checked={rotated} />Rotated 45&deg;</label>
  {/snippet}
  {#snippet colorPickers()}
    <label class="color">Z<input type="color" bind:value={colors.Z} /></label>
    <label class="color">X<input type="color" bind:value={colors.X} /></label>
  {/snippet}
  {#snippet children(qubits)}
    <g transform={groupTransform}>
      <!-- boundary half-circle markers -->
      {#if showEdges}
        {#each lattice.edges as e (e.path)}
          <path
            class="edge"
            d={e.path}
            fill={colorOf(e.type)}
            fill-opacity="0.35"
            stroke={colorOf(e.type)}
            stroke-width="1.5"
          />
        {/each}
      {/if}
      <!-- plaquettes: CSS faces are one flat X/Z tile; XZZX faces are a conic
           pinwheel of four corner wedges (red X / blue Z) showing the mixed check. -->
      {#if showFaces}
        {#each lattice.stabilizers as s (s.id)}
          {#if s.wedges}
            {#each s.wedges as w, i (`${s.id}-w${i}`)}
              <path
                class="diagram-face"
                d={w.path}
                fill={colorOf(w.pauli)}
                fill-opacity="0.4"
                stroke="var(--bg)"
                stroke-width="0.75"
              />
            {/each}
            <rect
              x={s.x}
              y={s.y}
              width={cellSize}
              height={cellSize}
              fill="none"
              stroke={colorOf("X")}
              stroke-opacity="0.4"
              stroke-width="1"
            />
          {:else}
            <rect
              class="diagram-face"
              x={s.x}
              y={s.y}
              width={cellSize}
              height={cellSize}
              fill={colorOf(s.type)}
              fill-opacity="0.28"
              stroke={colorOf(s.type)}
              stroke-width="1.5"
            />
          {/if}
        {/each}
      {/if}
      <!-- CSS plaquettes carry one X/Z glyph each; XZZX puts its structure on the
           qubits instead (see the per-qubit labels below), so skip the face glyph. -->
      {#if showLabels && pattern !== "xzzx"}
        {#each lattice.stabilizers as s (`l-${s.id}`)}
          <text
            x={s.x + cellSize / 2}
            y={s.y + cellSize / 2}
            text-anchor="middle"
            dominant-baseline="central"
            font-size={cellSize * 0.3}
            fill="var(--fg)"
          >{s.type}</text>
        {/each}
      {/if}
      <!-- data qubits -->
      {#if showQubits}{@render qubits(lattice.qubits, cellSize * 0.09)}{/if}
      <!-- XZZX: every plaquette is X-Z-Z-X, so the X/Z lives on each data qubit.
           Small per-qubit labels, colour-coded, keep the dense pattern readable. -->
      {#if showLabels && pattern === "xzzx"}
        {#each lattice.qubits as q (`p-${q.id}`)}
          <text
            x={q.x}
            y={q.y - cellSize * 0.18}
            text-anchor="middle"
            dominant-baseline="central"
            font-size={cellSize * 0.2}
            font-weight="700"
            fill={colorOf(q.pauli)}
          >{q.pauli}</text>
        {/each}
      {/if}
    </g>
  {/snippet}
</DiagramShell>

<style>
  .edge {
    transition: fill-opacity var(--dur-fast) var(--ease-out);
  }

  .edge:hover {
    fill-opacity: 0.6;
  }
</style>
