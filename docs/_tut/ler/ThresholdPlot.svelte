<script lang="ts">
  // Hand-rolled log-log SVG plot of LER vs physical rate p, one curve per code
  // distance d. The whole point is the CROSSING at the threshold p_th: below it
  // larger d pushes the LER down, above it larger d pushes it up. A dashed
  // vertical marks p_th and a dotted diagonal marks the break-even line LER = p.
  import { C, withAlpha } from "$lib/colors";

  export interface Curve {
    d: number;
    color: string;
    points: { p: number; ler: number }[];
  }

  let {
    curves,
    pTh,
    pMin = 1e-3,
    pMax = 0.5,
    lerMin = 1e-6,
    lerMax = 1,
    width = 720,
    height = 420,
    showBreakeven = true,
  }: {
    curves: Curve[];
    pTh: number;
    pMin?: number;
    pMax?: number;
    lerMin?: number;
    lerMax?: number;
    width?: number;
    height?: number;
    showBreakeven?: boolean;
  } = $props();

  const pad = { l: 64, r: 18, t: 18, b: 46 };
  const iw = $derived(width - pad.l - pad.r);
  const ih = $derived(height - pad.t - pad.b);

  const lpMin = $derived(Math.log10(pMin));
  const lpMax = $derived(Math.log10(pMax));
  const llMin = $derived(Math.log10(lerMin));
  const llMax = $derived(Math.log10(lerMax));

  function sx(p: number): number {
    return pad.l + ((Math.log10(p) - lpMin) / (lpMax - lpMin)) * iw;
  }
  function sy(ler: number): number {
    const clamped = Math.max(lerMin, Math.min(lerMax, ler));

    return pad.t + (1 - (Math.log10(clamped) - llMin) / (llMax - llMin)) * ih;
  }

  function decade(lo: number, hi: number): number[] {
    const ticks: number[] = [];
    for (let e = Math.ceil(lo); e <= Math.floor(hi); e += 1) {
      ticks.push(Math.pow(10, e));
    }

    return ticks;
  }

  const xTicks = $derived(decade(lpMin, lpMax));
  const yTicks = $derived(decade(llMin, llMax));

  function path(pts: { p: number; ler: number }[]): string {
    return pts
      .filter((pt) => pt.p >= pMin && pt.p <= pMax)
      .map((pt, i) => `${i === 0 ? "M" : "L"}${sx(pt.p).toFixed(1)},${sy(pt.ler).toFixed(1)}`)
      .join(" ");
  }

  // break-even diagonal LER = p, sampled across the visible p-range
  const breakeven = $derived(
    [pMin, pMax].map((p) => ({ x: sx(p), y: sy(p) })),
  );

  function fmtP(p: number): string {
    const e = Math.round(Math.log10(p));

    return `10${sup(e)}`;
  }
  function sup(e: number): string {
    const map: Record<string, string> = {
      "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
      "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    };

    return String(e).split("").map((ch) => map[ch] ?? ch).join("");
  }
</script>

<svg viewBox="0 0 {width} {height}" class="plot" role="img" aria-label="logical error rate versus physical rate, log-log, one curve per code distance">
  <!-- grid -->
  {#each xTicks as t}
    <line x1={sx(t)} y1={pad.t} x2={sx(t)} y2={pad.t + ih} stroke={withAlpha(C.line, 0.6)} stroke-width="1" />
    <text x={sx(t)} y={pad.t + ih + 18} text-anchor="middle" class="tick">{fmtP(t)}</text>
  {/each}
  {#each yTicks as t}
    <line x1={pad.l} y1={sy(t)} x2={pad.l + iw} y2={sy(t)} stroke={withAlpha(C.line, 0.6)} stroke-width="1" />
    <text x={pad.l - 9} y={sy(t) + 4} text-anchor="end" class="tick">{fmtP(t)}</text>
  {/each}

  <!-- break-even diagonal LER = p: "the code is doing nothing" -->
  {#if showBreakeven}
    <line
      x1={breakeven[0].x} y1={breakeven[0].y}
      x2={breakeven[1].x} y2={breakeven[1].y}
      stroke={withAlpha(C.muted, 0.55)} stroke-width="1.5" stroke-dasharray="2 4"
    />
  {/if}

  <!-- threshold marker: the crossing point of the curves -->
  {#if pTh >= pMin && pTh <= pMax}
    {@const near = sx(pTh) > pad.l + iw * 0.6}
    <line x1={sx(pTh)} y1={pad.t} x2={sx(pTh)} y2={pad.t + ih} stroke={C.defect} stroke-width="1.5" stroke-dasharray="5 4" />
    <text
      x={sx(pTh) + (near ? -6 : 6)}
      y={pad.t + 12}
      text-anchor={near ? "end" : "start"}
      class="pth"
      fill={C.defect}
    >p_th = threshold (curves cross)</text>
  {/if}

  <!-- curves -->
  {#each curves as c}
    <path d={path(c.points)} fill="none" stroke={c.color} stroke-width="2.4" stroke-linejoin="round" />
  {/each}

  <!-- distance labels at the left edge of each curve -->
  {#each curves as c}
    {@const first = c.points.find((pt) => pt.p >= pMin)}
    {#if first}
      <text x={sx(first.p) + 5} y={sy(first.ler) - 5} class="dlabel" fill={c.color}>d={c.d}</text>
    {/if}
  {/each}

  <!-- axis frame -->
  <rect x={pad.l} y={pad.t} width={iw} height={ih} fill="none" stroke={C.lineStrong} stroke-width="1" />

  <text x={pad.l + iw / 2} y={height - 8} text-anchor="middle" class="axis">physical error rate p (probability per qubit, log scale)</text>
  <text transform="translate(16,{pad.t + ih / 2}) rotate(-90)" text-anchor="middle" class="axis">logical error rate P_L (log scale)</text>
</svg>

<style>
  /* the tallest plot on the page; specificity beats the global
     `.frame svg:not(.no-vcap)` 62vh cap so this tighter px cap applies and the
     whole crossing fits a laptop viewport; viewBox letterboxes => no distortion */
  svg.plot:not(.no-vcap) {
    width: 100%;
    height: auto;
    max-height: 380px;
    display: block;
  }
  .tick {
    font-size: 11px;
    fill: var(--muted);
    font-family: var(--font-mono);
  }
  .axis {
    font-size: 12px;
    fill: var(--faint);
  }
  .dlabel {
    font-size: 12px;
    font-weight: 700;
    font-family: var(--font-mono);
  }
  .pth {
    font-size: 11px;
    font-weight: 700;
    font-family: var(--font-mono);
  }
</style>
