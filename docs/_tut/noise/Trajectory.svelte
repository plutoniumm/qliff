<script lang="ts">
  // The single-shot stabilizer-trajectory stepper (centerpiece of section 03).
  // Self-contained: it owns the seed / error-rate / location controls itself and
  // builds the tiny rep-code circuit internally, so it lives as one standalone
  // island in the markdown page. At each noise location it draws
  // threshold = rng()*gamma and walks the branches' cumulative |w|, lighting the
  // branch that covers the draw. The Scrubber selects how many locations we have
  // revealed (0..nLoc; 0 = nothing fired).
  //
  // Everything here is a pure $derived of (circuit, seed, loc): no $effect writes
  // back into state, so there is no risk of effect_update_depth white-screens.
  import { C, withAlpha } from "$lib/colors";
  import Tex from "$lib/Math.svelte";
  import Slider from "$lib/Slider.svelte";
  import Scrubber from "$lib/Scrubber.svelte";
  import { runTrajectory, makeChannel, type Circuit, type Branch, type NoiseFire } from "./channels";

  // controls owned by this island (previously the parent page's prose-level
  // state -- moved in so the interactive is self-contained in the markdown page).
  let seed = $state(7);
  let p = $state(0.18);
  let loc = $state(0);

  const qubitLabels = ["q0", "q1", "q2", "q3"];

  // A small rep-code-style round: 4 data qubits in a line, each gets a
  // DEPOLARIZE1 location after preparation; 3 Z-checks read parities of
  // neighbours. We only need the noise locations to show a trajectory.
  function buildRepCircuit(nData: number, rate: number): Circuit {
    const instructions = [];
    for (let q = 0; q < nData; q += 1) {
      instructions.push({
        type: "noise" as const,
        channel: makeChannel("DEPOLARIZE1", rate, [q]),
        label: `DEPOLARIZE1 q${q}`,
      });
    }
    // Z-checks between neighbours -> detectors over (q, q+1).
    const detectors: number[][] = [];
    for (let q = 0; q < nData - 1; q += 1) {
      detectors.push([q, q + 1]);
    }
    // logical observable = parity of all data qubits.
    const observables = [Array.from({ length: nData }, (_, q) => q)];

    return { numQubits: nData, instructions, detectors, observables };
  }
  const circuit = $derived<Circuit>(buildRepCircuit(4, p));

  // The whole shot, computed once from (circuit, seed). The Scrubber only
  // changes WHICH part we display, not the underlying sampled shot.
  const run = $derived(runTrajectory(circuit, seed));
  const fires = $derived(run.fires);
  const nLoc = $derived(fires.length);

  // revealed fires (the dice rolls the user has stepped through so far).
  const shown = $derived(fires.slice(0, Math.min(loc, nLoc)));
  // the location whose dice-roll panel we spotlight (the most recent revealed).
  const current = $derived<NoiseFire | null>(loc > 0 && loc <= nLoc ? fires[loc - 1] : null);

  // running signed weight after the revealed locations.
  const weightSoFar = $derived(
    shown.reduce((w, f) => w * f.sample.factor, 1),
  );

  // ---- layout for the circuit strip ----
  // W is wide (160) and the per-qubit row pitch small so the viewBox is a thin
  // band: rendered height = panelWidth * stripH/W stays a flat strip instead of
  // a ~880px tower. A max-height cap on .strip is the belt-and-braces backstop.
  const W = 160;
  const padX = 14;
  const nQ = $derived(circuit.numQubits);
  function rowY(q: number, h: number): number {
    const top = 11;
    const bot = h - 8;
    return nQ === 1 ? (top + bot) / 2 : top + (q / (nQ - 1)) * (bot - top);
  }
  const stripH = $derived(14 + nQ * 11);

  // X position of each noise location along the wire, evenly spaced.
  function locX(i: number): number {
    if (nLoc <= 1) {
      return W / 2;
    }
    return padX + (i / (nLoc - 1)) * (W - 2 * padX);
  }

  // which qubit a fire sits on (first op's qubit, or the channel's first target).
  function fireQubit(f: NoiseFire): number {
    const ins = circuit.instructions[f.insIndex];
    if (ins.type === "noise") {
      return ins.channel.qubits[0];
    }
    return 0;
  }

  // colour for a fired Pauli branch.
  function branchColor(pauli: string): string {
    const p = pauli.replace(/[^XYZ]/g, "");
    if (p.includes("X")) {
      return C.x;
    }
    if (p.includes("Y")) {
      return C.y;
    }
    if (p.includes("Z")) {
      return C.z;
    }
    return C.muted;
  }

  // For the dice-roll panel: the branches of the current location and their
  // cumulative |w| boundaries (already computed inside sampleChannel).
  const curBranches = $derived<Branch[]>(
    current
      ? (() => {
          const ins = circuit.instructions[current.insIndex];
          return ins.type === "noise" ? ins.channel.branches() : [];
        })()
      : [],
  );
  const curGamma = $derived(
    curBranches.reduce((s, b) => s + Math.abs(b.weight), 0),
  );
</script>

<div class="traj">
  <div class="traj-controls">
    <Slider bind:value={seed} min={0} max={9999} step={1} label="seed" />
    <Slider bind:value={p} min={0.02} max={0.4} step={0.005} label="error rate p" format={(v) => v.toFixed(3)} />
    <Scrubber bind:value={loc} min={0} max={nLoc} label="location" />
  </div>

  <!-- the circuit strip with noise locations -->
  <svg viewBox={`0 0 ${W} ${stripH}`} class="strip" role="img" aria-label="circuit">
    {#each Array(nQ) as _, q (q)}
      {@const y = rowY(q, stripH)}
      <line x1={padX} y1={y} x2={W - padX} y2={y} stroke={C.line} stroke-width="0.4" />
      <text x={2} y={y + 1.3} class="qlbl" text-anchor="start">
        {qubitLabels ? qubitLabels[q] : `q${q}`}
      </text>
    {/each}

    {#each fires as f, i (i)}
      {@const x = locX(i)}
      {@const y = rowY(fireQubit(f), stripH)}
      {@const revealed = i < loc}
      {@const isCur = i === loc - 1}
      {@const acted = revealed && f.sample.branch.ops.length > 0}
      <g class="loc" class:dim={!revealed}>
        {#if isCur}
          <circle cx={x} cy={y} r={4.4} fill={withAlpha(C.accent, 0.18)} />
        {/if}
        <rect
          x={x - 2.7}
          y={y - 2.7}
          width={5.4}
          height={5.4}
          rx={1.2}
          fill={!revealed
            ? withAlpha(C.muted, 0.1)
            : acted
              ? withAlpha(branchColor(f.sample.branch.pauli), 0.85)
              : withAlpha(C.ok, 0.18)}
          stroke={!revealed
            ? withAlpha(C.muted, 0.4)
            : acted
              ? branchColor(f.sample.branch.pauli)
              : withAlpha(C.ok, 0.7)}
          stroke-width="0.6"
        />
        {#if revealed}
          <text x={x} y={y + 1.3} class="plbl" text-anchor="middle">
            {f.sample.branch.ops.length === 0 ? "I" : f.sample.branch.pauli}
          </text>
        {:else}
          <text x={x} y={y + 1.4} class="qmk" text-anchor="middle">?</text>
        {/if}
      </g>
    {/each}
  </svg>

  <!-- dice-roll panel for the current location -->
  {#if current}
    {@const s = current.sample}
    <div class="dice">
      <div class="dice-head">
        <span class="loc-name mono">{current.label}</span>
        <span class="draw mono">
          draw = rng()·γ = {s.threshold.toFixed(3)} &nbsp; (γ = {curGamma.toFixed(3)})
        </span>
      </div>
      <!-- the cumulative |w| bar; threshold marker shows which branch covers it -->
      <div class="bar" style={`--g:${curGamma}`}>
        {#each curBranches as b, bi (bi)}
          {@const wabs = Math.abs(b.weight)}
          {@const fired = bi === s.index}
          <div
            class="seg"
            class:fired
            style={`flex:${wabs}; background:${
              fired
                ? withAlpha(branchColor(b.pauli), 0.55)
                : withAlpha(C.line, 0.5)
            }; border-color:${fired ? branchColor(b.pauli) : "transparent"};`}
            title={`${b.pauli}: |w|=${wabs.toFixed(4)}`}
          >
            {#if wabs / curGamma > 0.08}
              <span class="seg-lbl mono">{b.pauli}</span>
            {/if}
          </div>
        {/each}
        <div
          class="marker"
          style={`left:${(s.threshold / curGamma) * 100}%`}
          aria-hidden="true"
        ></div>
      </div>
      <div class="dice-foot">
        fired branch <strong style={`color:${branchColor(s.branch.pauli)}`}>{s.branch.pauli}</strong>
        {#if s.branch.weight < 0}
          <span class="neg">weight {s.branch.weight.toFixed(3)} &lt; 0 → factor {s.factor.toFixed(2)}</span>
        {:else if Math.abs(s.factor - 1) > 1e-9}
          <span class="muted">factor sign(w)·γ = {s.factor.toFixed(2)}</span>
        {:else}
          <span class="muted">factor = 1 (Pauli)</span>
        {/if}
      </div>
    </div>
  {:else}
    <div class="dice empty">
      Step forward to roll the dice at the first noise location.
    </div>
  {/if}

  <!-- running totals -->
  <div class="totals">
    <span>locations fired: <strong class="mono">{Math.min(loc, nLoc)} / {nLoc}</strong></span>
    <span>
      importance weight <Tex expr={String.raw`\prod \operatorname{sign}(w)\,\gamma`} /> =
      <strong class="mono" class:neg={weightSoFar < 0}>{weightSoFar.toFixed(3)}</strong>
    </span>
  </div>
</div>

<style>
  .traj {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .traj-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 14px;
    align-items: end;
  }

  .strip {
    width: 100%;
    height: auto;
    /* viewBox is 160 x ~58 -> a flat band (~250px tall on a wide panel). The
       cap is the backstop on extra-wide screens; default preserveAspectRatio
       (xMidYMid meet) letterboxes, so it never distorts. */
    max-height: 200px;
    display: block;
  }

  .qlbl {
    font-size: 2.6px;
    fill: var(--muted);
    font-family: var(--mono, ui-monospace, monospace);
  }

  .plbl {
    font-size: 2.8px;
    font-weight: 700;
    fill: #0b0f1e;
    pointer-events: none;
    font-family: var(--mono, ui-monospace, monospace);
  }

  .qmk {
    font-size: 3px;
    font-weight: 700;
    fill: var(--muted);
    font-family: var(--mono, ui-monospace, monospace);
  }

  .loc.dim {
    opacity: 0.85;
  }

  .dice {
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    padding: 12px 14px;
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
  }

  .dice.empty {
    color: var(--muted);
    font-size: 14px;
    text-align: center;
  }

  .dice-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 9px;
    flex-wrap: wrap;
  }

  .loc-name {
    font-size: 13px;
    font-weight: 700;
    color: var(--accent);
  }

  .draw {
    font-size: 12px;
    color: var(--muted);
  }

  .bar {
    position: relative;
    display: flex;
    height: 26px;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid var(--line);
  }

  .seg {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 0;
    border-right: 1px solid color-mix(in srgb, var(--bg-2) 80%, transparent);
    border-top: 2px solid transparent;
    border-bottom: 2px solid transparent;
  }

  .seg.fired {
    border-top-width: 0;
    border-bottom-width: 0;
  }

  .seg-lbl {
    font-size: 10px;
    color: var(--fg);
    white-space: nowrap;
    pointer-events: none;
  }

  .marker {
    position: absolute;
    top: -3px;
    bottom: -3px;
    width: 2px;
    background: var(--fg);
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--bg-2) 90%, transparent);
    transform: translateX(-1px);
  }

  .dice-foot {
    margin-top: 9px;
    font-size: 13.5px;
    color: var(--fg);
  }

  .dice-foot .muted {
    color: var(--muted);
    margin-left: 6px;
    font-size: 12.5px;
  }

  .neg {
    color: var(--bad);
    margin-left: 6px;
    font-size: 12.5px;
  }

  .totals {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    font-size: 13.5px;
    color: var(--muted);
  }

  .totals strong {
    color: var(--fg);
  }

  .totals strong.neg {
    color: var(--bad);
  }
</style>
