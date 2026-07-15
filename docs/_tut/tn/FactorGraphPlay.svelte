<script lang="ts">
  // Live repetition-code factor graph. Opens on the page's running example
  // (3 data qubits, p = 0.1, syndrome (1, 0)) so the drawn network is the one
  // the prose builds tensor by tensor. Two sliders (code distance, physical
  // error p) rebuild the DEM and its factor graph; click a detector to flip
  // its observed syndrome bit and the parity tensor re-pins. Mechanisms
  // touching a lit detector are highlighted, and the two factor tensors
  // (biased COPY [1-p, p] and the syndrome-pinned parity) are printed below.
  // Self-contained: owns its own distance/p/syndrome state (no $effect writes
  // back into shared state; the syndrome is length-fitted by a pure derived).
  import TnSlider from "./TnSlider.svelte";
  import FactorGraph from "./FactorGraph.svelte";
  import { C } from "$lib/colors";
  import { repetitionDem, buildFactorGraph, type Dem } from "./decoder";

  let dataQubits = $state(3); // the running example's code
  let p = $state(0.1); // physical error probability
  const demLive: Dem = $derived(repetitionDem(dataQubits, p));
  const fgLive = $derived(buildFactorGraph(demLive));
  let synLive = $state<number[]>([1, 0]); // the measured shot s = 10

  // keep the syndrome array length in sync WITHOUT an effect: derive a padded
  // copy used everywhere downstream (pure function of inputs).
  const synFitted = $derived.by(() => {
    const n = demLive.numDetectors;
    const out = new Array<number>(n).fill(0);
    for (let i = 0; i < Math.min(n, synLive.length); i += 1) {
      out[i] = synLive[i] & 1;
    }

    return out;
  });

  function setSynLive(d: number): void {
    const next = synFitted.slice();
    next[d] = next[d] ? 0 : 1;
    synLive = next;
  }

  // mechanisms touching at least one lit detector (for highlighting in the graph).
  const litMechs = $derived.by(() => {
    const lit = new Set<number>();
    fgLive.detectors.forEach((det) => {
      if (synFitted[det.d] === 1) {
        det.mechs.forEach((m) => lit.add(m));
      }
    });

    return [...lit];
  });
</script>

<div class="ctrl-row">
  <TnSlider bind:value={dataQubits} min={3} max={6} step={1} label="code distance (data qubits)" />
  <TnSlider bind:value={p} min={0.02} max={0.45} step={0.01} label="physical error p" />
</div>

<FactorGraph fg={fgLive} syndrome={synFitted} {p} highlightMechs={litMechs} onFlip={setSynLive} />

<div class="tensor-contents">
  <div class="tc">
    <div class="tc-name mono" style="color:{C.accent}">biased COPY [1-p, p]</div>
    <table class="mini mono">
      <tbody>
        <tr><td>00...0</td><td>{(1 - p).toFixed(3)}</td></tr>
        <tr><td>11...1</td><td>{p.toFixed(3)}</td></tr>
        <tr><td>mixed</td><td>0</td></tr>
      </tbody>
    </table>
  </div>
  <div class="tc">
    <div class="tc-name mono" style="color:{C.z}">parity(target = syndrome)</div>
    <table class="mini mono">
      <tbody>
        <tr><td>XOR = target</td><td>1</td></tr>
        <tr><td>XOR ≠ target</td><td>0</td></tr>
      </tbody>
    </table>
  </div>
</div>

<style>
  .ctrl-row {
    display: flex;
    flex-wrap: wrap;
    gap: 18px 28px;
    align-items: center;
    margin-bottom: 14px;
  }

  .tensor-contents {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    justify-content: center;
    margin-top: 14px;
  }

  .tc {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: center;
  }

  .tc-name {
    font-size: 12px;
    font-weight: 600;
  }

  table.mini {
    border-collapse: collapse;
    font-size: 12px;
  }

  table.mini td {
    border: 1px solid var(--line);
    padding: 3px 12px;
    color: var(--fg);
  }
</style>
