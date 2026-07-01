<script lang="ts">
  // Section 3 island: pick a starting Pauli, apply single-qubit Cliffords, and watch
  // the (x, z) bits and the sign rule fire in the tableau cell.
  import PauliCells from "./PauliCells.svelte";
  import { single, pauliString, apply1, type Pauli, type Gate1Name } from "./tableau";

  const G1: Gate1Name[] = ["H", "S", "S†", "X", "Y", "Z"];

  let s3 = $state<Pauli>(single(1, 0, "Z"));
  function gate3(name: Gate1Name): void {
    s3 = apply1(name, s3, 0);
  }
  function set3(letter: "I" | "X" | "Y" | "Z"): void {
    s3 = single(1, 0, letter);
  }
</script>

<div class="stage">
  <div class="setrow">
    <span class="lbl">start:</span>
    {#each (["I", "X", "Y", "Z"] as const) as l (l)}
      <button class="gbtn small mono" onclick={() => set3(l)}>{l}</button>
    {/each}
  </div>
  <div class="bigout"><PauliCells p={s3} labels={["q"]} /></div>
  <div class="gaterow">
    {#each G1 as g (g)}
      <button class="gbtn mono" onclick={() => gate3(g)}>{g}</button>
    {/each}
    <span class="curr mono">= {pauliString(s3)}</span>
  </div>
</div>

<style>
  .stage {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .setrow {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .lbl {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
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

  .bigout {
    margin: 4px 0;
  }

  .gaterow {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .curr {
    font-size: 15px;
    color: var(--accent);
    margin-left: 6px;
  }
</style>
