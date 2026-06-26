<script lang="ts">
  // A sweep of LER vs p for ONE code: a smooth analytic curve plus seeded
  // Monte-Carlo points with binomial error bars (the real (p, ler, stderr)
  // triples that qliff's `sweep` yields). Log y-axis so sub-threshold suppression
  // is visible; linear x in p for readability of the chosen range.
  import { C, withAlpha } from "$lib/colors";

  export interface MCPoint {
    p: number;
    ler: number;
    stderr: number;
  }

  let {
    curve,
    points,
    pMin,
    pMax,
    lerMin = 1e-5,
    lerMax = 1,
    width = 720,
    height = 380,
  }: {
    curve: { p: number; ler: number }[];
    points: MCPoint[];
    pMin: number;
    pMax: number;
    lerMin?: number;
    lerMax?: number;
    width?: number;
    height?: number;
  } = $props();

  const pad = { l: 62, r: 16, t: 16, b: 42 };
  const iw = $derived(width - pad.l - pad.r);
  const ih = $derived(height - pad.t - pad.b);
  const llMin = $derived(Math.log10(lerMin));
  const llMax = $derived(Math.log10(lerMax));

  function sx(p: number): number {
    return pad.l + ((p - pMin) / (pMax - pMin)) * iw;
  }
  function sy(ler: number): number {
    const c = Math.max(lerMin, Math.min(lerMax, ler));

    return pad.t + (1 - (Math.log10(c) - llMin) / (llMax - llMin)) * ih;
  }

  function yDecades(): number[] {
    const out: number[] = [];
    for (let e = Math.ceil(llMin); e <= Math.floor(llMax); e += 1) {
      out.push(Math.pow(10, e));
    }

    return out;
  }
  const yTicks = $derived(yDecades());

  function xTickVals(): number[] {
    const out: number[] = [];
    const n = 5;
    for (let i = 0; i <= n; i += 1) {
      out.push(pMin + ((pMax - pMin) * i) / n);
    }

    return out;
  }
  const xTicks = $derived(xTickVals());

  const linePath = $derived(
    curve
      .filter((pt) => pt.p >= pMin && pt.p <= pMax)
      .map((pt, i) => `${i === 0 ? "M" : "L"}${sx(pt.p).toFixed(1)},${sy(pt.ler).toFixed(1)}`)
      .join(" "),
  );

  function sup(e: number): string {
    const map: Record<string, string> = {
      "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
      "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    };

    return String(e).split("").map((ch) => map[ch] ?? ch).join("");
  }
</script>

<svg viewBox="0 0 {width} {height}" class="plot" role="img" aria-label="LER versus p sweep with Monte-Carlo error bars">
  {#each yTicks as t}
    <line x1={pad.l} y1={sy(t)} x2={pad.l + iw} y2={sy(t)} stroke={withAlpha(C.line, 0.6)} stroke-width="1" />
    <text x={pad.l - 8} y={sy(t) + 4} text-anchor="end" class="tick">10{sup(Math.round(Math.log10(t)))}</text>
  {/each}
  {#each xTicks as t}
    <text x={sx(t)} y={pad.t + ih + 18} text-anchor="middle" class="tick">{t.toFixed(3)}</text>
  {/each}

  <!-- analytic curve -->
  <path d={linePath} fill="none" stroke={withAlpha(C.accent2, 0.85)} stroke-width="2.2" />

  <!-- Monte-Carlo points with binomial error bars (+/- stderr) -->
  {#each points as pt}
    {@const x = sx(pt.p)}
    {@const yhi = sy(pt.ler + pt.stderr)}
    {@const ylo = sy(Math.max(lerMin, pt.ler - pt.stderr))}
    <line x1={x} y1={yhi} x2={x} y2={ylo} stroke={C.accent} stroke-width="1.5" />
    <line x1={x - 4} y1={yhi} x2={x + 4} y2={yhi} stroke={C.accent} stroke-width="1.5" />
    <line x1={x - 4} y1={ylo} x2={x + 4} y2={ylo} stroke={C.accent} stroke-width="1.5" />
    <circle cx={x} cy={sy(pt.ler)} r="3.4" fill={C.accent} stroke={C.bg} stroke-width="1" />
  {/each}

  <rect x={pad.l} y={pad.t} width={iw} height={ih} fill="none" stroke={C.lineStrong} stroke-width="1" />
  <text x={pad.l + iw / 2} y={height - 6} text-anchor="middle" class="axis">physical error rate p (probability per bit)</text>
  <text transform="translate(15,{pad.t + ih / 2}) rotate(-90)" text-anchor="middle" class="axis">logical error rate P_L (log scale)</text>
</svg>

<style>
  /* specificity beats the global `.frame svg:not(.no-vcap)` 62vh cap so this
     tighter px cap applies; viewBox letterboxes => no distortion */
  svg.plot:not(.no-vcap) {
    width: 100%;
    height: auto;
    max-height: 360px;
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
</style>
