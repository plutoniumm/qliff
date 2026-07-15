<script lang="ts">
  // Singular-value bar chart with a chi cutoff line. Bars past chi are dimmed
  // (they get dropped); the relative Frobenius error of that truncation is the
  // weight kept vs lost. This is the picture behind max_bond: keep the chi
  // largest singular values, factor the bond through a rank-chi waist, discard
  // the tail. Purely presentational -- it receives a spectrum + chi.
  import { C } from "$lib/colors";

  let {
    spectrum,
    chi,
    relError,
  }: {
    spectrum: number[];
    chi: number;
    relError: number;
  } = $props();

  const W = 560;
  const H = 210;
  const padL = 48;
  const padB = 44;
  const padT = 18;

  const maxS = $derived(Math.max(...spectrum, 1e-9));
  const barW = $derived((W - padL - 16) / Math.max(1, spectrum.length));

  function barH(s: number): number {
    return (s / maxS) * (H - padT - padB);
  }
  const cutX = $derived(padL + chi * barW);
</script>

<svg viewBox="0 0 {W} {H}" class="spec" role="img" aria-label="singular value spectrum">
  <!-- y-axis line + baseline (x-axis) -->
  <line class="axis" x1={padL} y1={padT - 6} x2={padL} y2={H - padB} />
  <line class="axis" x1={padL} y1={H - padB} x2={W - 4} y2={H - padB} />

  <!-- y-axis: singular-value magnitude (largest = top) -->
  <text class="ax-tick" x={padL - 7} y={padT + 4} text-anchor="end">{maxS.toFixed(2)}</text>
  <text class="ax-tick" x={padL - 7} y={H - padB} text-anchor="end">0</text>
  <text
    class="ax-title"
    x={14}
    y={(padT + H - padB) / 2}
    text-anchor="middle"
    transform="rotate(-90 14 {(padT + H - padB) / 2})">singular value σₖ</text
  >

  {#each spectrum as s, i}
    {@const kept = i < chi}
    <rect
      class="bar"
      class:dropped={!kept}
      x={padL + i * barW + barW * 0.12}
      y={H - padB - barH(s)}
      width={barW * 0.76}
      height={barH(s)}
    />
    <text class="idx" x={padL + i * barW + barW / 2} y={H - padB + 14} text-anchor="middle"
      >{i + 1}</text
    >
  {/each}

  <!-- x-axis title: which singular value (index k, descending) -->
  <text class="ax-title" x={(padL + W) / 2} y={H - 6} text-anchor="middle"
    >singular-value index k (descending)</text
  >

  {#if chi < spectrum.length}
    <line class="cut" x1={cutX} y1={padT - 6} x2={cutX} y2={H - padB} />
    <text class="cut-label" x={cutX + 6} y={padT + 6}>χ = {chi} cutoff</text>
  {/if}
</svg>

<div class="readout mono">
  kept {Math.min(chi, spectrum.length)} / {spectrum.length} singular values · truncation error
  <b style="color:{relError < 1e-6 ? C.ok : relError < 0.05 ? C.defect : C.bad}"
    >{(relError * 100).toFixed(relError < 1e-4 ? 4 : 2)}%</b
  >
  {#if relError < 1e-9}<span class="exact">(exact)</span>{/if}
</div>

<style>
  .spec {
    width: 100%;
    height: auto;
    /* viewBox is 560x210; explicit cap keeps the whole chart on a laptop screen. */
    max-height: 240px;
    display: block;
  }

  .axis {
    stroke: var(--line);
    stroke-width: 1;
  }

  .bar {
    fill: var(--accent);
    transition:
      fill 130ms ease,
      opacity 130ms ease;
  }

  .bar.dropped {
    fill: var(--faint);
    opacity: 0.4;
  }

  .cut {
    stroke: var(--accent-3);
    stroke-width: 2;
    stroke-dasharray: 5 3;
  }

  .cut-label {
    fill: var(--accent-3);
    font:
      600 12px/1 ui-monospace,
      monospace;
  }

  .idx {
    fill: var(--faint);
    font:
      10px/1 ui-monospace,
      monospace;
  }

  .ax-tick {
    fill: var(--faint);
    font:
      10px/1 ui-monospace,
      monospace;
  }

  .ax-title {
    fill: var(--muted);
    font:
      11px/1 ui-sans-serif,
      sans-serif;
  }

  .readout {
    margin-top: 10px;
    font-size: 13px;
    color: var(--muted);
    text-align: center;
  }

  .exact {
    color: var(--ok, #5be8b0);
  }
</style>
