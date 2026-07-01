<script lang="ts">
  // Section 5 island (KEPT AS A CLUSTER): a single fault injected before an
  // entangling gate spreads through a 4-qubit GHZ / cat-state encoder
  //   H q0; CX 0->1; CX 0->2; CX 0->3
  // the same CX fan-out a syndrome-extraction round uses. The old page component
  // shared its scrubber state with the <Circuit> figure; since a markdown page
  // cannot hold that reactive state, the scrubber, the inject controls and the
  // Circuit stay together in this one island. The scrubber is inlined (it was the
  // shared $lib/Scrubber) so the island has no external control dependency.
  import { onDestroy } from "svelte";
  import Circuit, { type Op } from "./Circuit.svelte";
  import { single, pauliString, apply1, withCX, type Pauli } from "./tableau";

  const NQ5 = 4;
  const OPS5: Op[] = [
    { kind: "H", a: 0 },
    { kind: "CX", a: 0, b: 1 },
    { kind: "CX", a: 0, b: 2 },
    { kind: "CX", a: 0, b: 3 },
  ];

  let injType = $state<"X" | "Z">("X");
  let injQubit = $state(0);
  // inject the fault BEFORE this column index (0..OPS5.length).
  let injStep = $state(1);
  let frame5step = $state(OPS5.length); // scrub position (columns executed)

  // Pure: build the Pauli frame after `step` columns, given the injected fault.
  // The fault is inserted just before column `injStep`; columns at/after the
  // injection that have executed then conjugate it.
  function frameAt(step: number): Pauli {
    // start identity; the fault only exists from injStep onward.
    let p: Pauli = single(NQ5, injQubit, injType);
    if (step < injStep) {
      return single(NQ5, 0, "I"); // nothing on the wires yet (before injection)
    }
    // apply every gate from column injStep .. step-1.
    for (let col = injStep; col < step; col += 1) {
      const op = OPS5[col];
      if (op.kind === "H") {
        p = apply1("H", p, op.a);
      } else if (op.kind === "CX" && op.b !== undefined) {
        p = withCX(p, op.a, op.b);
      }
    }

    return p;
  }

  const frame5 = $derived(frameAt(frame5step));
  const finalFrame5 = $derived(frameAt(OPS5.length));
  // final support = qubits carrying a non-identity Pauli at the end.
  const finalSupport5 = $derived.by(() => {
    const s: number[] = [];
    for (let q = 0; q < NQ5; q += 1) {
      if (finalFrame5.x[q] || finalFrame5.z[q]) {
        s.push(q);
      }
    }

    return s;
  });

  function setInject(type: "X" | "Z", qubit: number, step: number): void {
    injType = type;
    injQubit = qubit;
    injStep = step;
    frame5step = OPS5.length;
  }

  // ----- inlined scrubber (was $lib/Scrubber) --------------------------------
  const SMIN = 0;
  const SMAX = OPS5.length;
  let timer: ReturnType<typeof setInterval> | null = $state(null);

  function stopPlay(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }
  function play(): void {
    if (timer !== null) {
      stopPlay();

      return;
    }
    if (frame5step >= SMAX) {
      frame5step = SMIN;
    }
    timer = setInterval(() => {
      if (frame5step >= SMAX) {
        stopPlay();

        return;
      }
      frame5step += 1;
    }, 700);
  }
  function stepBy(delta: number): void {
    stopPlay();
    frame5step = Math.max(SMIN, Math.min(SMAX, frame5step + delta));
  }
  onDestroy(stopPlay);
</script>

<Circuit
  nq={NQ5}
  ops={OPS5}
  frame={frame5}
  step={frame5step}
  injectStep={injStep}
  injectQubit={injQubit}
  finalSupport={finalSupport5}
/>

<div class="scrubber">
  <button class="play" class:on={timer !== null} onclick={play} aria-label="play / pause">
    {timer !== null ? "❚❚" : "▶"}
  </button>
  <button onclick={() => stepBy(-1)} disabled={frame5step <= SMIN} aria-label="previous">‹</button>
  <input type="range" min={SMIN} max={SMAX} step="1" bind:value={frame5step} oninput={stopPlay} />
  <button onclick={() => stepBy(1)} disabled={frame5step >= SMAX} aria-label="next">›</button>
  <span class="readout mono">after gate {frame5step}/{SMAX}</span>
</div>

<div class="injrow">
  <span class="lbl">inject:</span>
  <button class="gbtn small mono" class:on={injType === "X"} onclick={() => setInject("X", injQubit, injStep)}>X</button>
  <button class="gbtn small mono" class:on={injType === "Z"} onclick={() => setInject("Z", injQubit, injStep)}>Z</button>
  <span class="lbl">on qubit:</span>
  {#each Array(NQ5) as _, q (q)}
    <button class="gbtn small mono" class:on={injQubit === q} onclick={() => setInject(injType, q, injStep)}>q{q}</button>
  {/each}
  <span class="lbl">before gate:</span>
  {#each Array(OPS5.length) as _, c (c)}
    <button class="gbtn small mono" class:on={injStep === c} onclick={() => setInject(injType, injQubit, c)}>#{c}</button>
  {/each}
</div>

<div class="finalbar mono">
  final error: <span style="color:var(--accent)">{pauliString(finalFrame5)}</span>
  &nbsp;·&nbsp; support = {finalSupport5.length} qubit{finalSupport5.length === 1 ? "" : "s"}
</div>

<style>
  .scrubber {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
  }

  .scrubber input[type="range"] {
    flex: 1;
  }

  .scrubber button {
    padding: 6px 11px;
  }

  .play.on {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-soft);
  }

  .readout {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    min-width: 84px;
    text-align: right;
  }

  .injrow {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 12px;
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

  .gbtn.on {
    border-color: color-mix(in srgb, var(--accent) 65%, transparent);
    background: var(--grad-soft);
  }

  .finalbar {
    margin-top: 12px;
    font-size: 13px;
    color: var(--muted);
  }
</style>
