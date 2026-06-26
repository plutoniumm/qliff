<script lang="ts">
  // A bipartite Tanner / factor graph drawn in SVG. Variable nodes (error
  // mechanisms) sit on top as circles; check nodes (detectors) sit below as
  // squares. An edge joins variable m to check c iff H[c][m] = 1. The component
  // is a PURE render of its props -- it never writes state in an effect -- so
  // the parent can scrub BP iterations and feed a different `frame` each time.
  import { C, withAlpha, heat } from "$lib/colors";
  import { pFromLlr, type Code, type BpFrame } from "./bp";

  let {
    code,
    syndrome = [],
    trueError = [],
    frame = null,
    showMessages = false,
    hover = $bindable(null),
    height = 260,
  }: {
    code: Code;
    syndrome?: number[];
    trueError?: number[];
    frame?: BpFrame | null;
    showMessages?: boolean;
    hover?: { kind: "var" | "check"; idx: number } | null;
    height?: number;
  } = $props();

  const width = 720;
  const padX = 56;
  const varY = 78;
  const checkY = $derived(height - 78);

  // Even horizontal spread for each layer.
  function xs(n: number): number[] {
    if (n === 1) {
      return [width / 2];
    }
    const span = width - 2 * padX;

    return Array.from({ length: n }, (_, i) => padX + (span * i) / (n - 1));
  }

  const varX = $derived(xs(code.nVars));
  const checkX = $derived(xs(code.nChecks));

  // Edge list with endpoints, plus the two BP messages riding on it.
  interface EdgeView {
    m: number;
    c: number;
    x1: number;
    y1: number;
    x2: number;
    y2: number;
    v2c: number; // variable -> check message
    c2v: number; // check -> variable message
  }

  const edges = $derived.by((): EdgeView[] => {
    const out: EdgeView[] = [];
    for (let c = 0; c < code.nChecks; c += 1) {
      for (const m of code.checkNeighbours[c]) {
        out.push({
          m,
          c,
          x1: varX[m],
          y1: varY,
          x2: checkX[c],
          y2: checkY,
          v2c: frame?.varToCheck.get(`${m},${c}`) ?? 0,
          c2v: frame?.checkToVar.get(`${c},${m}`) ?? 0,
        });
      }
    }

    return out;
  });

  // Map a message magnitude to a 0..1 intensity for heat()/width. Messages are
  // log-ratios; ~6 nats is already a very confident message.
  function intensity(mag: number): number {
    return Math.min(1, Math.abs(mag) / 6);
  }

  function isLit(c: number): boolean {
    return (syndrome[c] ?? 0) === 1;
  }

  function isHotEdge(e: EdgeView): boolean {
    if (!hover) {
      return false;
    }

    return (
      (hover.kind === "var" && hover.idx === e.m) ||
      (hover.kind === "check" && hover.idx === e.c)
    );
  }

  function dim(e: EdgeView): number {
    return hover && !isHotEdge(e) ? 0.18 : 1;
  }

  // Belief readout per variable: posterior probability of firing, 0..1.
  const beliefP = $derived(
    frame ? frame.posterior.map((l) => pFromLlr(l)) : code.priors.map(() => 0),
  );

  function setHover(kind: "var" | "check", idx: number): void {
    hover = { kind, idx };
  }

  function clearHover(): void {
    hover = null;
  }
</script>

<svg viewBox="0 0 {width} {height}" class="tanner" role="img" aria-label="Tanner graph">
  <!-- layer captions -->
  <text x={padX - 30} y={varY - 40} class="cap">mechanisms</text>
  <text x={padX - 30} y={varY - 24} class="cap sub">(possible errors)</text>
  <text x={padX - 30} y={checkY + 44} class="cap">detectors</text>
  <text x={padX - 30} y={checkY + 60} class="cap sub">(parity checks)</text>

  <!-- edges -->
  {#each edges as e (`${e.m}-${e.c}`)}
    <line
      x1={e.x1}
      y1={e.y1}
      x2={e.x2}
      y2={e.y2}
      stroke={withAlpha(C.line, dim(e))}
      stroke-width={isHotEdge(e) ? 2 : 1}
    />
  {/each}

  <!-- messages: little dots gliding along each edge, sized + coloured by
       magnitude. Check->var dots sit nearer the variable; var->check nearer
       the check, so both directions are visible at once. -->
  {#if showMessages && frame}
    {#each edges as e (`msg-${e.m}-${e.c}`)}
      {@const iC = intensity(e.c2v)}
      {@const iV = intensity(e.v2c)}
      <!-- check -> variable (riding up toward the mechanism) -->
      <circle
        cx={e.x1 + (e.x2 - e.x1) * 0.32}
        cy={e.y1 + (e.y2 - e.y1) * 0.32}
        r={1.6 + 4.4 * iC}
        fill={withAlpha(heat(iC), 0.85 * dim(e))}
      />
      <!-- variable -> check (riding down toward the detector) -->
      <circle
        cx={e.x1 + (e.x2 - e.x1) * 0.68}
        cy={e.y1 + (e.y2 - e.y1) * 0.68}
        r={1.6 + 4.4 * iV}
        fill={withAlpha(heat(iV), 0.55 * dim(e))}
      />
    {/each}
  {/if}

  <!-- check (detector) nodes -->
  {#each Array(code.nChecks) as _, c (c)}
    {@const lit = isLit(c)}
    {@const unsat = frame ? (frame.residual[c] ?? 0) === 1 : false}
    <g
      role="button"
      tabindex="0"
      onmouseenter={() => setHover("check", c)}
      onmouseleave={clearHover}
      onfocus={() => setHover("check", c)}
      onblur={clearHover}
    >
      <rect
        x={checkX[c] - 13}
        y={checkY - 13}
        width="26"
        height="26"
        rx="5"
        fill={lit ? withAlpha(C.defect, 0.22) : withAlpha(C.panel, 0.9)}
        stroke={unsat ? C.bad : lit ? C.defect : C.lineStrong}
        stroke-width={unsat ? 2.5 : lit ? 2 : 1.2}
      />
      <text x={checkX[c]} y={checkY + 1} class="node-label" fill={lit ? C.defect : C.muted}>
        d{c}
      </text>
    </g>
  {/each}

  <!-- variable (mechanism) nodes + belief ring -->
  {#each Array(code.nVars) as _, m (m)}
    {@const fired = frame ? (frame.hard[m] ?? 0) === 1 : false}
    {@const isTrue = (trueError[m] ?? 0) === 1}
    {@const p = beliefP[m]}
    <g
      role="button"
      tabindex="0"
      onmouseenter={() => setHover("var", m)}
      onmouseleave={clearHover}
      onfocus={() => setHover("var", m)}
      onblur={clearHover}
    >
      <!-- belief ring: arc length tracks posterior P(fired) -->
      <circle
        cx={varX[m]}
        cy={varY}
        r="17"
        fill="none"
        stroke={withAlpha(heat(p), 0.9)}
        stroke-width="3"
        stroke-dasharray="{(2 * Math.PI * 17 * p).toFixed(1)} 999"
        transform="rotate(-90 {varX[m]} {varY})"
      />
      <circle
        cx={varX[m]}
        cy={varY}
        r="13"
        fill={fired ? withAlpha(C.bad, 0.28) : withAlpha(C.panel, 0.95)}
        stroke={fired ? C.bad : isTrue ? C.accent2 : C.data}
        stroke-width={fired ? 2.4 : isTrue ? 2 : 1.2}
      />
      <text x={varX[m]} y={varY + 1} class="node-label" fill={fired ? C.bad : C.data}>
        e{m}
      </text>
      {#if isTrue}
        <text x={varX[m]} y={varY - 26} class="truth">true</text>
      {/if}
    </g>
  {/each}
</svg>

<style>
  .tanner {
    width: 100%;
    height: auto;
    max-height: 320px;
    display: block;
    overflow: visible;
  }

  .node-label {
    font-family: var(--mono, ui-monospace, monospace);
    font-size: 10.5px;
    text-anchor: middle;
    dominant-baseline: middle;
    pointer-events: none;
    font-weight: 600;
  }

  .cap {
    font-size: 11px;
    fill: var(--faint);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .cap.sub {
    font-size: 9.5px;
    opacity: 0.7;
    text-transform: none;
    letter-spacing: 0;
  }

  .truth {
    font-size: 9px;
    text-anchor: middle;
    fill: var(--accent-2, #4cc9f0);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  g[role="button"] {
    cursor: pointer;
    outline: none;
  }
</style>
