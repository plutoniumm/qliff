<script lang="ts">
  // A signed bar chart of quasiprobability branch weights. Zero sits on a center
  // baseline; positive weights grow up (accent), negative weights grow down and are
  // painted with C.bad -- the visual "sign problem". Each bar is labelled with its
  // Clifford core and its exact value. Pure SVG, animated by CSS transitions on the
  // bar geometry so dragging a slider sweeps the bars smoothly.
  import { C, withAlpha } from "$lib/colors";
  import type { Branch } from "./channel";

  let {
    branches,
    max = 1,
    height = 220,
  }: {
    branches: Branch[];
    max?: number;
    height?: number;
  } = $props();

  const W = 100;
  const padX = 6;
  const midY = $derived(height * 0.52);
  // pixels per unit weight: top half spans 0..max, bottom half the negatives.
  const scaleUp = $derived(midY - 18);
  const scaleDn = $derived(height - midY - 22);

  const slotW = $derived((W - 2 * padX) / branches.length);
  const barW = $derived(slotW * 0.52);

  function cx(i: number): number {
    return padX + slotW * (i + 0.5);
  }

  function barY(w: number): number {
    return w >= 0 ? midY - (w / max) * scaleUp : midY;
  }

  function barH(w: number): number {
    const h = w >= 0 ? (w / max) * scaleUp : (-w / max) * scaleDn;

    return Math.max(0.4, h);
  }

  function color(w: number): string {
    return w < -1e-9 ? C.bad : C.accent;
  }
</script>

<svg viewBox="0 0 {W} {height}" class="bars" preserveAspectRatio="none" role="img" aria-label="branch weights">
  <!-- zero baseline -->
  <line x1={padX} y1={midY} x2={W - padX} y2={midY} stroke={C.lineStrong} stroke-width="0.4" />
  <!-- +1 / 0 gridline ticks -->
  <line
    x1={padX}
    y1={midY - scaleUp}
    x2={W - padX}
    y2={midY - scaleUp}
    stroke={withAlpha(C.line, 0.5)}
    stroke-width="0.25"
    stroke-dasharray="1 1.4"
  />

  {#each branches as b, i (b.label)}
    <g>
      <rect
        x={cx(i) - barW / 2}
        y={barY(b.weight)}
        width={barW}
        height={barH(b.weight)}
        rx="0.6"
        fill={withAlpha(color(b.weight), 0.82)}
        stroke={color(b.weight)}
        stroke-width="0.3"
        class="bar"
      />
      <!-- core label under the baseline -->
      <text x={cx(i)} y={height - 6} class="lbl mono" text-anchor="middle">{b.label}</text>
      <!-- value above/below the bar -->
      <text
        x={cx(i)}
        y={b.weight >= 0 ? barY(b.weight) - 2.2 : barY(b.weight) + barH(b.weight) + 5}
        class="val mono"
        text-anchor="middle"
        fill={color(b.weight)}
      >
        {b.weight >= 0 ? "+" : "−"}{Math.abs(b.weight).toFixed(2)}
      </text>
    </g>
  {/each}
</svg>

<style>
  .bars {
    width: 100%;
    /* viewBox is 0 0 100 H, so width:100% alone would render at
       panelWidth*(H/100) -- far too tall on a wide panel. preserveAspectRatio
       is "none", so a CSS height cap simply clamps the box without distortion. */
    max-height: 260px;
    display: block;
  }

  .bar {
    transition:
      y var(--dur-fast, 0.12s) ease-out,
      height var(--dur-fast, 0.12s) ease-out,
      fill var(--dur-fast, 0.12s) ease-out,
      stroke var(--dur-fast, 0.12s) ease-out;
  }

  .lbl {
    font-size: 4px;
    fill: var(--fg);
  }

  .val {
    font-size: 3.4px;
    font-weight: 600;
  }
</style>
