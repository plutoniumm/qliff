<script lang="ts">
  // Which words a gate touches, row-major vs column-major. The tableau is 2n+1
  // Pauli rows over n qubits of bits; a 1-qubit gate on qubit q reads/writes q's
  // bit in EVERY row. Where those bits sit in memory is the whole story: row-major
  // scatters them one-per-row (strided, cache-hostile at large n -- the cliff);
  // column-major keeps q's plane as one contiguous run, so the gate is a
  // word-parallel sweep. The grid is a schematic of the access pattern; the stat
  // strip reports the ACTUAL word counts at a profiled n (colWords / rowTouches in
  // model.ts, the same closed forms as tableau.rs). Everything is a $derived of the
  // controls -- no $effect writes state.
  import Slider from "$lib/Slider.svelte";
  import { C, withAlpha } from "$lib/colors";
  import { colWords, reduction, rows, rowTouches, transposeBlocks } from "./model";

  let layout = $state<"row" | "col">("col");
  let n = $state(6);
  let qubit = $state(2);
  let exp = $state(10); // profiled n = 2^exp for the stat strip

  const rowsN = $derived(rows(n));
  const q = $derived(Math.min(qubit, n - 1));
  const profN = $derived(2 ** exp);

  // Row band of tableau row r: destabilizer (0..n-1), stabilizer (n..2n-1),
  // scratch (2n). Tints the three groups so the 2n+1 structure is legible.
  function band(r: number): string {
    if (r < n) {
      return C.accent2;
    }

    if (r < 2 * n) {
      return C.accent3;
    }

    return C.muted;
  }
</script>

<div class="ctl-row">
  <button class:active={layout === "col"} onclick={() => (layout = "col")}>
    column-major (gates)
  </button>
  <button class:active={layout === "row"} onclick={() => (layout = "row")}>
    row-major (measurement)
  </button>
</div>
<div class="prose-controls">
  <Slider bind:value={n} min={3} max={12} step={1} label="qubits n (schematic)" />
  <Slider bind:value={qubit} min={0} max={n - 1} step={1} label="gate on qubit q" />
</div>

{#if layout === "col"}
  <div class="planes">
    {#each Array(n) as _, j (j)}
      <div class="plane" class:hot={j === q}>
        {#each Array(rowsN) as _r, r (r)}
          <span
            class="cell"
            style="--c:{j === q ? C.accent : withAlpha(band(r), 0.28)}"
          ></span>
        {/each}
        <small>q{j}</small>
      </div>
    {/each}
  </div>
  <p class="cap">
    Memory runs top-to-bottom down each plane, then to the next plane. Qubit q's
    plane is one contiguous run of ceil((2n+1)/64) words, so a gate is a single
    word-parallel sweep -- no stride, cache-friendly.
  </p>
{:else}
  <div class="rowsview">
    {#each Array(rowsN) as _r, r (r)}
      <div class="trow">
        {#each Array(n) as _c, j (j)}
          <span
            class="cell"
            style="--c:{j === q ? C.accent : withAlpha(band(r), 0.28)}"
          ></span>
        {/each}
      </div>
    {/each}
  </div>
  <p class="cap">
    Memory runs left-to-right along each row, then to the next row. Qubit q's bit is
    one cell in every one of the 2n+1 rows, w = ceil(n/64) words apart, so a gate is
    2n+1 strided scalar touches -- what fell out of cache at large n (Wall 1).
  </p>
{/if}

<div class="legend">
  <span style="--c:{C.accent}">touched by the gate on q{q}</span>
  <span style="--c:{withAlpha(C.accent2, 0.55)}">destabilizer rows</span>
  <span style="--c:{withAlpha(C.accent3, 0.55)}">stabilizer rows</span>
  <span style="--c:{withAlpha(C.muted, 0.55)}">scratch</span>
</div>

<div class="profile">
  <Slider
    bind:value={exp}
    min={6}
    max={16}
    step={1}
    label="profiled n (real word counts)"
    format={() => `${profN}`}
  />
  <div class="stat-strip">
    <span>rows 2n+1 <b>{rows(profN).toLocaleString()}</b></span>
    <span>col-major word-ops / plane <b style="color:{C.accent}">{colWords(profN)}</b></span>
    <span>row-major scalar touches <b style="color:{C.bad}">{rowTouches(profN).toLocaleString()}</b></span>
    <span>reduction <b>{Math.round(reduction(profN))}x</b></span>
    <span>transpose 64x64 blocks <b>{transposeBlocks(profN).toLocaleString()}</b></span>
  </div>
</div>
<p class="note">
  A 1-qubit gate touches the same bits in both layouts; only the memory pattern
  differs. Column-major turns 2n+1 strided touches into ceil((2n+1)/64) contiguous
  word ops -- a ~64x drop in distinct cache lines once the rows exceed one word
  (n &gt; 32). The lazy row&lt;-&gt;col transpose that pays for this walks
  ceil((2n+1)/64) x ceil(n/64) blocks, once per measurement round.
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

  .planes {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .plane {
    display: flex;
    flex-direction: column;
    gap: 2px;
    align-items: center;
    padding: 4px;
    border-radius: 6px;
    border: 1.5px solid transparent;
  }

  .plane.hot {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .plane > small {
    font-size: 10px;
    color: var(--faint);
    font-family: var(--font-mono);
    margin-top: 2px;
  }

  .rowsview {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .trow {
    display: flex;
    gap: 2px;
  }

  .cell {
    width: 15px;
    height: 15px;
    border-radius: 3px;
    background: var(--c);
    flex: none;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
    margin: 12px 0 6px;
    font-size: 12.5px;
    color: var(--muted);
  }

  .legend > span {
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }

  .legend > span::before {
    content: "";
    width: 12px;
    height: 12px;
    border-radius: 3px;
    background: var(--c);
  }

  .cap {
    margin: 10px 0 0;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.5;
  }

  .profile {
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid var(--line);
  }

  .stat-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin-top: 12px;
    font-size: 14px;
    color: var(--muted);
  }

  .stat-strip b {
    color: var(--fg);
    font-family: var(--font-mono);
    font-weight: 700;
  }

  .note {
    margin: 10px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.55;
  }
</style>
