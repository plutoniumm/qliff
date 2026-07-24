<script lang="ts">
  // The payoff, measured. Col-major gate cost per PLANE-WORD stays on a flat floor
  // (~13-14 ns) as the plane grows 16x from n=4096 to n=65536 -- there is no cache
  // cliff. The per-GATE cost still climbs, because a gate is O(rows/64) = O(n) word
  // ops; that growth is expected and linear, not a collapse. One toggle switches
  // between the two views of the SAME measured runs (MEASURED in model.ts). No
  // $effect writes state; the curve is a pure $derived.
  import { C, withAlpha } from "$lib/colors";
  import LinePlot, { type DrawKit, type PlotSeries } from "$lib/LinePlot.svelte";
  import { MEASURED } from "./model";

  let metric = $state<"word" | "gate">("word");

  const floor = 14; // the ns/plane-word bandwidth floor the large-n points settle on

  const series = $derived<PlotSeries[]>([
    {
      pts: MEASURED.map(
        (m) => [m.n, metric === "word" ? m.nsWord : m.nsGate] as [number, number],
      ),
      color: metric === "word" ? C.accent : C.bad,
      width: 2,
      showPoints: true,
    },
  ]);

  const yRange = $derived<[number, number]>(
    metric === "word" ? [0, 45] : [1000, 100000],
  );

  // Draw the ns/word floor as a dashed guide so "flat" is not just an assertion.
  const annotate = $derived.by(() => {
    if (metric !== "word") {
      return undefined;
    }

    return (k: DrawKit) => {
      const { ctx, x, y, bbox, color, pxr } = k;
      ctx.save();
      ctx.strokeStyle = color(withAlpha(C.muted, 0.8));
      ctx.lineWidth = 1.4 * pxr;
      ctx.setLineDash([5 * pxr, 4 * pxr]);
      ctx.beginPath();
      ctx.moveTo(bbox.left, y(floor));
      ctx.lineTo(bbox.left + bbox.width, y(floor));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = `${11 * pxr}px ui-monospace, monospace`;
      ctx.fillStyle = color(C.muted);
      ctx.textAlign = "left";
      ctx.fillText(`~${floor} ns/word floor`, bbox.left + 8 * pxr, y(floor) - 6 * pxr);
      ctx.restore();
    };
  });
</script>

<div class="ctl-row">
  <button class:active={metric === "word"} onclick={() => (metric = "word")}>
    ns per plane-word
  </button>
  <button class:active={metric === "gate"} onclick={() => (metric = "gate")}>
    ns per gate
  </button>
</div>

<LinePlot
  {series}
  xScale="log"
  yScale={metric === "word" ? "lin" : "log"}
  xRange={[200, 70000]}
  {yRange}
  xLabel="qubits n (log)"
  yLabel={metric === "word" ? "ns per plane-word" : "ns per 1-qubit gate (log)"}
  height={300}
  {annotate}
/>

<div class="scroll">
  <table>
    <thead>
      <tr>
        <th>n</th>
        <th>rows 2n+1</th>
        <th>words / plane</th>
        <th>ns / gate</th>
        <th>ns / plane-word</th>
      </tr>
    </thead>
    <tbody>
      {#each MEASURED as m (m.n)}
        <tr>
          <td>{m.n.toLocaleString()}</td>
          <td>{(2 * m.n + 1).toLocaleString()}</td>
          <td>{m.rw.toLocaleString()}</td>
          <td>{m.nsGate.toLocaleString()}</td>
          <td style="color:{m.n >= 4096 ? C.accent : C.fg}">{m.nsWord.toFixed(1)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<p class="note">
  Measured with qliff's own ColTableau.run on the committed build (single core,
  Apple silicon, 2026-07); H sweeps on a fresh tableau, argument marshalling
  excluded. Absolute nanoseconds are machine-relative -- the shape is the point.
  From n = 4096 to n = 65536 the plane grows 16x (129 -&gt; 2049 words) while
  ns/plane-word holds at ~13-14: the working set leaves cache and throughput does
  not fall off a cliff. The per-gate cost climbs because a gate is O(rows/64) word
  ops, exactly linear in the plane size.
</p>

<style>
  .ctl-row {
    display: flex;
    gap: 10px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }

  .scroll {
    overflow-x: auto;
    margin-top: 14px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }

  th,
  td {
    text-align: right;
    padding: 5px 12px;
    border-bottom: 1px solid var(--line);
  }

  th {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    font-weight: 600;
  }

  td {
    font-family: var(--font-mono);
    color: var(--fg);
  }

  .note {
    margin: 12px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.55;
  }
</style>
