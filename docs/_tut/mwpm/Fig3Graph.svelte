<script lang="ts">
  // Section 3 island: the syndrome as a matching graph. Every candidate edge
  // (defect-defect and defect-boundary) is drawn dashed; hover an edge chip to
  // trace its chain. "new random errors" reseeds the instance.
  import RepCode from "./RepCode.svelte";
  import { LEFT, RIGHT, syndrome, chainLength, edgeWeight } from "./matching";
  import { mulberry32, bernoulli } from "$lib/rng";

  const D = 9;
  const p = 0.08;

  function seedErrors(seed: number): boolean[] {
    const rng = mulberry32(seed);
    const e = new Array(D).fill(false);
    // a couple of separated short chains so the graph is interesting.
    for (let q = 0; q < D; q += 1) {
      e[q] = bernoulli(rng, 0.16);
    }

    return e;
  }

  let errors = $state<boolean[]>(seedErrors(0x51));
  const defects = $derived(syndrome(errors));

  // candidate edges: every defect to every other defect, and to both boundaries.
  const candidateEdges = $derived.by<[number, number][]>(() => {
    const ds = defects;
    const edges: [number, number][] = [];
    for (let i = 0; i < ds.length; i += 1) {
      edges.push([ds[i], LEFT]);
      edges.push([ds[i], RIGHT]);
      for (let j = i + 1; j < ds.length; j += 1) {
        edges.push([ds[i], ds[j]]);
      }
    }

    return edges;
  });

  let hoverEdge = $state<[number, number] | null>(null);
  const w = $derived(edgeWeight(p));

  function reseed(): void {
    errors = seedErrors((Math.random() * 1e9) | 0);
    hoverEdge = null;
  }

  function nodeKey(id: number): string {
    if (id === LEFT) {
      return "L";
    }
    if (id === RIGHT) {
      return "R";
    }

    return `g${id}`;
  }

  function edgeLabel(a: number, b: number): string {
    const len = chainLength(a, b, D);
    const bnd = a === LEFT || b === LEFT || a === RIGHT || b === RIGHT;

    return `${bnd ? "boundary, " : ""}len ${len} -> ${(len * w).toFixed(2)}`;
  }
</script>

<RepCode d={D} {errors} {defects} {candidateEdges} {hoverEdge} interactive={false} height={34} />
<div class="edgelist">
  {#each candidateEdges as [a, b] (`${a}-${b}`)}
    <button
      class="chip mono"
      onmouseenter={() => (hoverEdge = [a, b])}
      onmouseleave={() => (hoverEdge = null)}
      onfocus={() => (hoverEdge = [a, b])}
      onblur={() => (hoverEdge = null)}
    >
      {nodeKey(a)}-{nodeKey(b)} | {edgeLabel(a, b)}
    </button>
  {/each}
  {#if candidateEdges.length === 0}
    <span class="tag">no defects -- perfect syndrome</span>
  {/if}
</div>
<div class="row">
  <button onclick={reseed}>new random errors</button>
  <span class="tag mono">{defects.length} defects | {candidateEdges.length} candidate edges</span>
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 12px;
    flex-wrap: wrap;
  }

  .tag {
    font-size: 12px;
    color: var(--muted);
  }

  .mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }

  .edgelist {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 12px 0 4px;
    max-height: 132px;
    overflow-y: auto;
  }

  .chip {
    font-size: 11.5px;
    padding: 4px 8px;
    line-height: 1.1;
  }
</style>
