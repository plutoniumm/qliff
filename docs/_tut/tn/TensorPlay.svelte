<script lang="ts">
  // A tiny editable contraction: two 2x2 tensors A (legs i, k) and B (legs k, j)
  // sharing leg k. Contracting over k is the matrix product C[i,j] = sum_k
  // A[i,k] B[k,j]. The user edits any entry; the shared-index sum and the result
  // update live. This is the whole grammar of tensor networks in one widget --
  // contraction = "sum over the shared leg". Pure derived state, no effects.
  import { heat } from "$lib/colors";
  import MathTex from "./Tex.svelte";

  let A = $state([
    [0.9, 0.1],
    [0.2, 0.8],
  ]);
  let B = $state([
    [0.7, 0.3],
    [0.4, 0.6],
  ]);
  let hi = $state<{ i: number; j: number } | null>({ i: 0, j: 0 });

  const C = $derived(
    [0, 1].map((i) => [0, 1].map((j) => A[i][0] * B[0][j] + A[i][1] * B[1][j])),
  );

  const maxC = $derived(Math.max(...C.flat(), 0.001));

  function cellColor(v: number, scale: number): string {
    return heat(Math.max(0, Math.min(1, v / scale)));
  }

  function setA(i: number, k: number, e: Event): void {
    const v = parseFloat((e.target as HTMLInputElement).value);
    if (!Number.isNaN(v)) {
      A[i][k] = v;
    }
  }
  function setB(k: number, j: number, e: Event): void {
    const v = parseFloat((e.target as HTMLInputElement).value);
    if (!Number.isNaN(v)) {
      B[k][j] = v;
    }
  }
</script>

<div class="play">
  <div class="grids">
    <div class="grid">
      <div class="gname mono">A<sub>ik</sub></div>
      <div class="cells">
        {#each [0, 1] as i}
          {#each [0, 1] as k}
            <input
              class="cell edit"
              class:row-hi={hi && hi.i === i}
              style="background:{cellColor(A[i][k], 1)}"
              value={A[i][k]}
              oninput={(e) => setA(i, k, e)}
            />
          {/each}
        {/each}
      </div>
    </div>

    <div class="op mono">×</div>

    <div class="grid">
      <div class="gname mono">B<sub>kj</sub></div>
      <div class="cells">
        {#each [0, 1] as k}
          {#each [0, 1] as j}
            <input
              class="cell edit"
              class:col-hi={hi && hi.j === j}
              style="background:{cellColor(B[k][j], 1)}"
              value={B[k][j]}
              oninput={(e) => setB(k, j, e)}
            />
          {/each}
        {/each}
      </div>
    </div>

    <div class="op mono">=</div>

    <div class="grid">
      <div class="gname mono">C<sub>ij</sub></div>
      <div class="cells">
        {#each [0, 1] as i}
          {#each [0, 1] as j}
            <button
              type="button"
              class="cell out"
              class:active={hi && hi.i === i && hi.j === j}
              style="background:{cellColor(C[i][j], maxC)}"
              onmouseenter={() => (hi = { i, j })}
              onfocus={() => (hi = { i, j })}
            >
              {C[i][j].toFixed(2)}
            </button>
          {/each}
        {/each}
      </div>
    </div>
  </div>

  {#if hi}
    <div class="sum mono">
      <MathTex
        expr={`C_{${hi.i}${hi.j}} = \\sum_{k} A_{${hi.i}k}\\,B_{k${hi.j}} = A_{${hi.i}0}B_{0${hi.j}} + A_{${hi.i}1}B_{1${hi.j}}`}
      />
      <span class="numeric"
        >= {A[hi.i][0].toFixed(2)}·{B[0][hi.j].toFixed(2)} + {A[hi.i][1].toFixed(2)}·{B[1][
          hi.j
        ].toFixed(2)} = <b>{C[hi.i][hi.j].toFixed(3)}</b></span
      >
    </div>
  {/if}
</div>

<style>
  .play {
    display: flex;
    flex-direction: column;
    gap: 16px;
    align-items: center;
  }

  .grids {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    justify-content: center;
  }

  .grid {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: center;
  }

  .gname {
    font-size: 13px;
    color: var(--muted);
  }

  .cells {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 4px;
    padding: 6px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
  }

  .cell {
    width: 56px;
    height: 42px;
    border-radius: 7px;
    text-align: center;
    font:
      600 13px/1 ui-monospace,
      monospace;
    color: #0a0c16;
    border: 1px solid color-mix(in srgb, #000 25%, transparent);
  }

  input.cell.edit {
    -moz-appearance: textfield;
    appearance: textfield;
  }

  .cell.out {
    cursor: pointer;
    transition: transform 120ms ease;
  }

  .cell.out.active {
    outline: 2px solid var(--fg);
    transform: scale(1.06);
  }

  .row-hi {
    box-shadow: 0 0 0 2px var(--accent);
  }

  .col-hi {
    box-shadow: 0 0 0 2px var(--accent-2);
  }

  .op {
    font-size: 22px;
    color: var(--muted);
  }

  .sum {
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: center;
    font-size: 13px;
    color: var(--fg);
    text-align: center;
  }

  .numeric {
    color: var(--muted);
  }
</style>
