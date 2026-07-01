<script lang="ts">
  // Section 7 island: a live Monte-Carlo logical error rate for the MWPM-decoded
  // repetition code. Sliders set distance d and physical error p; the plot sweeps
  // LER vs p, with a marker at the current p. Pure functions of (d, p) -> $derived
  // (no $effect writing state).
  import { syndrome, minWeightMatching, logicalFailed } from "./matching";
  import { mulberry32, bernoulli } from "$lib/rng";
  import { C, withAlpha } from "$lib/colors";

  let d = $state(5);
  let p = $state(0.08);
  const SHOTS = 4000;

  const ler = $derived.by(() => {
    const dd = d;
    const pp = p;
    const rng = mulberry32(0xbeef ^ (dd << 8) ^ Math.round(pp * 1000));
    let fails = 0;
    for (let s = 0; s < SHOTS; s += 1) {
      const e: boolean[] = new Array(dd);
      for (let q = 0; q < dd; q += 1) {
        e[q] = bernoulli(rng, pp);
      }
      const defs = syndrome(e);
      const m = minWeightMatching(defs, dd, pp);
      if (logicalFailed(e, m.correction)) {
        fails += 1;
      }
    }

    return fails / SHOTS;
  });

  // a sweep of LER vs p at the current distance, for the little curve.
  const sweep = $derived.by(() => {
    const dd = d;
    const ps = [0.02, 0.04, 0.06, 0.08, 0.1, 0.13, 0.16, 0.2, 0.25, 0.3];
    const N = 2500;

    return ps.map((pp) => {
      const rng = mulberry32(0x1234 ^ (dd << 8) ^ Math.round(pp * 1000));
      let fails = 0;
      for (let s = 0; s < N; s += 1) {
        const e: boolean[] = new Array(dd);
        for (let q = 0; q < dd; q += 1) {
          e[q] = bernoulli(rng, pp);
        }
        const m = minWeightMatching(syndrome(e), dd, pp);
        if (logicalFailed(e, m.correction)) {
          fails += 1;
        }
      }

      return { p: pp, ler: fails / N };
    });
  });

  // map a LER in [0,1] (log-ish) to a y in a small plot.
  function plotY(v: number, h: number): number {
    const lo = 1e-4;
    const c = Math.max(v, lo);
    const t = (Math.log10(c) - Math.log10(lo)) / (0 - Math.log10(lo));

    return h - t * h;
  }
</script>

<div class="dist-grid">
  <div class="ctrl">
    <label class="slider">
      <span class="srow">
        <span class="label">code distance d</span>
        <span class="value mono">{d}</span>
      </span>
      <input type="range" min="3" max="11" step="2" bind:value={d} />
    </label>
    <label class="slider">
      <span class="srow">
        <span class="label">physical error p</span>
        <span class="value mono">{p.toFixed(3)}</span>
      </span>
      <input type="range" min="0.01" max="0.4" step="0.005" bind:value={p} />
    </label>
    <div class="ler-readout">
      <span class="k">logical error rate</span>
      <span class="v mono" style="color:{ler < p ? 'var(--ok)' : 'var(--bad)'}">
        {ler === 0 ? "< 1/" + SHOTS : ler.toExponential(2)}
      </span>
      <span class="sub mono">
        {ler < p ? "below physical p -- the code helps" : "above physical p -- past threshold"}
      </span>
    </div>
  </div>

  <svg viewBox="0 0 200 120" class="plot" role="img" aria-label="logical error rate vs p">
    <!-- y gridlines at 1e-1, 1e-2, 1e-3 -->
    {#each [0.1, 0.01, 0.001] as gy (gy)}
      <line x1="22" x2="196" y1={plotY(gy, 100) + 6} y2={plotY(gy, 100) + 6} stroke={withAlpha(C.line, 1)} stroke-width="0.4" />
      <text x="2" y={plotY(gy, 100) + 8} class="axlbl">{gy}</text>
    {/each}
    <!-- LER sweep curve -->
    <polyline
      points={sweep.map((s) => `${22 + (s.p / 0.3) * 174},${plotY(s.ler, 100) + 6}`).join(" ")}
      fill="none"
      stroke={C.accent2}
      stroke-width="1.4"
    />
    {#each sweep as s (s.p)}
      <circle cx={22 + (s.p / 0.3) * 174} cy={plotY(s.ler, 100) + 6} r="1.6" fill={C.accent2} />
    {/each}
    <!-- marker at current p -->
    <line
      x1={22 + (Math.min(p, 0.3) / 0.3) * 174}
      x2={22 + (Math.min(p, 0.3) / 0.3) * 174}
      y1="6" y2="106"
      stroke={withAlpha(C.accent, 0.6)}
      stroke-width="0.6"
      stroke-dasharray="2 2"
    />
    <text x="100" y="118" class="axlbl" text-anchor="middle">physical error p -></text>
  </svg>
</div>

<style>
  .mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }

  .dist-grid {
    display: grid;
    grid-template-columns: minmax(220px, 320px) 1fr;
    gap: 24px;
    align-items: center;
  }

  .ctrl {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 180px;
  }

  .slider {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .slider .srow {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }

  .slider .label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .slider .value {
    font-size: 13px;
    color: var(--fg);
  }

  .slider input[type="range"] {
    width: 100%;
  }

  .ler-readout {
    display: flex;
    flex-direction: column;
    gap: 3px;
    margin-top: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--line);
  }

  .ler-readout .k {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .ler-readout .v {
    font-size: 26px;
    font-weight: 700;
  }

  .ler-readout .sub {
    font-size: 11.5px;
    color: var(--faint);
  }

  .plot {
    width: 100%;
    height: auto;
    max-height: 300px;
    display: block;
  }

  .axlbl {
    font-size: 5px;
    fill: var(--muted);
    font-family: ui-monospace, monospace;
  }

  @media (max-width: 720px) {
    .dist-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
