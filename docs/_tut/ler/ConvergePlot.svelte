<script lang="ts">
  // Watch a Monte-Carlo estimate of the LER converge as shots accumulate. The
  // running estimate (a seeded trace) jitters around the true value; the shaded
  // +/- stderr band narrows like 1/sqrt(N). x-axis is log in N so the 1/sqrt(N)
  // shrink reads as a steady taper.
  import { C, withAlpha } from "$lib/colors";

  let {
    trace,
    truth,
    maxN,
    width = 720,
    height = 320,
  }: {
    trace: { n: number; ler: number; stderr: number }[];
    truth: number;
    maxN: number;
    width?: number;
    height?: number;
  } = $props();

  const pad = { l: 64, r: 16, t: 16, b: 44 };
  const iw = $derived(width - pad.l - pad.r);
  const ih = $derived(height - pad.t - pad.b);

  // y-range: pad around the true value and the trace spread
  const yMax = $derived(
    Math.max(truth * 2.2, ...trace.map((t) => t.ler + t.stderr), truth + 1e-9) * 1.05,
  );
  const nMin = 1;

  function sx(n: number): number {
    const lo = Math.log10(nMin);
    const hi = Math.log10(maxN);

    return pad.l + ((Math.log10(Math.max(nMin, n)) - lo) / (hi - lo)) * iw;
  }
  function sy(v: number): number {
    return pad.t + (1 - v / yMax) * ih;
  }

  const band = $derived(() => {
    const top = trace.map((t) => `${sx(t.n).toFixed(1)},${sy(t.ler + t.stderr).toFixed(1)}`);
    const bot = trace
      .slice()
      .reverse()
      .map((t) => `${sx(t.n).toFixed(1)},${sy(Math.max(0, t.ler - t.stderr)).toFixed(1)}`);

    return `M${top.join(" L")} L${bot.join(" L")} Z`;
  });

  const line = $derived(
    trace.map((t, i) => `${i === 0 ? "M" : "L"}${sx(t.n).toFixed(1)},${sy(t.ler).toFixed(1)}`).join(" "),
  );

  function nTicks(): number[] {
    const out: number[] = [];
    for (let e = 1; Math.pow(10, e) <= maxN; e += 1) {
      out.push(Math.pow(10, e));
    }

    return out;
  }
  const xticks = $derived(nTicks());

  function yTicks(): number[] {
    const out: number[] = [];
    const n = 4;
    for (let i = 0; i <= n; i += 1) {
      out.push((yMax * i) / n);
    }

    return out;
  }
  const yt = $derived(yTicks());

  function sup(e: number): string {
    const m: Record<string, string> = { "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷" };

    return String(e).split("").map((c) => m[c] ?? c).join("");
  }
</script>

<svg viewBox="0 0 {width} {height}" class="plot" role="img" aria-label="Monte-Carlo estimate converging on the true LER as shots increase">
  {#each yt as t}
    <line x1={pad.l} y1={sy(t)} x2={pad.l + iw} y2={sy(t)} stroke={withAlpha(C.line, 0.55)} stroke-width="1" />
    <text x={pad.l - 8} y={sy(t) + 4} text-anchor="end" class="tick">{(t * 100).toFixed(2)}%</text>
  {/each}
  {#each xticks as t}
    <line x1={sx(t)} y1={pad.t} x2={sx(t)} y2={pad.t + ih} stroke={withAlpha(C.line, 0.4)} stroke-width="1" />
    <text x={sx(t)} y={pad.t + ih + 17} text-anchor="middle" class="tick">10{sup(Math.round(Math.log10(t)))}</text>
  {/each}

  <!-- true LER -->
  <line x1={pad.l} y1={sy(truth)} x2={pad.l + iw} y2={sy(truth)} stroke={C.ok} stroke-width="1.6" stroke-dasharray="6 4" />
  <text x={pad.l + iw - 4} y={sy(truth) - 6} text-anchor="end" class="truth" fill={C.ok}>true LER</text>

  <!-- +/- stderr band and running estimate -->
  {#if trace.length > 1}
    {@const last = trace[trace.length - 1]}
    <path d={band()} fill={withAlpha(C.accent, 0.16)} stroke="none" />
    <path d={line} fill="none" stroke={C.accent} stroke-width="2" />
    <text x={sx(last.n) - 6} y={sy(last.ler + last.stderr) - 5} text-anchor="end" class="band-lbl" fill={C.accent}>±1σ band</text>
  {/if}

  <rect x={pad.l} y={pad.t} width={iw} height={ih} fill="none" stroke={C.lineStrong} stroke-width="1" />
  <text x={pad.l + iw / 2} y={height - 6} text-anchor="middle" class="axis">shots N (log scale, dimensionless count)</text>
  <text transform="translate(15,{pad.t + ih / 2}) rotate(-90)" text-anchor="middle" class="axis">LER estimate (% of shots)</text>
</svg>

<style>
  /* specificity beats the global `.frame svg:not(.no-vcap)` 62vh cap so this
     tighter px cap actually applies; viewBox letterboxes => no distortion */
  svg.plot:not(.no-vcap) {
    width: 100%;
    height: auto;
    max-height: 340px;
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
  .truth {
    font-size: 11px;
    font-weight: 700;
    font-family: var(--font-mono);
  }
  .band-lbl {
    font-size: 10.5px;
    font-weight: 700;
    font-family: var(--font-mono);
  }
</style>
