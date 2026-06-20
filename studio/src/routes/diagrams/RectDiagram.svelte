<script lang="ts">
  // Square surface-code lattice diagram + its controls.
  import { buildRect, defaultParity } from "./rect";
  import LatticeView from "./LatticeView.svelte";

  let cols = $state(5);
  let rows = $state(5);
  let cellSize = $state(60);
  let showQubits = $state(true);
  let showEdges = $state(true);
  let showLabels = $state(false);
  let rotated = $state(false);

  let lattice = $derived(
    buildRect(cols, rows, cellSize, showEdges, rotated, defaultParity),
  );
  let groupTransform = $derived(
    rotated
      ? `rotate(45 ${(cols * cellSize) / 2} ${(rows * cellSize) / 2})`
      : "",
  );
  let name = $derived(`surface_code_${cols}x${rows}`);
</script>

<div class="layout">
  <aside class="sidebar glass">
    <header class="head">
      <h3 class="gradient-text">Square surface code</h3>
      <p class="sub">CSS planar code &middot; X/Z plaquettes</p>
    </header>
    <label>Columns (n)<input type="number" min="1" max="20" bind:value={cols} /></label>
    <label>Rows (m)<input type="number" min="1" max="20" bind:value={rows} /></label>
    <label>Cell size<input type="number" min="10" max="120" step="5" bind:value={cellSize} /></label>
    <label class="chk"><input type="checkbox" bind:checked={showQubits} />Data qubits</label>
    <label class="chk"><input type="checkbox" bind:checked={showEdges} />Boundary edges</label>
    <label class="chk"><input type="checkbox" bind:checked={showLabels} />Labels</label>
    <label class="chk"><input type="checkbox" bind:checked={rotated} />Rotated 45&deg;</label>
    <p class="legend">
      <span class="chip z"><span class="swatch z"></span>Z stabilizer</span>
      <span class="chip x"><span class="swatch x"></span>X stabilizer</span>
    </p>
  </aside>

  <LatticeView viewBox={lattice.view.viewBox} {name}>
    <g transform={groupTransform}>
      <!-- boundary half-circle markers -->
      {#each lattice.edges as e (e.path)}
        <path
          class="edge"
          d={e.path}
          fill={e.type === "X" ? "var(--x)" : "var(--z)"}
          fill-opacity="0.35"
          stroke={e.type === "X" ? "var(--x)" : "var(--z)"}
          stroke-width="1.5"
        />
      {/each}
      <!-- plaquettes -->
      {#each lattice.stabilizers as s (s.id)}
        <rect
          class="plaq"
          x={s.x}
          y={s.y}
          width={cellSize}
          height={cellSize}
          fill={s.type === "X" ? "var(--x)" : "var(--z)"}
          fill-opacity="0.18"
          stroke={s.type === "X" ? "var(--x)" : "var(--z)"}
          stroke-width="1.5"
        />
      {/each}
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
          <circle class="qubit" cx={q.x} cy={q.y} r={cellSize * 0.1} fill="var(--fg)" />
        {/each}
      {/if}
    </g>
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

  .legend {
    margin: 6px 0 0;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 12px;
    color: var(--fg);
    padding: 4px 10px 4px 8px;
    border-radius: 99px;
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
    border: 1px solid var(--line);
  }

  .swatch {
    width: 11px;
    height: 11px;
    border-radius: 4px;
    display: inline-block;
  }

  .swatch.x {
    background: var(--x);
    box-shadow: 0 0 10px -1px color-mix(in srgb, var(--x) 75%, transparent);
  }

  .swatch.z {
    background: var(--z);
    box-shadow: 0 0 10px -1px color-mix(in srgb, var(--z) 75%, transparent);
  }

  .plaq {
    transition:
      fill-opacity var(--dur-fast) var(--ease-out),
      filter var(--dur-fast) var(--ease-out);
  }

  .plaq:hover {
    fill-opacity: 0.4;
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--accent) 60%, transparent));
  }

  .edge {
    transition: fill-opacity var(--dur-fast) var(--ease-out);
  }

  .edge:hover {
    fill-opacity: 0.6;
  }

  .qubit {
    filter: drop-shadow(0 0 3px color-mix(in srgb, var(--fg) 55%, transparent));
  }
</style>
