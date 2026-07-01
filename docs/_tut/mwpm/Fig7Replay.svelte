<script lang="ts">
  // Section 7 island (optional): replay the brute-force search on the fixed
  // instance from steps 3/4, revealing the chosen optimal pairs one at a time as
  // you scrub. The final frame also draws the correction band.
  import RepCode from "./RepCode.svelte";
  import { LEFT, RIGHT, syndrome, minWeightMatching } from "./matching";
  import { mulberry32, bernoulli } from "$lib/rng";

  const D = 9;
  const p = 0.08;

  function seedErrors(seed: number): boolean[] {
    const rng = mulberry32(seed);
    const e = new Array(D).fill(false);
    for (let q = 0; q < D; q += 1) {
      e[q] = bernoulli(rng, 0.16);
    }

    return e;
  }

  // same seeded instance as steps 3/4.
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

  const result = minWeightMatching(defects, D, p);
  const optSearchPairs = result.pairs;
  const maxFrame = Math.max(1, optSearchPairs.length);

  let frame = $state(0);
  const shownPairs = $derived<[number, number][]>(optSearchPairs.slice(0, frame));
  const correction = $derived(frame >= optSearchPairs.length ? result.correction : null);

  function step(delta: number): void {
    frame = Math.max(0, Math.min(maxFrame, frame + delta));
  }
</script>

<RepCode
  d={D}
  {errors}
  {defects}
  {candidateEdges}
  matching={shownPairs}
  {correction}
  interactive={false}
  height={34}
/>
<div class="scrubber">
  <button onclick={() => step(-1)} disabled={frame <= 0} aria-label="previous">&lsaquo;</button>
  <input type="range" min="0" max={maxFrame} step="1" bind:value={frame} />
  <button onclick={() => step(1)} disabled={frame >= maxFrame} aria-label="next">&rsaquo;</button>
  <span class="readout mono">pair {frame}/{maxFrame}</span>
</div>

<style>
  .mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }

  .scrubber {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
  }

  .scrubber input[type="range"] {
    flex: 1;
  }

  .scrubber button {
    padding: 6px 11px;
  }

  .readout {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    min-width: 84px;
    text-align: right;
  }
</style>
