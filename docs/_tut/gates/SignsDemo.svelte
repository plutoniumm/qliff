<script lang="ts">
  // Section 6 island: the sign bit IS the Z-measurement outcome. +Z stabilizes |0>
  // (measures 0), -Z stabilizes |1> (measures 1); an X flips +Z <-> -Z.
  import { single, pauliString, stateLabel, apply1, type Pauli } from "./tableau";

  let measPauli = $state<Pauli>(single(1, 0, "Z"));
  const measOutcome = $derived(measPauli.sign === 0 ? 0 : 1);
  function flipMeas(): void {
    // X flips +Z <-> -Z (the bit), demonstrating the sign carries the outcome.
    measPauli = apply1("X", measPauli, 0);
  }
  function resetMeas(): void {
    measPauli = single(1, 0, "Z");
  }
</script>

<div class="stage center">
  <div class="bigstate">
    <span class="ket mono">{stateLabel(measPauli)}</span>
    <span class="stab mono">{pauliString(measPauli)} → measure Z = <b style="color:{measOutcome === 0 ? 'var(--ok)' : 'var(--bad)'}">{measOutcome}</b></span>
  </div>
  <div class="gaterow">
    <button class="gbtn mono" onclick={flipMeas}>apply X</button>
    <button class="reset" onclick={resetMeas}>reset to +Z</button>
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
