<script lang="ts">
  // Section 4 island: the CX propagator. Compose a two-qubit input Pauli from the
  // generator buttons, then read off CX.input.CX-dagger, with a live rule table for
  // the four generators. Control = q0, target = q1.
  import PauliCells from "./PauliCells.svelte";
  import { single, pauliString, withCX, type Pauli } from "./tableau";

  const INPUTS: { key: string; letter: "X" | "Y" | "Z"; q: 0 | 1 }[] = [
    { key: "Xc", letter: "X", q: 0 },
    { key: "Zc", letter: "Z", q: 0 },
    { key: "Yc", letter: "Y", q: 0 },
    { key: "Xt", letter: "X", q: 1 },
    { key: "Zt", letter: "Z", q: 1 },
    { key: "Yt", letter: "Y", q: 1 },
  ];
  let cxInput = $state<Pauli>(single(2, 1, "Z")); // default Z_t (the backward-propagating one)
  const cxOutput = $derived(withCX(cxInput, 0, 1));

  function setCXInput(letter: "X" | "Y" | "Z", q: 0 | 1): void {
    cxInput = single(2, q, letter);
  }

  // the four generator rules, each produced by withCX so the table is live.
  const cxRules = [
    { inp: single(2, 0, "X"), name: "X_c" },
    { inp: single(2, 1, "X"), name: "X_t" },
    { inp: single(2, 0, "Z"), name: "Z_c" },
    { inp: single(2, 1, "Z"), name: "Z_t" },
  ].map((r) => ({ ...r, out: withCX(r.inp, 0, 1) }));
</script>

<div class="cxgrid">
  <div class="cxcol">
    <span class="lbl">input on (control q0, target q1)</span>
    <div class="setrow wrap">
      {#each INPUTS as inp (inp.key)}
        <button class="gbtn small mono" onclick={() => setCXInput(inp.letter, inp.q)}>
          {inp.letter}<sub>{inp.q === 0 ? "c" : "t"}</sub>
        </button>
      {/each}
    </div>
    <div class="cxio"><PauliCells p={cxInput} labels={["q0 (c)", "q1 (t)"]} /></div>
  </div>

  <div class="cxarrow mono">-- CX 0→1 →</div>

  <div class="cxcol">
    <span class="lbl">output {pauliString(cxOutput)}</span>
    <div class="cxio"><PauliCells p={cxOutput} labels={["q0 (c)", "q1 (t)"]} /></div>
    <div class="bitnote mono">
      x₁ ^= x₀ = {cxInput.x[0] ? 1 : 0} → x₁ now {cxOutput.x[1] ? 1 : 0};
      z₀ ^= z₁ = {cxInput.z[1] ? 1 : 0} → z₀ now {cxOutput.z[0] ? 1 : 0}
    </div>
  </div>
</div>

<table class="rules mono">
  <thead><tr><th>generator</th><th>→ becomes</th><th>direction</th></tr></thead>
  <tbody>
    {#each cxRules as r (r.name)}
      <tr>
        <td class="lt">{r.name.replace("_c", "₍c₎").replace("_t", "₍t₎")}</td>
        <td class="lt" style="color:var(--accent)">{pauliString(r.out)}</td>
        <td class="muted">
          {r.name === "X_c" ? "X forward → target" : r.name === "Z_t" ? "Z backward → control" : "unchanged"}
        </td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
  .cxgrid {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 18px;
    align-items: center;
  }

  .cxcol {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .lbl {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .setrow {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .gbtn {
    min-width: 40px;
    font-size: 15px;
    font-weight: 700;
    padding: 7px 12px;
  }

  .gbtn.small {
    min-width: 32px;
    font-size: 13px;
    padding: 5px 9px;
  }

  .cxarrow {
    font-size: 13px;
    color: var(--accent);
    white-space: nowrap;
    text-align: center;
  }

  .cxio {
    margin-top: 2px;
  }

  .bitnote {
    font-size: 11.5px;
    color: var(--faint);
    line-height: 1.5;
  }

  .rules {
    border-collapse: collapse;
    font-size: 13px;
    margin-top: 16px;
    width: 100%;
  }

  .rules th,
  .rules td {
    padding: 5px 12px;
    text-align: left;
    border-bottom: 1px solid var(--line);
  }

  .rules th {
    color: var(--muted);
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .lt {
    font-weight: 700;
  }

  .muted {
    color: var(--muted);
  }

  @media (max-width: 760px) {
    .cxgrid {
      grid-template-columns: 1fr;
    }

    .cxarrow {
      transform: rotate(90deg);
    }
  }
</style>
