<script lang="ts">
  // Left control panel. Chooses the source (template vs. the drawn freeform
  // lattice), the noise channel + strength (single p or a swept range), rounds,
  // shots, and the decoder. Surfaces a Compile readout and fires Run. It builds
  // the RunRequest and hands it back to Builder, which owns the API plumbing.
  import type {
    TemplateInfo,
    CodeFamily,
    DecoderName,
    RunRequest,
    CompileResponse,
    LatticeSpec,
  } from "$lib/schema";

  interface Props {
    templates: TemplateInfo[];
    spec: LatticeSpec; // current freeform lattice (from the canvas)
    compileResult: CompileResponse | null;
    compileError: string | null;
    running: boolean;
    runError: string | null;
    oncompile: (req: RunRequest) => void;
    onrun: (req: RunRequest) => void;
    onstop: () => void;
  }

  let {
    templates,
    spec,
    compileResult,
    compileError,
    running,
    runError,
    oncompile,
    onrun,
    onstop,
  }: Props = $props();

  let mode = $state<"template" | "freeform">("template");

  // template params
  let family = $state<CodeFamily>("rotated_surface");
  let distance = $state(3);

  // noise params
  let channel = $state("DEPOLARIZE1");
  let p = $state(0.001);
  let sweep = $state(false);
  let sweepMin = $state(0.001);
  let sweepMax = $state(0.02);
  let sweepSteps = $state(8);

  // run params
  let rounds = $state(3);
  let shots = $state(10000);
  let decoder = $state<DecoderName>("mwpm");

  // Keep family/decoder pointed at something the server actually offers.
  $effect(() => {
    if (templates.length > 0 && !templates.some((t) => t.family === family)) {
      family = templates[0].family;
    }
  });

  const channels = ["DEPOLARIZE1", "X_ERROR", "Z_ERROR"];

  // Available decoders. `transformer` is a planned ML decoder (needs its own
  // training loop) -- listed but disabled until that lands, so `decoder` only
  // ever holds a value the server can run.
  const decoders: { value: string; label: string; ready: boolean }[] = [
    {
      value: "mwpm",
      label: "MWPM (matching)",
      ready: true,
    },
    {
      value: "bposd",
      label: "BP+OSD",
      ready: true,
    },
    {
      value: "transformer",
      label: "Transformer (soon)",
      ready: false,
    },
  ];

  // Geometric sweep from min..max over `steps` points (log-spaced reads nicer on
  // a log axis); falls back to a single value when steps <= 1.
  function buildSweep(): number[] {
    const n = Math.max(1, Math.floor(sweepSteps));

    if (n === 1 || sweepMax <= sweepMin) {
      return [sweepMin];
    }

    const out: number[] = [];
    const lo = Math.log(sweepMin);
    const hi = Math.log(sweepMax);

    for (let i = 0; i < n; i++) {
      out.push(Math.exp(lo + ((hi - lo) * i) / (n - 1)));
    }

    return out;
  }

  function buildRequest(): RunRequest {
    const noise = sweep
      ? { channel, p_sweep: buildSweep() }
      : { channel, p };
    const base = {
      rounds,
      noise,
      shots,
      decoder,
    };

    if (mode === "template") {
      return { ...base, template: { family, distance } };
    }

    return { ...base, spec };
  }
</script>

<div class="panel">
  <div class="grp">
    <div class="hd">Source</div>
    <div class="seg">
      <button
        class:active={mode === "template"}
        onclick={() => (mode = "template")}>Template</button
      >
      <button
        class:active={mode === "freeform"}
        onclick={() => (mode = "freeform")}>Freeform</button
      >
    </div>

    {#if mode === "template"}
      <label>
        Family
        <select bind:value={family}>
          {#each templates as t (t.family)}
            <option value={t.family}>{t.label}</option>
          {/each}
          {#if templates.length === 0}
            <option value="rotated_surface">rotated_surface</option>
          {/if}
        </select>
      </label>
      <label>
        Distance
        <input type="number" min="2" step="1" bind:value={distance} />
      </label>
    {:else}
      <p class="hint">
        Using {spec.tiles.length} drawn tile{spec.tiles.length === 1 ? "" : "s"}
        from the canvas. The server resolves stabilizers/observables.
      </p>
    {/if}
  </div>

  <div class="grp">
    <div class="hd">Noise</div>
    <label>
      Channel
      <select bind:value={channel}>
        {#each channels as c}
          <option value={c}>{c}</option>
        {/each}
      </select>
    </label>
    <label class="row">
      <input type="checkbox" bind:checked={sweep} />
      Sweep p
    </label>
    {#if sweep}
      <div class="trio">
        <label>min<input type="number" step="0.0001" bind:value={sweepMin} /></label>
        <label>max<input type="number" step="0.0001" bind:value={sweepMax} /></label>
        <label>steps<input type="number" min="1" step="1" bind:value={sweepSteps} /></label>
      </div>
    {:else}
      <label>
        Strength p
        <input type="number" step="0.0001" min="0" max="1" bind:value={p} />
      </label>
    {/if}
  </div>

  <div class="grp">
    <div class="hd">Run</div>
    <label>Rounds<input type="number" min="1" step="1" bind:value={rounds} /></label>
    <label>Shots<input type="number" min="1" step="1000" bind:value={shots} /></label>
    <label>
      Decoder
      <select bind:value={decoder}>
        {#each decoders as d (d.value)}
          <option value={d.value} disabled={!d.ready}>{d.label}</option>
        {/each}
      </select>
    </label>
  </div>

  <div class="grp">
    <div class="actions">
      <button onclick={() => oncompile(buildRequest())} disabled={running}>
        Compile
      </button>
      {#if running}
        <button class="run stop" onclick={onstop}>Stop</button>
      {:else}
        <button class="run" onclick={() => onrun(buildRequest())}>Run</button>
      {/if}
    </div>

    {#if compileError !== null}
      <div class="readout err">Compile failed: {compileError}</div>
    {:else if compileResult !== null}
      <div class="readout" class:warn={!compileResult.ok}>
        <div>qubits: {compileResult.num_qubits}</div>
        <div>data: {compileResult.num_data}</div>
        <div>stabilizers: {compileResult.num_stabilizers}</div>
        <div>detectors: {compileResult.num_detectors}</div>
        <div>observables: {compileResult.num_observables}</div>
        {#if compileResult.warnings.length > 0}
          <ul class="warns">
            {#each compileResult.warnings as w}
              <li>{w}</li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}

    {#if runError !== null}
      <div class="readout err">Run error: {runError}</div>
    {/if}
  </div>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .grp {
    display: flex;
    flex-direction: column;
    gap: 9px;
  }

  .hd {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    padding-bottom: 6px;
    border-bottom: 1px solid var(--line);
  }

  /* tiny leading phase-gradient tick on each section heading */
  .hd::before {
    content: "";
    width: 2px;
    height: 12px;
    border-radius: 2px;
    background: var(--grad-phase);
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--muted);
  }

  label.row {
    flex-direction: row;
    align-items: center;
    gap: 7px;
  }

  input,
  select {
    width: 100%;
  }

  .seg {
    display: flex;
    gap: 6px;
  }

  .seg button {
    flex: 1;
  }

  .trio {
    display: flex;
    gap: 7px;
  }

  .trio label {
    flex: 1;
  }

  .trio input {
    width: 100%;
  }

  .actions {
    display: flex;
    gap: 8px;
  }

  .actions button {
    flex: 1;
  }

  .run {
    background: var(--grad-phase);
    color: var(--ink-on-accent);
    border-color: color-mix(in srgb, var(--accent) 55%, transparent);
    font-weight: 700;
  }

  .run:hover {
    box-shadow: var(--glow-accent);
  }

  /* Stop button: red family, with a live "run is streaming" pulse + sheen. */
  .run.stop {
    position: relative;
    overflow: hidden;
    background: color-mix(in srgb, var(--x) 22%, var(--panel));
    color: var(--fg);
    border-color: color-mix(in srgb, var(--x) 60%, transparent);
    font-weight: 700;
    animation: run-pulse 2.2s ease-in-out infinite;
  }

  .run.stop::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
      100deg,
      transparent 30%,
      color-mix(in srgb, var(--x) 45%, transparent) 50%,
      transparent 70%
    );
    transform: translateX(-100%);
    animation: run-sheen 1.6s ease-in-out infinite;
  }

  .run.stop:hover {
    border-color: var(--x);
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--x) 55%, transparent),
      0 10px 30px -12px color-mix(in srgb, var(--x) 70%, transparent);
  }

  @keyframes run-pulse {
    50% {
      box-shadow: 0 0 0 1px color-mix(in srgb, var(--x) 50%, transparent),
        0 8px 26px -12px color-mix(in srgb, var(--x) 70%, transparent);
    }
  }

  @keyframes run-sheen {
    to {
      transform: translateX(100%);
    }
  }

  .readout {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    padding: 10px 11px;
    line-height: 1.55;
  }

  .readout.warn {
    border-color: var(--x);
  }

  .readout.err {
    border-color: var(--x);
    color: var(--x);
  }

  .warns {
    margin: 4px 0 0;
    padding-left: 16px;
    color: var(--x);
  }

  .hint {
    font-size: 12px;
    color: var(--muted);
    line-height: 1.5;
    margin: 0;
  }
</style>
