<script lang="ts">
  // Square surface-code lattice diagram + its controls. Shares the control-panel
  // chrome (.diagram-*) and the mark styles with the triangular/hex diagrams so
  // all three stay consistent -- see app.css.
  import { buildRect } from "./rect";
  import type {
    DiagramPattern,
    DiagramStart,
    DiagramEdge,
    FaceType,
  } from "./rect";
  import LatticeView from "./LatticeView.svelte";

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

  const PATTERNS: { value: DiagramPattern; label: string }[] = [
    { value: "css", label: "CSS" },
    { value: "xzzx", label: "XZZX" },
  ];
  const STARTS: { value: DiagramStart; label: string }[] = [
    { value: "Z", label: "EVEN-Z (Z-dominated)" },
    { value: "X", label: "EVEN-X (X-dominated)" },
  ];
  const EDGES: { value: DiagramEdge; label: string }[] = [
    { value: "even", label: "Even boundary" },
    { value: "odd", label: "Odd boundary" },
  ];

  // X/Z stabilizer colours, a subset of the color-code A/B/C palette so the three
  // diagrams share a hue language (Z = blue, X = red). XZZX reuses the same two: each
  // plaquette is a conic pinwheel of X (red) / Z (blue) corner wedges.
  let colors = $state({
    Z: "#4cc9f0",
    X: "#ff5d8f",
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

<div class="diagram-layout">
  <aside class="diagram-sidebar glass">
    <header class="head">
      <h3 class="gradient-text">Square surface code</h3>
      <p class="sub">CSS planar code &middot; X/Z plaquettes</p>
    </header>
    <label
      >Stabiliser type
      <select bind:value={pattern}>
        {#each PATTERNS as v (v.value)}
          <option value={v.value}>{v.label}</option>
        {/each}
      </select>
    </label>
    <label
      >Colouring
      <select bind:value={start}>
        {#each STARTS as v (v.value)}
          <option value={v.value}>{v.label}</option>
        {/each}
      </select>
    </label>
    {#if pattern === "css"}
      <label
        >Boundary
        <select bind:value={edge}>
          {#each EDGES as v (v.value)}
            <option value={v.value}>{v.label}</option>
          {/each}
        </select>
      </label>
    {/if}
    <label>Columns (n)<input type="number" min="1" max="20" bind:value={cols} /></label>
    <label>Rows (m)<input type="number" min="1" max="20" bind:value={rows} /></label>
    <label>Cell size<input type="number" min="10" max="120" step="5" bind:value={cellSize} /></label>
    <label class="chk"><input type="checkbox" bind:checked={showFaces} />Faces</label>
    <label class="chk"><input type="checkbox" bind:checked={showQubits} />Data qubits</label>
    <label class="chk"><input type="checkbox" bind:checked={showEdges} />Edges</label>
    <label class="chk"><input type="checkbox" bind:checked={showLabels} />Labels</label>
    <label class="chk"><input type="checkbox" bind:checked={rotated} />Rotated 45&deg;</label>
    <fieldset class="colors">
      <legend>Stabilizer colors</legend>
      <label class="color">Z<input type="color" bind:value={colors.Z} /></label>
      <label class="color">X<input type="color" bind:value={colors.X} /></label>
    </fieldset>
  </aside>

  <LatticeView viewBox={lattice.view.viewBox} {name}>
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
      {#if showQubits}
        {#each lattice.qubits as q (q.id)}
          <circle class="diagram-qubit" cx={q.x} cy={q.y} r={cellSize * 0.09} fill="var(--fg)" />
        {/each}
      {/if}
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
  </LatticeView>
</div>

<style>
  .edge {
    transition: fill-opacity var(--dur-fast) var(--ease-out);
  }

  .edge:hover {
    fill-opacity: 0.6;
  }
</style>
