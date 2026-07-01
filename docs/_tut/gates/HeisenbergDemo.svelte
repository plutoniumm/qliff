<script lang="ts">
  // Section 1 island: the single stabilizer of a 1-qubit state moves under a gate,
  // and the ket it pins down changes with it. State lived in the old page component;
  // it now lives here so the island is self-contained.
  import { single, pauliString, stateLabel, apply1, type Pauli, type Gate1Name } from "./tableau";

  const G1: Gate1Name[] = ["H", "S", "S†", "X", "Y", "Z"];

  let s1 = $state<Pauli>(single(1, 0, "Z")); // start at +Z = |0>
  const s1label = $derived(stateLabel(s1));

  function gate1(name: Gate1Name): void {
    s1 = apply1(name, s1, 0);
  }
  function reset1(): void {
    s1 = single(1, 0, "Z");
  }
</script>

<div class="stage center">
  <div class="bigstate">
    <span class="ket mono">{s1label}</span>
    <span class="stab mono">stabilizer {pauliString(s1)}</span>
  </div>
  <div class="gaterow">
    {#each G1 as g (g)}
      <button class="gbtn mono" onclick={() => gate1(g)}>{g}</button>
    {/each}
    <button class="reset" onclick={reset1}>reset to |0⟩</button>
  </div>
</div>

<style>
  .stage {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .stage.center {
    align-items: center;
  }

  .bigstate {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }

  .ket {
    font-size: 44px;
    font-weight: 700;
    color: var(--fg);
    line-height: 1;
  }

  .stab {
    font-size: 13px;
    color: var(--muted);
  }

  .gaterow {
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

  .reset {
    margin-left: 6px;
    font-size: 12px;
  }
</style>
