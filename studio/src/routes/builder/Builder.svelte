<script lang="ts">
  // Part B entry: interactive surface-code builder. Layout is a left control
  // panel (source/noise/run + compile readout) over the tile palette, a main SVG
  // editing canvas, and an LER plot panel beneath them. This component owns the
  // CanvasModel, the API calls (compile + streaming run), and save/load.
  import { onMount, onDestroy } from "svelte";
  import { CanvasModel } from "$lib/canvas";
  import { getTemplates, compile, runStream, type RunHandle } from "$lib/api";
  import type {
    TemplateInfo,
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

  const model = new CanvasModel();

  // Re-read the model after the canvas mutates it in place.
  let modelTick = $state(0);

  function onCanvasChange(): void {
    modelTick += 1;
  }

  let armed = $state<TileKind | null>(null);
  let templates = $state<TemplateInfo[]>([]);

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

  onMount(async () => {
    try {
      templates = await getTemplates();
    } catch {
      // server may not be up yet; non-fatal — keep the default empty list.
    }
  });

  onDestroy(() => {
    handle?.close();
  });

  async function onCompile(req: RunRequest): Promise<void> {
    compileError = null;
    compileResult = null;
    try {
      compileResult = await compile(req);
    } catch (err) {
      compileError = String(err);
    }
  }

  function onRun(req: RunRequest): void {
    runError = null;
    points = [];
    running = true;
    handle = runStream(req, (e: RunEvent) => {
      if (e.type === "point" && e.point) {
        // new array ref so $state/the plot $effect notice the change
        points = [...points, e.point];
      } else if (e.type === "error") {
        runError = e.message ?? "unknown error";
        running = false;
      } else if (e.type === "done") {
        running = false;
      }
    });
  }

  function onStop(): void {
    handle?.close();
    running = false;
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
        {spec}
        {compileResult}
        {compileError}
        {running}
        {runError}
        oncompile={onCompile}
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
      <Canvas {model} {armed} onarm={(k) => (armed = k)} onchange={onCanvasChange} />
    </div>
    <div class="plot-panel glass">
      <div class="plot-hd gradient-text">Logical error rate</div>
      <LerPlot {points} />
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

  .plot-hd {
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 12px;
  }

  .files {
    display: flex;
    gap: 8px;
  }

  .files button {
    flex: 1;
  }
</style>
