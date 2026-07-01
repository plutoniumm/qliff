<script lang="ts">
  // Part B entry: interactive surface-code builder. Layout is a left control
  // panel (code/noise/run + live Surface stats) over the tile palette, a main
  // SVG editing canvas (only in freeform mode), and an LER plot panel beneath.
  // This component owns the CanvasModel, the API metadata fetches, the debounced
  // auto-compile, the run (WS with automatic REST fallback), and save/load.
  import { onMount, onDestroy } from "svelte";
  import { CanvasModel } from "$lib/canvas";
  import {
    getTemplates,
    getChannels,
    getDecoders,
    compile,
    runWithFallback,
    type RunHandle,
  } from "$lib/api";
  import type {
    TemplateInfo,
    DecoderInfo,
    ChannelInfo,
    RunRequest,
    CompileResponse,
    LerPoint,
    LatticeSpec,
    RunEvent,
  } from "$lib/schema";
  import Palette from "./Palette.svelte";
  import Canvas from "./Canvas.svelte";
  import ControlPanel from "./ControlPanel.svelte";
  import LerPlot from "./LerPlot.svelte";
  import type { TileKind } from "$lib/schema";

  // Hardcoded fallbacks matching the API contract, so the UI is never blocked
  // when an endpoint 404s during parallel backend development.
  const FALLBACK_TEMPLATES: TemplateInfo[] = [
    {
      family: "repetition",
      label: "Repetition",
      min_distance: 3,
      decoders: ["mwpm", "bposd", "mld", "tn"],
      patterns: ["css"],
      starts: ["Z"],
      edges: ["even"],
    },
    {
      family: "rotated_surface",
      label: "Rotated surface",
      min_distance: 3,
      decoders: ["mwpm", "bposd", "mld", "tn"],
      patterns: ["css", "xzzx"],
      starts: ["Z", "X"],
      edges: ["even", "odd"],
    },
    {
      family: "unrotated_surface",
      label: "Unrotated surface",
      min_distance: 3,
      decoders: ["mwpm", "bposd", "mld", "tn"],
      patterns: ["css", "xzzx"],
      starts: ["Z", "X"],
      edges: ["even"],
    },
    {
      family: "toric",
      label: "Toric",
      min_distance: 3,
      decoders: ["mwpm", "bposd", "mld", "tn"],
      patterns: ["css"],
      starts: ["Z"],
      edges: ["even"],
    },
    {
      family: "hex_color",
      label: "Hexagonal color",
      min_distance: 3,
      decoders: ["color", "bposd", "mld", "tn"],
      patterns: ["css"],
      starts: ["Z"],
      edges: ["even"],
    },
    {
      family: "triangular",
      label: "Triangular",
      min_distance: 3,
      decoders: ["color", "bposd", "mld", "tn"],
      patterns: ["css"],
      starts: ["Z"],
      edges: ["even"],
    },
    {
      family: "kagome",
      label: "Kagome",
      min_distance: 3,
      decoders: ["bposd", "mld", "tn"],
      patterns: ["css"],
      starts: ["Z"],
      edges: ["even"],
    },
  ];

  const FALLBACK_CHANNELS: ChannelInfo[] = [
    {
      name: "DEPOLARIZE1",
      label: "Depolarize (1q)",
      is_pauli: true,
      arg: "p",
      note: "Single-qubit depolarizing channel at rate p.",
    },
    {
      name: "DEPOLARIZE2",
      label: "Depolarize (2q)",
      is_pauli: true,
      arg: "p",
      note: "Two-qubit depolarizing channel at rate p.",
    },
    {
      name: "X_ERROR",
      label: "X error",
      is_pauli: true,
      arg: "p",
      note: "Bit-flip (X) with probability p.",
    },
    {
      name: "Z_ERROR",
      label: "Z error",
      is_pauli: true,
      arg: "p",
      note: "Phase-flip (Z) with probability p.",
    },
    {
      name: "PAULI_CHANNEL_1",
      label: "Pauli channel (1q)",
      is_pauli: true,
      arg: "vec3",
      note: "Independent (pX, pY, pZ) Pauli error probabilities.",
    },
    {
      name: "RZ",
      label: "Coherent RZ",
      is_pauli: false,
      arg: "theta",
      note: "Coherent over-rotation about Z by θ radians.",
    },
    {
      name: "RX",
      label: "Coherent RX",
      is_pauli: false,
      arg: "theta",
      note: "Coherent over-rotation about X by θ radians.",
    },
    {
      name: "AMPLITUDE_DAMP",
      label: "Amplitude damping",
      is_pauli: false,
      arg: "p",
      note: "Energy relaxation (T1) with damping probability p.",
    },
  ];

  const FALLBACK_DECODERS: DecoderInfo[] = [
    {
      name: "mwpm",
      label: "MWPM",
      pauli_only: true,
      note: "Minimum-weight perfect matching on the detector graph.",
    },
    {
      name: "bposd",
      label: "BP+OSD",
      pauli_only: true,
      note: "Belief propagation with ordered statistics decoding.",
    },
    {
      name: "mld",
      label: "MLD (exact TN)",
      pauli_only: true,
      note: "Exact maximum-likelihood decoding via tensor-network contraction.",
    },
    {
      name: "tn",
      label: "TN (truncated)",
      pauli_only: true,
      note: "Tensor-network decoder with bond-dimension truncation.",
    },
    {
      name: "coherent",
      label: "Coherent TN",
      pauli_only: false,
      note: "Tensor-network decoder for non-Pauli / coherent noise.",
    },
    {
      name: "color",
      label: "Color",
      pauli_only: true,
      note: "Dedicated color-code decoder (restriction / projection based).",
    },
  ];

  const model = new CanvasModel();

  // Re-read the model after the canvas mutates it in place.
  let modelTick = $state(0);

  function onCanvasChange(): void {
    modelTick += 1;
  }

  let armed = $state<TileKind | null>(null);
  let templates = $state<TemplateInfo[]>(FALLBACK_TEMPLATES);
  let channels = $state<ChannelInfo[]>(FALLBACK_CHANNELS);
  let decoders = $state<DecoderInfo[]>(FALLBACK_DECODERS);

  // The template key currently drawn on the canvas, so we only reseed when the
  // selected code/distance actually changes (and never clobber freeform edits).
  let seededKey = "";

  // The freeform spec, kept in sync with the canvas.
  let spec = $state<LatticeSpec>(model.toSpec());
  $effect(() => {
    // depend on modelTick so this recomputes after edits
    void modelTick;
    spec = model.toSpec();
  });

  // compile state
  let compileResult = $state<CompileResponse | null>(null);
  let compileError = $state<string | null>(null);

  // run state
  let running = $state(false);
  let runError = $state<string | null>(null);
  let points = $state<LerPoint[]>([]);
  let handle: RunHandle | null = null;

  // run progress / timing (client-side; the server streams one point per p).
  let expected = $state(0);
  let viaRest = $state(false); // true once we degrade to the blocking REST run
  let runStartMs = 0;
  let nowMs = $state(0);
  let doneMs = $state(0);

  // live elapsed clock while a run streams.
  $effect(() => {
    if (!running) {
      return;
    }

    const id = setInterval(() => {
      nowMs = performance.now();
    }, 100);

    return () => clearInterval(id);
  });

  let elapsedS = $derived(
    runStartMs === 0 ? 0 : ((running ? nowMs : doneMs) - runStartMs) / 1000,
  );

  onMount(async () => {
    // Fetch metadata; keep the hardcoded fallback on any failure (404 during
    // parallel backend dev, server down, etc.). Each is independent.
    const [t, c, d] = await Promise.allSettled([
      getTemplates(),
      getChannels(),
      getDecoders(),
    ]);

    if (t.status === "fulfilled" && t.value.length > 0) {
      templates = t.value;
    }

    if (c.status === "fulfilled" && c.value.length > 0) {
      channels = c.value;
    }

    if (d.status === "fulfilled" && d.value.length > 0) {
      decoders = d.value;
    }
  });

  onDestroy(() => {
    handle?.close();
  });

  // Surface stats source: the latest live RunRequest from the panel, debounced.
  let pendingReq: RunRequest | null = null;
  let compileTimer: ReturnType<typeof setTimeout> | null = null;

  // Selecting a named code CONSTRUCTS it on the always-visible canvas; "freeform"
  // keeps the current drawing as an editable starting point; "" clears it.
  function onSpecChange(next: string, dist: number): void {
    if (next === "") {
      model.clear();
      onCanvasChange();
      seededKey = "";

      return;
    }

    if (next === "freeform") {
      seededKey = "";

      return;
    }

    const key = `${next}:${dist}`;

    if (key !== seededKey) {
      model.loadTemplate(next, dist);
      onCanvasChange();
      seededKey = key;
    }
  }

  // True once a finished run is entirely LER=0 (nothing to plot on a log axis).
  let allZero = $derived(
    !running &&
      runError === null &&
      points.length > 0 &&
      points.every((pt) => pt.ler === 0),
  );

  // Debounced auto-compile (no Compile button). A null request (incomplete run
  // matrix or empty canvas) clears the stats so we never show a stale count.
  function onBuild(req: RunRequest | null): void {
    pendingReq = req;

    if (compileTimer !== null) {
      clearTimeout(compileTimer);
    }

    if (req === null) {
      compileResult = null;
      compileError = null;

      return;
    }

    if (running) {
      return;
    }

    compileTimer = setTimeout(() => {
      if (pendingReq !== null) {
        void onCompile(pendingReq);
      }
    }, 260);
  }

  async function onCompile(req: RunRequest): Promise<void> {
    compileError = null;
    try {
      compileResult = await compile(req);
    } catch (err) {
      compileError = String(err);
      compileResult = null;
    }
  }

  function onRun(req: RunRequest): void {
    runError = null;
    points = [];
    viaRest = false;
    expected = req.noise.p_sweep?.length ?? 1;
    runStartMs = performance.now();
    nowMs = runStartMs;
    doneMs = 0;
    running = true;
    handle = runWithFallback(req, (e: RunEvent) => {
      if (e.type === "point" && e.point) {
        // new array ref so $state/the plot $effect notice the change
        points = [...points, e.point];
      } else if (e.type === "fallback") {
        // degraded to the blocking REST run: switch to an indeterminate bar.
        viaRest = true;
      } else if (e.type === "error") {
        runError = e.message ?? "unknown error";
        doneMs = performance.now();
        running = false;
      } else if (e.type === "done") {
        doneMs = performance.now();
        running = false;
      }
    });
  }

  function onStop(): void {
    handle?.close();
    doneMs = performance.now();
    running = false;
  }

  // observed logical errors at a point (LER is the fraction over `shots`).
  function errorsAt(pt: LerPoint): number {
    return Math.round(pt.ler * pt.shots);
  }

  function fmtP(v: number): string {
    return v < 0.001 ? v.toExponential(1) : v.toFixed(4);
  }

  function fmtLer(pt: LerPoint): string {
    if (pt.ler === 0) {
      return `0 (<${(1 / pt.shots).toExponential(1)})`;
    }

    return pt.ler.toExponential(2);
  }

  function onSave(): void {
    const blob = new Blob([JSON.stringify(model.toSpec(), null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "lattice.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  let fileInput: HTMLInputElement | null = $state(null);

  async function onLoadFile(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];

    if (file === undefined) {
      return;
    }

    try {
      const parsed = JSON.parse(await file.text()) as LatticeSpec;
      model.fromSpec(parsed);
      onCanvasChange();
    } catch (err) {
      runError = `load failed: ${String(err)}`;
    }
    input.value = "";
  }
</script>

<section class="builder enter">
  <aside class="left glass">
    <div class="left-scroll">
      <ControlPanel
        {templates}
        {channels}
        {decoders}
        {spec}
        {compileResult}
        {compileError}
        {running}
        {runError}
        onspecchange={onSpecChange}
        onbuild={onBuild}
        onrun={onRun}
        onstop={onStop}
      />
      <Palette {armed} onarm={(k) => (armed = k)} />
      <div class="files">
        <button onclick={onSave}>Save JSON</button>
        <button onclick={() => fileInput?.click()}>Load JSON</button>
        <input
          bind:this={fileInput}
          type="file"
          accept="application/json,.json"
          onchange={onLoadFile}
          hidden
        />
      </div>
    </div>
  </aside>

  <main class="main">
    <div class="canvas-frame glass">
      <Canvas {model} {armed} rev={modelTick} onarm={(k) => (armed = k)} onchange={onCanvasChange} />
    </div>
    <div class="plot-panel glass">
      <div class="plot-top">
        <div class="plot-hd gradient-text">Logical error rate</div>
        <div class="status">
          {#if running && viaRest}
            <span class="dot live"></span>
            running over HTTP · {elapsedS.toFixed(1)}s
          {:else if running}
            <span class="dot live"></span>
            running {points.length}/{expected} · {elapsedS.toFixed(1)}s
          {:else if runError !== null}
            <span class="dot err"></span> error
          {:else if points.length > 0}
            <span class="dot ok"></span>
            done · {points.length} point{points.length === 1 ? "" : "s"} ·
            {elapsedS.toFixed(1)}s · {compileResult?.num_qubits ?? "?"} qubits
          {:else}
            idle
          {/if}
        </div>
      </div>

      {#if running && viaRest}
        <!-- blocking REST fallback: no per-point progress, so go indeterminate -->
        <div class="bar"><div class="fill indeterminate"></div></div>
      {:else if running && expected > 0}
        <div class="bar"><div class="fill" style:width={`${(points.length / expected) * 100}%`}></div></div>
      {/if}

      <LerPlot {points} />

      {#if allZero}
        <p class="zero-note">
          Every point came back <b>LER = 0</b> — no logical errors were
          observable for this code + channel, so there's nothing to plot on a log
          axis. A Z-basis memory (repetition / surface code) under Z-diagonal
          noise like <b>RZ</b> or <b>amplitude damping</b> has nothing to detect;
          try <b>RX</b>, a different code, or a larger p / θ.
        </p>
      {/if}

      {#if points.length > 0}
        <table class="results">
          <thead>
            <tr><th>p</th><th>LER</th><th>±σ</th><th>errors / shots</th></tr>
          </thead>
          <tbody>
            {#each [...points].sort((a, b) => a.p - b.p) as pt (pt.p)}
              <tr>
                <td>{fmtP(pt.p)}</td>
                <td>{fmtLer(pt)}</td>
                <td>{pt.stderr.toExponential(1)}</td>
                <td>{errorsAt(pt)} / {pt.shots}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </main>
</section>

<style>
  .builder {
    display: grid;
    grid-template-columns: 312px 1fr;
    gap: 16px;
    padding: 16px;
    height: calc(100vh - 53px);
  }

  .left {
    overflow: hidden;
  }

  .left-scroll {
    height: 100%;
    overflow-y: auto;
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .main {
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow: auto;
    min-height: 0;
  }

  .canvas-frame {
    padding: 12px;
    display: flex;
  }

  .plot-panel {
    padding: 18px;
  }

  .plot-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
  }

  .plot-hd {
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 99px;
    background: var(--faint);
  }

  .dot.live {
    background: var(--accent-2);
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent-2) 70%, transparent);
    animation: pulse 1.4s ease-out infinite;
  }

  .dot.ok {
    background: #4ade80;
  }

  .dot.err {
    background: var(--x);
  }

  @keyframes pulse {
    70% {
      box-shadow: 0 0 0 6px transparent;
    }
  }

  .bar {
    height: 4px;
    border-radius: 99px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    overflow: hidden;
    margin-bottom: 12px;
  }

  .bar .fill {
    height: 100%;
    background: var(--grad-phase);
    transition: width var(--dur) var(--ease-out);
  }

  /* indeterminate bar for the blocking REST fallback (no per-point progress). */
  .bar .fill.indeterminate {
    width: 35%;
    transition: none;
    animation: bar-slide 1.2s var(--ease-out) infinite;
  }

  @keyframes bar-slide {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(330%);
    }
  }

  .results {
    width: 100%;
    margin-top: 14px;
    border-collapse: collapse;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 12px;
  }

  .results th,
  .results td {
    text-align: right;
    padding: 4px 10px;
    border-bottom: 1px solid var(--line);
  }

  .results th:first-child,
  .results td:first-child {
    text-align: left;
  }

  .results th {
    color: var(--muted);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 10.5px;
    letter-spacing: 0.06em;
  }

  .results td {
    color: var(--fg);
  }

  .zero-note {
    margin: 14px 0 0;
    padding: 11px 13px;
    font-size: 12px;
    line-height: 1.55;
    color: var(--muted);
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
  }

  .zero-note b {
    color: var(--fg);
  }

  .files {
    display: flex;
    gap: 8px;
  }

  .files button {
    flex: 1;
  }
</style>
