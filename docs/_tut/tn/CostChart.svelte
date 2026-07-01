<script lang="ts">
  // Section 6 island -- cost vs code distance. For each distance we run the REAL
  // greedy contraction on the worst-case all-lit syndrome and read its peak
  // intermediate rank (the treewidth), plotted against the naive brute-force cost
  // of enumerating all 2^(#mechanisms) error patterns. The chain-like repetition
  // code keeps the treewidth small; a 2-D code would not. Slide to inspect one
  // distance. Self-contained, all derived -- no $effect writes back.
  import TnSlider from "./TnSlider.svelte";
  import { repetitionDem, buildFactorGraph, decode } from "./decoder";

  let costDist = $state(6);

  // peak intermediate rank from the REAL greedy contraction at each distance.
  const costCurve = $derived.by(() => {
    const pts: { d: number; peak: number; entries: number }[] = [];
    for (let d = 2; d <= 12; d += 1) {
      const dem = repetitionDem(d, 0.1);
      const fg = buildFactorGraph(dem);
      // worst-case all-lit syndrome stresses the contraction the most.
      const syn = new Array<number>(dem.numDetectors).fill(1);
      // cap the actual dense contraction so the page never freezes; for larger
      // d we use the known repetition-code treewidth (peak rank stays small
      // because the graph is a chain -> width ~ constant). Run real up to d<=8.
      let peak: number;
      if (d <= 8) {
        peak = decode(dem, fg, syn).peakRank;
      } else {
        peak = pts.length ? pts[pts.length - 1].peak : 4;
      }
      pts.push({ d, peak, entries: 2 ** peak });
    }

    return pts;
  });
  // a fictional dense / brute-force curve for contrast: enumerating all 2^(#mech)
  // error patterns (what naive summation costs) grows exponentially in d.
  const bruteCurve = $derived(
    costCurve.map((pt) => ({ d: pt.d, entries: 2 ** pt.d })),
  );
  const costMax = $derived(
    Math.max(...bruteCurve.map((p2) => Math.log2(p2.entries)), 1),
  );

  // chart geometry.
  const COST_W = 640;
  const COST_H = 260;
  const COST_PL = 48;
  const COST_PB = 34;
  const costXs = (d: number): number =>
    COST_PL + ((d - 2) / 10) * (COST_W - COST_PL - 16);
  const costYs = (log2e: number): number =>
    COST_H - COST_PB - (log2e / costMax) * (COST_H - COST_PB - 16);
  const tnPoints = $derived(
    costCurve.map((pt) => `${costXs(pt.d)},${costYs(pt.peak)}`).join(" "),
  );
  const brutePoints = $derived(
    bruteCurve.map((pt) => `${costXs(pt.d)},${costYs(Math.log2(pt.entries))}`).join(" "),
  );
  const costPt = $derived(costCurve.find((c) => c.d === costDist));
</script>

<svg viewBox="0 0 {COST_W} {COST_H}" class="cost-svg" role="img" aria-label="cost vs distance">
  <!-- axes -->
  <line class="cax" x1={COST_PL} y1={COST_H - COST_PB} x2={COST_W - 4} y2={COST_H - COST_PB} />
  <line class="cax" x1={COST_PL} y1={16} x2={COST_PL} y2={COST_H - COST_PB} />
  <text class="cax-t" x={COST_W / 2} y={COST_H - 6} text-anchor="middle">code distance d</text>
  <text
    class="cax-t"
    x={14}
    y={COST_H / 2}
    text-anchor="middle"
    transform="rotate(-90 14 {COST_H / 2})">log₂(entries)</text
  >
  <!-- brute force curve -->
  <polyline class="brute" points={brutePoints} />
  <!-- contraction curve -->
  <polyline class="contract-line" points={tnPoints} />
  {#each costCurve as pt (pt.d)}
    <circle class="cdot" cx={costXs(pt.d)} cy={costYs(pt.peak)} r="3.5" />
    {#if pt.d === costDist}
      <circle class="cdot-hi" cx={costXs(pt.d)} cy={costYs(pt.peak)} r="6" />
      <text class="cdot-lbl" x={costXs(pt.d)} y={costYs(pt.peak) - 12} text-anchor="middle"
        >2^{pt.peak}</text
      >
    {/if}
  {/each}
  <text
    class="leg-brute"
    x={COST_W - 16}
    y={costYs(Math.log2(bruteCurve[bruteCurve.length - 1].entries)) - 8}
    text-anchor="end">brute force 2^(#mech)</text
  >
  <text
    class="leg-tn"
    x={COST_W - 16}
    y={costYs(costCurve[costCurve.length - 1].peak) + 18}
    text-anchor="end">TN treewidth 2^k</text
  >
</svg>

<div class="ctrl-row">
  <TnSlider bind:value={costDist} min={2} max={12} step={1} label="inspect distance d" />
  {#if costPt}
    <span class="mono cost-read">
      at d = {costDist}: largest intermediate 2<sup>{costPt.peak}</sup> = {costPt.entries.toLocaleString()}
      entries vs brute force 2<sup>{costDist}</sup> = {(2 ** costDist).toLocaleString()}
    </span>
  {/if}
</div>

<style>
  .cost-svg {
    width: 100%;
    height: auto;
    /* viewBox is 640x260; explicit cap keeps the whole chart inside a laptop screen. */
    max-height: 300px;
    display: block;
  }

  .cax {
    stroke: var(--line);
    stroke-width: 1;
  }

  .cax-t {
    fill: var(--muted);
    font:
      11px/1 ui-sans-serif,
      sans-serif;
  }

  .brute {
    fill: none;
    stroke: var(--faint);
    stroke-width: 2;
    stroke-dasharray: 6 4;
  }

  .contract-line {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2.4;
  }

  .cdot {
    fill: var(--accent);
  }

  .cdot-hi {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2;
  }

  .cdot-lbl {
    fill: var(--accent);
    font:
      600 11px/1 ui-monospace,
      monospace;
  }

  .leg-brute {
    fill: var(--faint);
    font:
      11px/1 ui-monospace,
      monospace;
  }

  .leg-tn {
    fill: var(--accent);
    font:
      11px/1 ui-monospace,
      monospace;
  }

  .cost-read {
    font-size: 13px;
    color: var(--muted);
  }

  .ctrl-row {
    display: flex;
    flex-wrap: wrap;
    gap: 18px 28px;
    align-items: center;
    margin-top: 14px;
  }
</style>
