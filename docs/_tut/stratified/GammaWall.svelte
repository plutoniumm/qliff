<script lang="ts">
  // The wall: Gamma = prod(gamma_i) is the magnitude EVERY flat trajectory carries,
  // so it multiplies once per noise location whether that location faulted or not.
  // Sweep the location count and watch it leave the log axis, with the flat shot
  // budget (Gamma^2 times the Pauli one) alongside. Everything is a pure $derived of
  // the four controls -- no $effect writes state, so no effect_update_depth trap.
  import Slider from "$lib/Slider.svelte";
  import { C, withAlpha } from "$lib/colors";
  import LinePlot, { type DrawKit, type PlotSeries } from "$shared/LinePlot.svelte";
  import { binomialShots, flatShots, location, totalGamma, type Kind } from "./model";

  let kind = $state<Kind>("AMPLITUDE_DAMP");
  let strength = $state(0.05);
  let count = $state(27);
  let lerExp = $state(-3);

  const maxCount = 400;
  const targetRel = 0.1; // 10% relative error bar, as on the LER page
  const loc = $derived(location(kind, strength));
  const ler = $derived(Math.pow(10, lerExp));
  const bigGamma = $derived(totalGamma(loc, count));
  const pauliBudget = $derived(binomialShots(ler, targetRel));
  const flatBudget = $derived(flatShots(ler, targetRel, bigGamma));

  // Gamma against the number of noise locations, sampled thinly enough to stay a
  // smooth curve on the log axis without shipping 400 points.
  const curve = $derived<PlotSeries[]>([
    {
      pts: Array.from({ length: 81 }, (_, i) => {
        const a = 1 + Math.round((i / 80) * (maxCount - 1));

        return [a, totalGamma(loc, a)] as [number, number];
      }),
      color: C.accent,
      width: 2,
    },
  ]);
  const yTop = $derived(Math.max(10, totalGamma(loc, maxCount)));

  const annotate = $derived.by(() => {
    const at = count;
    const here = bigGamma;

    return (k: DrawKit) => {
      const { ctx, x, y, bbox, color, pxr } = k;
      ctx.save();
      ctx.strokeStyle = color(withAlpha(C.bad, 0.85));
      ctx.lineWidth = 1.6 * pxr;
      ctx.setLineDash([5 * pxr, 4 * pxr]);
      ctx.beginPath();
      ctx.moveTo(x(at), bbox.top);
      ctx.lineTo(x(at), bbox.top + bbox.height);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(x(at), y(here), 4 * pxr, 0, 2 * Math.PI);
      ctx.fillStyle = color(C.bad);
      ctx.fill();
      ctx.font = `bold ${11 * pxr}px ui-monospace, monospace`;
      ctx.textAlign = "left";
      ctx.fillText(`A = ${at}`, x(at) + 7 * pxr, bbox.top + 14 * pxr);
      ctx.restore();
    };
  });

  // Readable magnitude: exponent form once the number leaves everyday range.
  function big(v: number): string {
    if (!Number.isFinite(v)) {
      return "infinite";
    }

    if (v >= 1e5) {
      return v.toExponential(2);
    }

    if (v >= 100) {
      return v.toFixed(0);
    }

    return v.toFixed(3);
  }
</script>

<div class="ctl-row">
  <button class:active={kind === "AMPLITUDE_DAMP"} onclick={() => (kind = "AMPLITUDE_DAMP")}>
    amplitude damping
  </button>
  <button class:active={kind === "RZ"} onclick={() => (kind = "RZ")}>coherent RZ</button>
</div>
<div class="prose-controls">
  <Slider
    bind:value={strength}
    min={0.01}
    max={0.3}
    step={0.005}
    label={kind === "RZ" ? "angle θ (rad)" : "damping p"}
    format={(v) => v.toFixed(3)}
  />
  <Slider bind:value={count} min={1} max={maxCount} step={1} label="noise locations A" />
  <Slider
    bind:value={lerExp}
    min={-6}
    max={-1}
    step={1}
    label="target logical error rate"
    format={(v) => `10^${v}`}
  />
</div>
<LinePlot
  series={curve}
  xScale="lin"
  yScale="log"
  xRange={[1, maxCount]}
  yRange={[1, yTop]}
  xLabel="noise locations A (count)"
  yLabel="Γ = γ^A (weight magnitude per shot)"
  height={300}
  {annotate}
/>
<div class="stat-strip">
  <span>γ per location <b>{loc.gamma.toFixed(6)}</b></span>
  <span>Γ at A = {count} <b style="color:{C.accent}">{big(bigGamma)}</b></span>
  <span>Pauli shots <b>{big(pauliBudget)}</b></span>
  <span>flat shots <b style="color:{bigGamma > 10 ? C.bad : C.fg}">{big(flatBudget)}</b></span>
</div>
<p class="note">
  Shots for a 10% relative error bar on the target rate: the Pauli budget is
  (1 - LER) / (LER · 0.1²); flat importance sampling multiplies it by Γ².
</p>

<style>
  .ctl-row {
    display: flex;
    gap: 10px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }

  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }

  .stat-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin-top: 14px;
    font-size: 14px;
    color: var(--muted);
  }

  .stat-strip b {
    color: var(--fg);
    font-family: var(--font-mono);
    font-weight: 700;
  }

  .note {
    margin: 6px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.5;
  }
</style>
