<script lang="ts">
  // Renders an n-qubit Pauli as a row of per-qubit cells: each cell shows the
  // Pauli letter (I/X/Y/Z, coloured) above its two bits (x, z). A leading sign
  // chip shows +/-. Pure presentation; all logic lives in tableau.ts.
  import { C } from "$lib/colors";
  import { pauliChar, type Pauli } from "./tableau";

  let {
    p,
    labels,
    highlight = [],
    compact = false,
  }: {
    p: Pauli;
    labels?: string[];
    highlight?: number[];
    compact?: boolean;
  } = $props();

  const n = $derived(p.x.length);

  function letterColor(c: "I" | "X" | "Y" | "Z"): string {
    if (c === "X") {
      return C.x;
    }
    if (c === "Z") {
      return C.z;
    }
    if (c === "Y") {
      return C.y;
    }

    return C.faint;
  }
</script>

<!-- Reskinned onto the shared qui .q-cells component (components.css, loaded
     globally). Only the per-Pauli colors (letter via --c, x/z bits, sign) and
     the two variants the shared class lacks (.hl highlight, .compact) stay
     local; the duplicated layout CSS is gone. -->
<div class="q-cells" class:compact>
  <span class="q-sign mono" style="color:{p.sign === 0 ? C.ok : C.bad}">
    {p.sign === 0 ? "+" : "−"}
  </span>
  {#each Array(n) as _, i (i)}
    {@const c = pauliChar(p.x[i], p.z[i])}
    <div class="q-cell" class:hl={highlight.includes(i)} style="--c:{letterColor(c)}">
      <b class="mono">{c}</b>
      <span class="q-bits">
        <span style="color:{p.x[i] ? C.x : C.faint}">x={p.x[i] ? 1 : 0}</span>
        <span style="color:{p.z[i] ? C.z : C.faint}">z={p.z[i] ? 1 : 0}</span>
      </span>
      <small>{labels?.[i] ?? `q${i}`}</small>
    </div>
  {/each}
</div>

<style>
  /* variants the shared .q-cell has no equivalent for */
  .q-cell.hl {
    border-color: color-mix(in srgb, var(--accent) 65%, transparent);
    background: var(--grad-soft);
  }

  .q-cells.compact > .q-cell > b {
    font-size: 20px;
  }
</style>
