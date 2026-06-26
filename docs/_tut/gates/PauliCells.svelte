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

<div class="cells" class:compact>
  <span class="sign mono" style="color:{p.sign === 0 ? C.ok : C.bad}">
    {p.sign === 0 ? "+" : "−"}
  </span>
  {#each Array(n) as _, i (i)}
    {@const c = pauliChar(p.x[i], p.z[i])}
    <div class="cell" class:hl={highlight.includes(i)}>
      <span class="letter mono" style="color:{letterColor(c)}">{c}</span>
      <div class="bits mono">
        <span class="bit" style="color:{p.x[i] ? C.x : C.faint}">x={p.x[i] ? 1 : 0}</span>
        <span class="bit" style="color:{p.z[i] ? C.z : C.faint}">z={p.z[i] ? 1 : 0}</span>
      </div>
      <span class="qlbl mono">{labels?.[i] ?? `q${i}`}</span>
    </div>
  {/each}
</div>

<style>
  .cells {
    display: flex;
    align-items: stretch;
    gap: 10px;
    flex-wrap: wrap;
  }

  .sign {
    align-self: center;
    font-size: 30px;
    font-weight: 700;
    width: 18px;
    text-align: center;
  }

  .cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 8px 12px;
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: color-mix(in srgb, var(--bg-2) 55%, transparent);
    min-width: 58px;
  }

  .cell.hl {
    border-color: color-mix(in srgb, var(--accent) 65%, transparent);
    background: var(--grad-soft);
  }

  .letter {
    font-size: 26px;
    font-weight: 700;
    line-height: 1;
  }

  .compact .letter {
    font-size: 20px;
  }

  .bits {
    display: flex;
    gap: 8px;
    font-size: 11.5px;
  }

  .qlbl {
    font-size: 10.5px;
    color: var(--faint);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
</style>
