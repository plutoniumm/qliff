<script lang="ts">
  // The multi-observable np.any verdict rule as a tiny truth table: two logical
  // observables, click any bit; the shot fails the moment a single column
  // mismatches. Self-contained (was inline in Ler.svelte's Callout).
  import { C } from "$lib/colors";

  let obsA = $state<[boolean, boolean]>([true, false]); // predicted (2 observables)
  let obsB = $state<[boolean, boolean]>([true, true]); // true
  const rowWrong = $derived(obsA.some((v, i) => v !== obsB[i]));
</script>

<div class="tt">
  <div class="tt-col">
    <span class="tt-h">predicted</span>
    <div class="tt-cells">
      <button class="bit" class:on={obsA[0]} onclick={() => (obsA = [!obsA[0], obsA[1]])}>{obsA[0] ? "1" : "0"}</button>
      <button class="bit" class:on={obsA[1]} onclick={() => (obsA = [obsA[0], !obsA[1]])}>{obsA[1] ? "1" : "0"}</button>
    </div>
  </div>
  <div class="tt-col">
    <span class="tt-h">true</span>
    <div class="tt-cells">
      <button class="bit" class:on={obsB[0]} onclick={() => (obsB = [!obsB[0], obsB[1]])}>{obsB[0] ? "1" : "0"}</button>
      <button class="bit" class:on={obsB[1]} onclick={() => (obsB = [obsB[0], !obsB[1]])}>{obsB[1] ? "1" : "0"}</button>
    </div>
  </div>
  <div class="tt-col">
    <span class="tt-h">verdict</span>
    <div class="verdict" style="color:{rowWrong ? C.bad : C.ok}">
      {rowWrong ? "LOGICAL ERROR" : "survived"}
    </div>
  </div>
</div>
<p style="margin:10px 0 0; font-size:14px;">
  Two logical observables. Click any bit. The shot counts as wrong the moment a single
  column mismatches, so <span class="mono">10</span> vs <span class="mono">11</span> already fails.
</p>

<style>
  .tt {
    display: flex;
    gap: 26px;
    align-items: flex-start;
  }
  .tt-col {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }
  .tt-h {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .tt-cells {
    display: flex;
    gap: 6px;
  }
  .bit {
    width: 38px;
    height: 38px;
    font-family: var(--font-mono);
    font-size: 16px;
    font-weight: 700;
    color: var(--muted);
  }
  .bit.on {
    color: var(--fg);
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-soft);
  }
  .verdict {
    font-family: var(--font-mono);
    font-size: 14px;
    font-weight: 700;
    padding-top: 8px;
  }
  .mono {
    font-family: var(--font-mono);
  }
</style>
