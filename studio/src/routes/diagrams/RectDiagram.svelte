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

  // X/Z stabilizer colours, a subset of the color-code A/B/C palette so the
  // three diagrams share a hue language (Z = cyan, X = magenta, XZZX = amber).
  let colors = $state({
    Z: "#4cc9f0",
    X: "#ff5d8f",
    XZZX: "#ffb703",
  });

  function colorOf(type: FaceType | undefined): string {
    if (type === "X") return colors.X;
    if (type === "XZZX") return colors.XZZX;

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
      {#if pattern === "xzzx"}
        <label class="color">XZZX<input type="color" bind:value={colors.XZZX} /></label>
      {/if}
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
      <!-- plaquettes -->
      {#if showFaces}
        {#each lattice.stabilizers as s (s.id)}
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
        {/each}
      {/if}
      {#if showLabels}
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
