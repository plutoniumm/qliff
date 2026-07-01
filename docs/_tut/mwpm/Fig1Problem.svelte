<script lang="ts">
  // Section 1 island: click data qubits to inject X errors and watch checks
  // light. Owns errors1 (was in the page component); RepCode is a pure renderer.
  import RepCode from "./RepCode.svelte";
  import { syndrome } from "./matching";

  const D = 9;
  let errors = $state<boolean[]>(new Array(D).fill(false));
  const defects = $derived(syndrome(errors));

  function toggleQubit(q: number): void {
    errors = errors.map((e, i) => (i === q ? !e : e));
  }

  function clearAll(): void {
    errors = new Array(D).fill(false);
  }

  function makeChain(): void {
    // a contiguous chain in the middle: lights only its two endpoints.
    const next = new Array(D).fill(false);
    for (let q = 3; q <= 5; q += 1) {
      next[q] = true;
    }
    errors = next;
  }
</script>

<RepCode d={D} {errors} {defects} onToggleQubit={toggleQubit} height={48} />
<div class="row gap">
  <button onclick={makeChain}>make a chain</button>
  <button onclick={clearAll}>clear</button>
  <span class="tag mono">{defects.length} defect{defects.length === 1 ? "" : "s"} lit</span>
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
    flex-wrap: wrap;
  }

  .tag {
    font-size: 12px;
    color: var(--muted);
  }

  .mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }
</style>
