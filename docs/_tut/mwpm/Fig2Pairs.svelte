<script lang="ts">
  // Section 2 island: a fixed syndrome (defects at gaps 2 and 6) with two
  // different error chains that both explain it. Flip between explanations.
  import RepCode from "./RepCode.svelte";
  import { syndrome } from "./matching";

  const D = 9;
  // distinct explanations (sets of flipped qubits) all giving the same syndrome.
  const explanations: { label: string; qubits: number[] }[] = [
    { label: "inner chain (4 flips)", qubits: [3, 4, 5, 6] },
    { label: "outer chain (5 flips)", qubits: [0, 1, 2, 7, 8] },
  ];
  let pick = $state(0);
  const errors = $derived.by(() => {
    const e = new Array(D).fill(false);
    for (const q of explanations[pick].qubits) {
      e[q] = true;
    }

    return e;
  });
  const defects = $derived(syndrome(errors));
</script>

<RepCode d={D} {errors} {defects} interactive={false} height={48} />
<div class="row gap wrap">
  {#each explanations as ex, i (i)}
    <button class:active={pick === i} onclick={() => (pick = i)}>{ex.label}</button>
  {/each}
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
    flex-wrap: wrap;
  }

  button.active {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-soft);
  }
</style>
