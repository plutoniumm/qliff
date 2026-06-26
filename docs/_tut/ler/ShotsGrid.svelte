<script lang="ts">
  // A grid of shots. Each cell shows the decoder's PREDICTED observable flip and
  // the TRUE flip; they match -> success (ok), disagree -> logical error (bad).
  // Click a cell to flip its prediction and watch the running LER update. This is
  // exactly qliff's verdict: error iff predicted != observed.
  import { C, withAlpha } from "$lib/colors";

  interface Shot {
    predicted: boolean;
    observed: boolean;
  }

  let { shots = $bindable<Shot[]>([]) }: { shots?: Shot[] } = $props();

  const errors = $derived(shots.filter((s) => s.predicted !== s.observed).length);
  const ler = $derived(shots.length > 0 ? errors / shots.length : 0);

  function toggle(i: number): void {
    shots[i] = { ...shots[i], predicted: !shots[i].predicted };
  }

  const cols = 12;
</script>

<div class="wrap">
  <div class="grid" style="--cols:{cols}">
    {#each shots as s, i}
      {@const wrong = s.predicted !== s.observed}
      <button
        class="cell"
        class:wrong
        style="
          --c:{wrong ? C.bad : C.ok};
          --bgc:{withAlpha(wrong ? C.bad : C.ok, 0.16)};
        "
        onclick={() => toggle(i)}
        title={`shot ${i + 1}: predicted ${s.predicted ? "flip" : "no flip"}, true ${s.observed ? "flip" : "no flip"} -> ${wrong ? "LOGICAL ERROR" : "ok"}`}
      >
        <span class="pred">{s.predicted ? "1" : "0"}</span>
        <span class="sep">/</span>
        <span class="obs">{s.observed ? "1" : "0"}</span>
      </button>
    {/each}
  </div>

  <div class="readout">
    <div class="stat">
      <span class="num" style="color:{C.bad}">{errors}</span>
      <span class="lbl">logical errors</span>
    </div>
    <div class="stat">
      <span class="num" style="color:{C.ok}">{shots.length - errors}</span>
      <span class="lbl">survived</span>
    </div>
    <div class="stat big">
      <span class="num">{(ler * 100).toFixed(1)}%</span>
      <span class="lbl">LER = errors / shots</span>
    </div>
    <div class="stat big">
      <span class="num" style="color:{C.ok}">{((1 - ler) * 100).toFixed(1)}%</span>
      <span class="lbl">fidelity = 1 − LER</span>
    </div>
  </div>
  <p class="hint">
    Each cell reads <span class="mono">predicted / true</span>. Click any cell to flip the decoder's
    prediction; a mismatch turns it red -- a logical error.
  </p>
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(var(--cols), 1fr);
    gap: 6px;
    /* cap cell size (~58px each) so the grid never grows unbounded on a wide
       panel and the whole figure stays inside a laptop viewport */
    max-width: 760px;
    margin-inline: auto;
  }
  .cell {
    padding: 0;
    aspect-ratio: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1px;
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 600;
    border-radius: var(--r-sm);
    border: 1.5px solid var(--c);
    background: var(--bgc);
    color: var(--c);
    transition: transform var(--dur-fast) var(--ease-out);
  }
  .cell:hover {
    transform: translateY(-1px) scale(1.03);
  }
  .cell .sep {
    color: var(--faint);
  }
  .readout {
    display: flex;
    flex-wrap: wrap;
    gap: 22px;
    margin-top: 18px;
    align-items: baseline;
  }
  .stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .stat .num {
    font-family: var(--font-mono);
    font-size: 20px;
    font-weight: 700;
    color: var(--fg);
  }
  .stat.big .num {
    font-size: 26px;
  }
  .stat .lbl {
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .hint {
    margin: 16px 0 0;
    font-size: 13.5px;
    color: var(--faint);
    line-height: 1.5;
  }
  .hint .mono {
    color: var(--muted);
  }
</style>
