<script lang="ts">
  // A small fixed circuit drawn as horizontal wires with gate symbols at each
  // time step, plus a Pauli "frame" overlay: at the scrubbed step, each wire is
  // tagged with the Pauli letter currently riding it (the error propagated up to
  // that point). The injected-fault step is marked. Pure SVG, viewBox-scaled so
  // it never overflows the viewport.
  import { C, withAlpha } from "$lib/colors";
  import { pauliChar, type Pauli } from "./tableau";

  // A gate occupies one column. CX has a control wire and a target wire.
  export interface Op {
    kind: "H" | "CX";
    a: number; // control / sole qubit
    b?: number; // target (CX only)
  }

  let {
    nq,
    ops,
    frame,
    step,
    injectStep,
    injectQubit,
    finalSupport = [],
  }: {
    nq: number;
    ops: Op[];
    frame: Pauli; // the Pauli on the wires AFTER `step` columns
    step: number; // 0..ops.length: how many columns have executed
    injectStep: number;
    injectQubit: number;
    finalSupport?: number[];
  } = $props();

  // geometry
  const COL_W = 64;
  const LEFT_PAD = 70;
  const RIGHT_PAD = 70;
  const ROW_H = 52;
  const TOP_PAD = 26;
  const W = $derived(LEFT_PAD + ops.length * COL_W + RIGHT_PAD);
  const H = $derived(TOP_PAD * 2 + nq * ROW_H);

  function yOf(q: number): number {
    return TOP_PAD + q * ROW_H + ROW_H / 2;
  }
  function xOf(col: number): number {
    // center of column `col` (0-based); the injection marker sits before col 0.
    return LEFT_PAD + col * COL_W + COL_W / 2;
  }

  function letterColor(c: "I" | "X" | "Y" | "Z"): string {
    if (c === "X") {
      return C.x;
    }
    if (c === "Z") {
      return C.z;
    }
    if (c === "Y") {
      return C.y;
    }

    return C.faint;
  }

  // x where the frame is currently sampled: just after `step` columns.
  const frameX = $derived(LEFT_PAD + step * COL_W - 8);
</script>

<svg viewBox="0 0 {W} {H}" class="circuit" role="img" aria-label="syndrome-extraction circuit with propagating Pauli frame">
  <!-- wires -->
  {#each Array(nq) as _, q (q)}
    <line x1={LEFT_PAD - 40} x2={W - 20} y1={yOf(q)} y2={yOf(q)} stroke={C.line} stroke-width="1.5" />
    <text x={LEFT_PAD - 48} y={yOf(q) + 4} class="wlbl" text-anchor="end">q{q}</text>
  {/each}

  <!-- injection marker (a fault placed on a wire before a chosen column) -->
  {#if injectStep >= 0}
    {@const ix = LEFT_PAD + injectStep * COL_W - 18}
    <line x1={ix} x2={ix} y1={TOP_PAD - 6} y2={H - TOP_PAD + 6} stroke={withAlpha(C.accent3, 0.5)} stroke-width="1" stroke-dasharray="3 3" />
    <circle cx={ix} cy={yOf(injectQubit)} r="9" fill={withAlpha(C.accent3, 0.25)} stroke={C.accent3} stroke-width="1.5" />
    <text x={ix} y={TOP_PAD - 10} class="ilbl" text-anchor="middle">fault</text>
  {/if}

  <!-- gates -->
  {#each ops as op, col (col)}
    {@const x = xOf(col)}
    {@const done = col < step}
    <g opacity={done ? 1 : 0.42}>
      {#if op.kind === "H"}
        <rect x={x - 13} y={yOf(op.a) - 13} width="26" height="26" rx="5" fill={C.panel} stroke={C.lineStrong} stroke-width="1.5" />
        <text x={x} y={yOf(op.a) + 5} class="glbl" text-anchor="middle">H</text>
      {:else if op.kind === "CX" && op.b !== undefined}
        <line x1={x} x2={x} y1={yOf(op.a)} y2={yOf(op.b)} stroke={C.lineStrong} stroke-width="1.6" />
        <circle cx={x} cy={yOf(op.a)} r="5" fill={C.fg} />
        <circle cx={x} cy={yOf(op.b)} r="11" fill={C.panel} stroke={C.fg} stroke-width="1.6" />
        <line x1={x - 7} x2={x + 7} y1={yOf(op.b)} y2={yOf(op.b)} stroke={C.fg} stroke-width="1.6" />
        <line x1={x} x2={x} y1={yOf(op.b) - 7} y2={yOf(op.b) + 7} stroke={C.fg} stroke-width="1.6" />
      {/if}
    </g>
  {/each}

  <!-- the propagating Pauli frame: tag each wire with its current Pauli letter -->
  {#each Array(nq) as _, q (q)}
    {@const c = pauliChar(frame.x[q], frame.z[q])}
    {#if c !== "I"}
      <g>
        <rect
          x={frameX - 12}
          y={yOf(q) - 12}
          width="24"
          height="24"
          rx="6"
          fill={withAlpha(letterColor(c), 0.18)}
          stroke={letterColor(c)}
          stroke-width="1.6"
        />
        <text x={frameX} y={yOf(q) + 6} class="frame-lbl" style="fill:{letterColor(c)}" text-anchor="middle">{c}</text>
      </g>
    {/if}
    {#if finalSupport.includes(q)}
      <circle cx={W - 30} cy={yOf(q)} r="6" fill={C.bad} />
    {/if}
  {/each}
</svg>

<style>
  .circuit {
    width: 100%;
    height: auto;
    max-height: 360px;
    display: block;
  }

  .wlbl,
  .ilbl {
    font-size: 11px;
    fill: var(--muted);
    font-family: ui-monospace, monospace;
  }

  .ilbl {
    fill: var(--accent-3);
    font-size: 9px;
  }

  .glbl {
    font-size: 14px;
    font-weight: 700;
    fill: var(--fg);
    font-family: ui-monospace, monospace;
  }

  .frame-lbl {
    font-size: 15px;
    font-weight: 700;
    font-family: ui-monospace, monospace;
  }
</style>
