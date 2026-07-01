<script lang="ts">
  // Section 2 island: a Pauli is two bits + a sign. A static reference table sits
  // beside a live toggle-demo (flip x / z / sign and watch the tableau cell).
  import PauliCells from "./PauliCells.svelte";
  import { type Pauli } from "./tableau";

  let bx = $state(false);
  let bz = $state(true); // default Z
  let bsign = $state<0 | 1>(0);
  const bitsPauli = $derived<Pauli>({ x: [bx], z: [bz], sign: bsign });

  const pauliTable = [
    { letter: "I", x: 0, z: 0, note: "does nothing", color: "var(--faint)" },
    { letter: "X", x: 1, z: 0, note: "bit flip", color: "var(--x)" },
    { letter: "Z", x: 0, z: 1, note: "phase flip", color: "var(--z)" },
    { letter: "Y", x: 1, z: 1, note: "both (Y = iXZ)", color: "var(--y)" },
  ];
</script>

<div class="splitgrid">
  <table class="tbl mono">
    <thead><tr><th>Pauli</th><th>x</th><th>z</th><th>meaning</th></tr></thead>
    <tbody>
      {#each pauliTable as r (r.letter)}
        <tr>
          <td class="lt" style="color:{r.color}">{r.letter}</td>
          <td>{r.x}</td>
          <td>{r.z}</td>
          <td class="muted">{r.note}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  <div class="toggle-demo">
    <div class="tdrow">
      <button class="bitbtn" class:on={bx} style="--bc:var(--x)" onclick={() => (bx = !bx)}>x = {bx ? 1 : 0}</button>
      <button class="bitbtn" class:on={bz} style="--bc:var(--z)" onclick={() => (bz = !bz)}>z = {bz ? 1 : 0}</button>
      <button class="bitbtn" class:on={bsign === 1} style="--bc:var(--bad)" onclick={() => (bsign = (bsign ^ 1) as 0 | 1)}>sign = {bsign}</button>
    </div>
    <div class="tdout">
      <PauliCells p={bitsPauli} labels={["q"]} />
    </div>
    <p class="hint">Toggle the bits -- a whole tableau row is just many of these side by side.</p>
  </div>
</div>

<style>
  .splitgrid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 28px;
    align-items: start;
  }

  .tbl {
    border-collapse: collapse;
    font-size: 13px;
  }

  .tbl th,
  .tbl td {
    padding: 5px 12px;
    text-align: left;
    border-bottom: 1px solid var(--line);
  }

  .tbl th {
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

  .toggle-demo {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .tdrow {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .bitbtn {
    font-size: 13px;
    font-weight: 700;
    padding: 6px 12px;
    border-color: color-mix(in srgb, var(--bc) 35%, var(--line));
  }

  .bitbtn.on {
    border-color: var(--bc);
    background: color-mix(in srgb, var(--bc) 14%, transparent);
    color: var(--fg);
  }

  .tdout {
    margin: 4px 0;
  }

  .hint {
    font-size: 12.5px;
    color: var(--faint);
    margin: 8px 0 0;
  }

  @media (max-width: 760px) {
    .splitgrid {
      grid-template-columns: 1fr;
    }
  }
</style>
