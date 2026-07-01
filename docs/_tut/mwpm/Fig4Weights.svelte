<script lang="ts">
  // Section 4 island: the edge weight w(p) = log((1-p)/p). Slide the physical
  // error rate and watch the per-step weight (and the little p-table) move; the
  // graph from step 3 is shown with the same seeded instance.
  import RepCode from "./RepCode.svelte";
  import { LEFT, RIGHT, syndrome, edgeWeight } from "./matching";
  import { mulberry32, bernoulli } from "$lib/rng";

  const D = 9;

  function seedErrors(seed: number): boolean[] {
    const rng = mulberry32(seed);
    const e = new Array(D).fill(false);
    for (let q = 0; q < D; q += 1) {
      e[q] = bernoulli(rng, 0.16);
    }

    return e;
  }

  // same seeded instance as step 3, so the two graphs agree.
  const errors = seedErrors(0x51);
  const defects = syndrome(errors);
  const candidateEdges: [number, number][] = (() => {
    const edges: [number, number][] = [];
    for (let i = 0; i < defects.length; i += 1) {
      edges.push([defects[i], LEFT]);
      edges.push([defects[i], RIGHT]);
      for (let j = i + 1; j < defects.length; j += 1) {
        edges.push([defects[i], defects[j]]);
      }
    }

    return edges;
  })();

  let p = $state(0.08);
  let showWeights = $state(true);
  const w = $derived(edgeWeight(p));
  // a small p -> weight table.
  const pTable = [0.5, 0.2, 0.1, 0.05, 0.01, 0.001];
</script>

<div class="weights-grid">
  <div class="big mono" style="color:var(--accent2)">
    w = {w.toFixed(2)}
  </div>
  <div class="ctrl">
    <label class="slider">
      <span class="srow">
        <span class="label">physical error p</span>
        <span class="value mono">{p.toFixed(3)}</span>
      </span>
      <input type="range" min="0.001" max="0.49" step="0.001" bind:value={p} />
    </label>
    <label class="toggle">
      <input type="checkbox" bind:checked={showWeights} />
      <span class="ttext">show edge weights on graph</span>
    </label>
  </div>
  <table class="ptable mono">
    <thead><tr><th>p</th><th>w = log((1-p)/p)</th></tr></thead>
    <tbody>
      {#each pTable as pv (pv)}
        <tr class:hl={Math.abs(pv - p) < 0.02}>
          <td>{pv}</td>
          <td>{edgeWeight(pv).toFixed(2)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
{#if showWeights}
  <RepCode d={D} {errors} {defects} {candidateEdges} interactive={false} height={34} />
{/if}

<style>
  .mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }

  .weights-grid {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 18px;
    align-items: center;
    margin-bottom: 8px;
  }

  .weights-grid .big {
    font-size: 30px;
    font-weight: 700;
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

  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    cursor: pointer;
    user-select: none;
    font-size: 13.5px;
    color: var(--fg);
  }

  .ptable {
    font-size: 12px;
    border-collapse: collapse;
  }

  .ptable th,
  .ptable td {
    padding: 2px 10px;
    text-align: right;
    border-bottom: 1px solid var(--line);
  }

  .ptable th {
    color: var(--muted);
    font-weight: 600;
  }

  .ptable tr.hl td {
    color: var(--accent-2);
    background: color-mix(in srgb, var(--accent-2) 10%, transparent);
  }

  @media (max-width: 720px) {
    .weights-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
