<script lang="ts">
  // Section 6 island: matching -> correction -> did the qubit survive? Pick a
  // scenario (short chain vs past-midpoint chain) or click qubits; the residual
  // (error XOR correction) reveals whether MWPM caused a logical error.
  import RepCode from "./RepCode.svelte";
  import { syndrome, minWeightMatching, logicalFailed, type MatchResult } from "./matching";

  const D = 9;

  function scenario(spanning: boolean): boolean[] {
    const e = new Array(D).fill(false);
    if (spanning) {
      // a long chain past the midpoint: the matcher pairs the lone defect to the
      // WRONG boundary, residual spans the line -> logical error.
      for (let q = 0; q <= 5; q += 1) {
        e[q] = true;
      }
    } else {
      for (let q = 2; q <= 4; q += 1) {
        e[q] = true;
      }
    }

    return e;
  }

  let errors = $state<boolean[]>(scenario(false));
  const defects = $derived(syndrome(errors));
  const match = $derived<MatchResult>(minWeightMatching(defects, D, 0.08));
  const failed = $derived(logicalFailed(errors, match.correction));
  // residual = error XOR correction.
  const residual = $derived(errors.map((e, i) => e !== match.correction[i]));

  let scen = $state<"safe" | "fail">("safe");
  function setScen(s: "safe" | "fail"): void {
    scen = s;
    errors = scenario(s === "fail");
  }

  function toggleQubit(q: number): void {
    errors = errors.map((e, i) => (i === q ? !e : e));
    scen = "safe";
  }
</script>

<div class="row gap">
  <button class:active={scen === "safe"} onclick={() => setScen("safe")}>short chain (safe)</button>
  <button class:active={scen === "fail"} onclick={() => setScen("fail")}>past-midpoint chain</button>
</div>
<RepCode
  d={D}
  {errors}
  {defects}
  matching={match.pairs}
  correction={match.correction}
  onToggleQubit={toggleQubit}
  height={48}
/>
<div class="outcome" class:bad={failed} class:ok={!failed}>
  {#if failed}
    <strong>LOGICAL ERROR.</strong> Correction + error wrap the line: the
    residual is the logical operator. The matcher chose the cheaper pairing,
    but the true chain was longer than half the code, so it guessed the wrong
    side.
  {:else}
    <strong>Survived.</strong> Residual is trivial: error and correction
    cancel. The logical bit is intact.
  {/if}
</div>
<div class="residual mono">
  residual = {residual.map((b) => (b ? "1" : "0")).join("")}
  {residual.every((b) => !b) ? "(identity)" : residual.every((b) => b) ? "(spans line -> logical)" : ""}
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }

  .mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }

  button.active {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-soft);
  }

  .outcome {
    margin-top: 14px;
    padding: 12px 14px;
    border-radius: var(--r-md);
    border: 1px solid var(--line);
    border-left-width: 3px;
    font-size: 14.5px;
    line-height: 1.55;
  }

  .outcome.ok {
    border-left-color: var(--ok);
    background: color-mix(in srgb, var(--ok) 8%, transparent);
  }

  .outcome.bad {
    border-left-color: var(--bad);
    background: color-mix(in srgb, var(--bad) 8%, transparent);
  }

  .residual {
    margin-top: 10px;
    font-size: 12.5px;
    color: var(--muted);
  }
</style>
