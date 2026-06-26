<script lang="ts">
  // A reusable SVG view of a 1D repetition code: a row of data qubits with a
  // Z-check sitting in each gap between neighbours, plus two virtual boundary
  // nodes off the ends. Errors (X flips) are click-toggled on the data qubits;
  // lit checks (defects) glow. Optional overlays draw the matching graph edges,
  // a chosen matching, and the correction chains.
  import { C, withAlpha } from "$lib/colors";
  import {
    LEFT,
    RIGHT,
    qubitX,
    gapX,
    chainQubits,
  } from "./matching";

  let {
    d,
    errors,
    defects,
    matching = [],
    correction = null,
    candidateEdges = [],
    hoverEdge = null,
    showBoundary = true,
    showChecks = true,
    interactive = true,
    onToggleQubit,
    onClickDefect,
    height = 150,
  }: {
    d: number;
    errors: boolean[];
    defects: number[];
    matching?: [number, number][];
    correction?: boolean[] | null;
    candidateEdges?: [number, number][];
    hoverEdge?: [number, number] | null;
    showBoundary?: boolean;
    showChecks?: boolean;
    interactive?: boolean;
    onToggleQubit?: (q: number) => void;
    onClickDefect?: (gap: number) => void;
    height?: number;
  } = $props();

  // Layout in a 0..100 x 0..H viewBox with margins for boundary nodes.
  const W = 100;
  const padX = 9;
  const dataY = $derived(height * 0.62);
  const checkY = $derived(height * 0.34);

  function px(t: number): number {
    return padX + t * (W - 2 * padX);
  }

  // node id -> screen point.
  function nodePoint(id: number): { x: number; y: number } {
    if (id === LEFT) {
      return { x: padX * 0.45, y: checkY };
    }
    if (id === RIGHT) {
      return { x: W - padX * 0.45, y: checkY };
    }

    return { x: px(gapX(id, d)), y: checkY };
  }

  const isDefect = $derived(new Set(defects));
  const corrQubits = $derived(
    correction ? correction.map((b, i) => (b ? i : -1)).filter((i) => i >= 0) : [],
  );

  // The arc path for a matching/candidate edge between two graph nodes.
  function edgePath(a: number, b: number): string {
    const pa = nodePoint(a);
    const pb = nodePoint(b);
    const mx = (pa.x + pb.x) / 2;
    const span = Math.abs(pb.x - pa.x);
    const lift = Math.min(checkY * 0.85, 8 + span * 0.45);
    const my = checkY - lift;

    return `M ${pa.x} ${pa.y} Q ${mx} ${my} ${pb.x} ${pb.y}`;
  }
</script>

<svg viewBox={`0 0 ${W} ${height}`} class="repcode" role="img" aria-label="repetition code">
  <!-- correction chains as a soft band under the data row -->
  {#if correction}
    {#each matching as [a, b] (`${a}-${b}`)}
      {@const qs = chainQubits(a, b, d)}
      {#if qs.length}
        <rect
          x={px(qubitX(qs[0], d)) - (0.5 / d) * (W - 2 * padX)}
          y={dataY - 11}
          width={((qs[qs.length - 1] - qs[0] + 1) / d) * (W - 2 * padX)}
          height={22}
          rx={5}
          fill={withAlpha(C.ok, 0.14)}
          stroke={withAlpha(C.ok, 0.4)}
          stroke-width="0.4"
        />
      {/if}
    {/each}
  {/if}

  <!-- the qubit line -->
  <line x1={px(0)} y1={dataY} x2={px(1)} y2={dataY} stroke={C.line} stroke-width="0.6" />

  <!-- candidate / hover edges (matching graph) -->
  {#each candidateEdges as [a, b] (`cand-${a}-${b}`)}
    <path
      d={edgePath(a, b)}
      fill="none"
      stroke={withAlpha(C.muted, 0.32)}
      stroke-width="0.5"
      stroke-dasharray="1.4 1.4"
    />
  {/each}
  {#if hoverEdge}
    <path
      d={edgePath(hoverEdge[0], hoverEdge[1])}
      fill="none"
      stroke={C.accent}
      stroke-width="1.1"
    />
  {/if}

  <!-- chosen matching edges -->
  {#each matching as [a, b] (`m-${a}-${b}`)}
    <path d={edgePath(a, b)} fill="none" stroke={C.accent2} stroke-width="1.3" />
  {/each}

  <!-- boundary nodes -->
  {#if showBoundary}
    {#each [LEFT, RIGHT] as bid (bid)}
      {@const pt = nodePoint(bid)}
      <g class="boundary">
        <rect
          x={pt.x - 2.6}
          y={pt.y - 4}
          width={5.2}
          height={8}
          rx={1.4}
          fill={withAlpha(C.muted, 0.16)}
          stroke={withAlpha(C.muted, 0.5)}
          stroke-width="0.4"
        />
      </g>
    {/each}
  {/if}

  <!-- checks (defects) -->
  {#if showChecks}
    {#each Array(Math.max(0, d - 1)) as _, i (i)}
      {@const pt = nodePoint(i)}
      {@const lit = isDefect.has(i)}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <g
        class="check"
        class:clickable={interactive && onClickDefect}
        onclick={() => onClickDefect?.(i)}
        onkeydown={(e) => {
          if (e.key === "Enter") {
            onClickDefect?.(i);
          }
        }}
        role={interactive && onClickDefect ? "button" : undefined}
        tabindex={interactive && onClickDefect ? 0 : undefined}
      >
        {#if lit}
          <circle cx={pt.x} cy={pt.y} r={5.6} fill={withAlpha(C.defect, 0.22)} />
        {/if}
        <circle
          cx={pt.x}
          cy={pt.y}
          r={3.1}
          fill={lit ? C.defect : C.bg2}
          stroke={lit ? C.defect : withAlpha(C.z, 0.55)}
          stroke-width="0.7"
        />
      </g>
    {/each}
  {/if}

  <!-- data qubits -->
  {#each errors as err, q (q)}
    {@const x = px(qubitX(q, d))}
    {@const inCorr = corrQubits.includes(q)}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <g
      class="qubit"
      class:clickable={interactive && onToggleQubit}
      onclick={() => onToggleQubit?.(q)}
      onkeydown={(e) => {
        if (e.key === "Enter") {
          onToggleQubit?.(q);
        }
      }}
      role={interactive && onToggleQubit ? "button" : undefined}
      tabindex={interactive && onToggleQubit ? 0 : undefined}
    >
      <circle
        cx={x}
        cy={dataY}
        r={4.4}
        fill={err ? withAlpha(C.x, 0.92) : C.data}
        stroke={inCorr ? C.ok : err ? C.x : withAlpha(C.line, 0.9)}
        stroke-width={inCorr ? 1.2 : 0.7}
      />
      {#if err}
        <text x={x} y={dataY + 1.7} class="lbl" text-anchor="middle">X</text>
      {/if}
    </g>
  {/each}
</svg>

<style>
  .repcode {
    width: 100%;
    height: auto;
    display: block;
    touch-action: manipulation;
  }

  .clickable {
    cursor: pointer;
  }

  .qubit.clickable:hover circle,
  .check.clickable:hover circle {
    filter: brightness(1.25);
  }

  .lbl {
    font-size: 4.2px;
    font-weight: 700;
    fill: #1a0b14;
    pointer-events: none;
    font-family: var(--mono, ui-monospace, monospace);
  }

  g:focus {
    outline: none;
  }

  g:focus-visible circle {
    stroke: var(--accent);
    stroke-width: 1.4;
  }
</style>
