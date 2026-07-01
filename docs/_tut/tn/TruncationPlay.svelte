<script lang="ts">
  // Section 7 island -- bond truncation (chi). We build a representative boundary
  // matrix with a decaying spectrum, take its thin SVD, and keep only the chi
  // largest singular values; the bar chart dims the dropped tail and prints the
  // relative Frobenius truncation error. Slide chi up and the error falls to zero
  // -- at full chi the contraction is bit-for-bit exact. Self-contained, all
  // derived -- no $effect writes back.
  import TnSlider from "./TnSlider.svelte";
  import SpectrumChart from "./SpectrumChart.svelte";
  import MathTex from "./Tex.svelte";
  import { C } from "$lib/colors";
  import { svdTruncate } from "./tensor";

  // A structured but non-trivial matrix with a graded spectrum so chi visibly
  // trades accuracy for size (the unfolding of a boundary tensor).
  const chiMatrix = $derived.by(() => {
    const n = 8;
    const m = new Float64Array(n * n);
    // outer product of two smooth vectors + decaying noise -> graded spectrum.
    for (let i = 0; i < n; i += 1) {
      for (let j = 0; j < n; j += 1) {
        const base = Math.cos((Math.PI * i) / n) * Math.cos((Math.PI * j) / n);
        const ripple = 0.4 * Math.sin((2 * Math.PI * (i + 1) * (j + 1)) / (n * n));
        const decay = Math.exp(-(i + j) / 5);
        m[i * n + j] = base + ripple * decay + 0.15 * Math.exp(-Math.abs(i - j));
      }
    }

    return { data: m, n };
  });
  let chi = $state(3);
  const chiResult = $derived(
    svdTruncate(chiMatrix.data, chiMatrix.n, chiMatrix.n, chi),
  );
</script>

<TnSlider bind:value={chi} min={1} max={8} step={1} label="bond dimension χ" />
<SpectrumChart spectrum={chiResult.spectrum} {chi} relError={chiResult.relError} />
<div class="chi-note mono">
  <MathTex expr={"\\text{bond carries } \\min(\\chi, 2^s) \\text{ values}"} /> · keep the top
  <b style="color:{C.accent}">{chiResult.kept}</b>, discard the tail
</div>

<style>
  .chi-note {
    margin-top: 10px;
    font-size: 13px;
    color: var(--muted);
    text-align: center;
  }
</style>
