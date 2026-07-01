<script lang="ts">
  // Left control panel. ONE "Code" dropdown selects a template family or
  // "Freeform (draw)" (which reveals the canvas); the noise channel is rendered
  // from /api/channels with the right input per arg (single p, theta, or a
  // vec3), and the decoder from /api/decoders. There is no Compile button: an
  // always-on Surface stats panel is fed by Builder's debounced auto-compile.
  // Non-Pauli channels steer the decoder to "coherent" and warn that DEM
  // decoders can't honestly handle them. Builds the RunRequest for Builder.
  import type {
    TemplateInfo,
    DecoderInfo,
    ChannelInfo,
    CodeFamily,
    DecoderName,
    SurfacePattern,
    SurfaceStart,
    SurfaceEdge,
    RunRequest,
    NoiseModel,
    CompileResponse,
    LatticeSpec,
  } from "$lib/schema";
  import {
    PATTERN_OPTIONS,
    START_OPTIONS,
    EDGE_OPTIONS,
    type VariantOption,
  } from "$lib/variants";

  // Group the code families under titled + subtitled headers in the picker. The
  // families themselves come from /api/templates (availability is backend-driven);
  // this only decides grouping + copy. Anything the backend adds that is not listed
  // here falls into a trailing "Other" group, so a new family never disappears.
  const FAMILY_GROUPS: { title: string; subtitle: string; families: CodeFamily[] }[] = [
    {
      title: "Planar codes",
      subtitle: "square lattice, matching-friendly",
      families: ["repetition", "rotated_surface", "unrotated_surface", "toric"],
    },
    {
      title: "Triangular axes",
      subtitle: "color code + medial surface codes",
      families: ["hex_color", "triangular", "kagome"],
    },
  ];
  const FAMILY_SUB: Partial<Record<CodeFamily, string>> = {
    repetition: "1D bit-flip chain",
    rotated_surface: "the workhorse d x d patch",
    unrotated_surface: "CSS, both check types",
    toric: "periodic, two logicals",
    hex_color: "6.6.6 color code (non-graphlike)",
    triangular: "triangular surface code",
    kagome: "medial: X-tri / Z-hex",
  };

  interface CodeGroup {
    title: string;
    subtitle: string;
    items: TemplateInfo[];
  }

  // Partition the backend templates into the display groups, dropping empty ones.
  function groupTemplates(all: TemplateInfo[]): CodeGroup[] {
    const seen = new Set<string>();
    const groups: CodeGroup[] = [];

    for (const g of FAMILY_GROUPS) {
      const items = all.filter((t) => g.families.includes(t.family));

      for (const t of items) {
        seen.add(t.family);
      }

      if (items.length > 0) {
        groups.push({
          title: g.title,
          subtitle: g.subtitle,
          items,
        });
      }
    }

    const rest = all.filter((t) => !seen.has(t.family));

    if (rest.length > 0) {
      groups.push({
        title: "Other",
        subtitle: "additional families",
        items: rest,
      });
    }

    return groups;
  }

  interface Props {
    templates: TemplateInfo[];
    channels: ChannelInfo[];
    decoders: DecoderInfo[];
    spec: LatticeSpec; // current freeform lattice (from the canvas)
    compileResult: CompileResponse | null;
    compileError: string | null;
    running: boolean;
    runError: string | null;
    onspecchange: (code: string, distance: number) => void; // "" | "freeform" | family
    onbuild: (req: RunRequest | null) => void; // live request for auto-compile
    onrun: (req: RunRequest) => void;
    onstop: () => void;
  }

  let {
    templates,
    channels,
    decoders,
    spec,
    compileResult,
    compileError,
    running,
    runError,
    onspecchange,
    onbuild,
    onrun,
    onstop,
  }: Props = $props();

  // Single source-of-truth selector. "" = nothing chosen (placeholder, so we
  // never pre-select a random code); "freeform" reveals the canvas; anything
  // else is a template family.
  let code = $state<string>("");
  let distance = $state(3);
  // Stabiliser-pattern knobs for the surface families, held in one record so the
  // selector loop below can bind variant[key]; reset to the css/Z/even default
  // whenever the family changes (every family supports it).
  let variant = $state<Record<"pattern" | "start" | "edge", SurfacePattern | SurfaceStart | SurfaceEdge>>({
    pattern: "css",
    start: "Z",
    edge: "even",
  });

  let isFreeform = $derived(code === "freeform");
  let isTemplate = $derived(code !== "" && code !== "freeform");
  let codeGroups = $derived(groupTemplates(templates));

  // The picked family's metadata.
  let codeTemplate = $derived<TemplateInfo | null>(
    templates.find((t) => t.family === code) ?? null,
  );

  // Keep only the canonical options this family offers along an axis (defaulting to
  // the first when it lists none); one option => that axis's selector stays hidden.
  function offered<T>(all: VariantOption<T>[], allowed: T[] | undefined): VariantOption<T>[] {
    if (allowed === undefined) {
      return [all[0]];
    }

    return all.filter((o) => allowed.includes(o.value));
  }

  // One config row per knob axis, driving a single selector loop in the template.
  let variantAxes = $derived([
    { key: "pattern" as const, label: "Stabiliser type", options: offered(PATTERN_OPTIONS, codeTemplate?.patterns) },
    { key: "start" as const, label: "Colouring", options: offered(START_OPTIONS, codeTemplate?.starts) },
    { key: "edge" as const, label: "Boundary", options: offered(EDGE_OPTIONS, codeTemplate?.edges) },
  ]);

  // Tell Builder which source is active + at what distance so it can draw the
  // selected code on the always-visible canvas. This is fired IMPERATIVELY from
  // the code/distance change handlers below -- never from an $effect: a reactive
  // effect here writes back into the shared canvas model (modelTick -> spec) and
  // re-triggers itself, which is an infinite effect loop (effect_update_depth).
  function emitSpec(): void {
    onspecchange(code, distance);
  }

  // Family changed: drop any variant the new family doesn't offer (always safe to
  // fall back to css_z), then redraw the canvas. Variant itself doesn't change the
  // geometry, so it never needs to flow through onspecchange.
  function onCodeChange(): void {
    variant = { pattern: "css", start: "Z", edge: "even" };
    emitSpec();
  }

  // noise: explicit "— select —" placeholder; no random default channel.
  let channel = $state<string>("");
  let p = $state(0.001);
  let theta = $state(0.05);
  let vx = $state(0.001);
  let vy = $state(0.001);
  let vz = $state(0.001);
  let sweep = $state(true);
  let sweepMin = $state(0.001);
  let sweepMax = $state(0.05);
  let sweepSteps = $state(8);

  // run params
  let rounds = $state(3);
  let shots = $state(10000);
  let decoder = $state<DecoderName | "">("");
  // True once the user touches the decoder, so auto-steering stops overriding.
  let decoderTouched = $state(false);

  let channelInfo = $derived<ChannelInfo | null>(
    channels.find((c) => c.name === channel) ?? null,
  );
  let decoderInfo = $derived<DecoderInfo | null>(
    decoders.find((d) => d.name === decoder) ?? null,
  );
  let nonPauli = $derived(channelInfo !== null && !channelInfo.is_pauli);
  // Only p / vec3 args can be swept; theta is a single coherent angle.
  let sweepable = $derived(channelInfo === null || channelInfo.arg === "p");

  // Steer the decoder when a channel is picked: coherent for non-Pauli noise,
  // mwpm for Pauli — unless the user has explicitly chosen a decoder.
  $effect(() => {
    if (decoderTouched || channelInfo === null) {
      return;
    }

    decoder = nonPauli ? "coherent" : "mwpm";
  });

  // A DEM decoder picked against non-Pauli noise: honest-decoding warning.
  let demOnNonPauli = $derived(
    nonPauli &&
      decoderInfo !== null &&
      decoderInfo.pauli_only,
  );

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

  // The noise payload, shaped by the channel's `arg`.
  function buildNoise(): NoiseModel {
    if (channelInfo?.arg === "theta") {
      return { channel, theta };
    }

    if (channelInfo?.arg === "vec3") {
      return { channel, vec3: [vx, vy, vz] };
    }

    return sweep ? { channel, p_sweep: buildSweep() } : { channel, p };
  }

  // The full RunRequest, or null when the run matrix isn't complete yet (no
  // code, no channel, no decoder). Builder uses null to clear stale stats.
  function buildRequest(): RunRequest | null {
    if (
      code === "" ||
      channel === "" ||
      decoder === ""
    ) {
      return null;
    }

    const base = {
      rounds,
      noise: buildNoise(),
      shots,
      decoder: decoder as DecoderName,
    };

    if (isFreeform) {
      return { ...base, spec };
    }

    return {
      ...base,
      template: {
        family: code as CodeFamily,
        distance,
        pattern: variant.pattern as SurfacePattern,
        start: variant.start as SurfaceStart,
        edge: variant.edge as SurfaceEdge,
      },
    };
  }

  let canRun = $derived(
    code !== "" &&
      channel !== "" &&
      decoder !== "",
  );

  // Hand Builder a live request (or null) whenever any structural input changes,
  // so it can debounce-compile the Surface stats and gate the Run button.
  $effect(() => {
    // touch every structural dep so this effect re-runs on any change.
    const sig = JSON.stringify({
      code,
      distance,
      pattern: variant.pattern,
      start: variant.start,
      edge: variant.edge,
      rounds,
      channel,
      arg: channelInfo?.arg,
      theta,
      vx,
      vy,
      vz,
      sweep,
      sweepMin,
      sweepMax,
      sweepSteps,
      p,
      decoder,
      boundary: spec.boundary,
      tiles: spec.tiles,
    });
    void sig;

    onbuild(buildRequest());
  });

  // Honest freeform readout: the server resolves *square* tiles by bounding box
  // into a rotated-surface patch (gaps ignored); tri/hex tiles aren't simulated.
  let freeform = $derived.by(() => {
    const sq = spec.tiles.filter((t) => t.kind === "square");
    const other = spec.tiles.length - sq.length;

    if (sq.length === 0) {
      return {
        sq: 0,
        other,
        rows: 0,
        cols: 0,
      };
    }

    const rows = sq.map((t) => t.row);
    const cols = sq.map((t) => t.col);

    return {
      sq: sq.length,
      other,
      rows: Math.max(...rows) - Math.min(...rows) + 1,
      cols: Math.max(...cols) - Math.min(...cols) + 1,
    };
  });

  // Is anything actually placed/selected to compile? Empty => show "empty",
  // never a stale qubit count.
  let hasContent = $derived(isTemplate || (isFreeform && freeform.sq > 0));

  function fire(): void {
    const req = buildRequest();

    if (req !== null) {
      onrun(req);
    }
  }
</script>

<div class="panel">
  <div class="grp">
    <div class="hd">Code</div>
    <label>
      Code
      <select class="code-select" bind:value={code} onchange={onCodeChange}>
        <button>
          <selectedcontent></selectedcontent>
        </button>
        <option value="" disabled>— select a code —</option>
        {#each codeGroups as g (g.title)}
          <optgroup label={`${g.title} -- ${g.subtitle}`}>
            <legend>
              <span class="g-title">{g.title}</span>
              <span class="g-sub">{g.subtitle}</span>
            </legend>
            {#each g.items as t (t.family)}
              <option value={t.family}>
                <span class="o-title">{t.label}</span>
                {#if FAMILY_SUB[t.family]}
                  <span class="o-sub">{FAMILY_SUB[t.family]}</span>
                {/if}
              </option>
            {/each}
          </optgroup>
        {/each}
        <optgroup label="Custom -- draw your own">
          <legend>
            <span class="g-title">Custom</span>
            <span class="g-sub">draw your own lattice</span>
          </legend>
          <option value="freeform">
            <span class="o-title">Freeform (draw)</span>
            <span class="o-sub">place tiles on the canvas</span>
          </option>
        </optgroup>
      </select>
    </label>

    {#if isTemplate}
      <label>
        Distance
        <input type="number" min="2" step="1" bind:value={distance} oninput={emitSpec} />
      </label>
      {#each variantAxes as axis (axis.key)}
        {#if axis.options.length > 1}
          <label>
            {axis.label}
            <select bind:value={variant[axis.key]}>
              {#each axis.options as o (o.value)}
                <option value={o.value}>{o.label}</option>
              {/each}
            </select>
          </label>
        {/if}
      {/each}
    {:else if isFreeform}
      <p class="hint">
        {#if freeform.sq > 0}
          {freeform.sq} square tile{freeform.sq === 1 ? "" : "s"} →
          <b>{freeform.rows}×{freeform.cols}</b> rotated-surface patch (resolved
          from the bounding box; gaps are ignored).
        {:else}
          Draw <b>square</b> tiles on the canvas to define a patch.
        {/if}
        {#if freeform.other > 0}
          <span class="warntext">
            {freeform.other} tri/hex tile{freeform.other === 1 ? "" : "s"} are
            diagram-only and won't be simulated.
          </span>
        {/if}
      </p>
    {:else}
      <p class="hint">Choose a code family or <b>Freeform (draw)</b> to begin.</p>
    {/if}
  </div>

  <div class="grp">
    <div class="hd">Surface</div>
    {#if !hasContent}
      <div class="readout grid2 empty">
        <span>qubits</span><b>0</b>
        <span>data</span><b>0</b>
        <span>stabilizers</span><b>0</b>
        <span>detectors</span><b>0</b>
        <span>observables</span><b>0</b>
      </div>
      <p class="hint">empty — nothing to simulate yet.</p>
    {:else if compileError !== null}
      <div class="readout err">Compile failed: {compileError}</div>
    {:else if compileResult !== null && compileResult.ok}
      <div class="readout grid2">
        <span>qubits</span><b>{compileResult.num_qubits}</b>
        <span>data</span><b>{compileResult.num_data}</b>
        <span>stabilizers</span><b>{compileResult.num_stabilizers}</b>
        <span>detectors</span><b>{compileResult.num_detectors}</b>
        <span>observables</span><b>{compileResult.num_observables}</b>
      </div>
      {#if compileResult.warnings.length > 0}
        <ul class="warns">
          {#each compileResult.warnings as w}
            <li>{w}</li>
          {/each}
        </ul>
      {/if}
    {:else if compileResult !== null}
      <div class="readout warn">
        Not simulatable yet:
        <ul class="warns">
          {#each compileResult.warnings as w}
            <li>{w}</li>
          {/each}
        </ul>
      </div>
    {:else}
      <p class="hint">Computing…</p>
    {/if}
  </div>

  <div class="grp">
    <div class="hd">Noise</div>
    <label>
      Channel
      <select bind:value={channel}>
        <option value="" disabled selected>— select a channel —</option>
        {#each channels as c (c.name)}
          <option value={c.name}>{c.label}{c.is_pauli ? "" : " ◇"}</option>
        {/each}
      </select>
    </label>

    {#if channelInfo !== null}
      <p class="hint">{channelInfo.note}</p>

      {#if nonPauli}
        <div class="readout warn">
          Non-Pauli ({channelInfo.label}). Steered the decoder to
          <b>coherent</b>;
          {#if demOnNonPauli}
            <span class="warntext"
              >{decoderInfo?.label} is DEM-based and can't honestly decode
              non-Pauli noise.</span
            >
          {/if}
        </div>
      {/if}

      {#if channelInfo.arg === "theta"}
        <label>
          Angle θ (rad)
          <input type="number" step="0.01" bind:value={theta} />
        </label>
      {:else if channelInfo.arg === "vec3"}
        <div class="trio">
          <label>p<sub>x</sub><input type="number" step="0.0001" bind:value={vx} /></label>
          <label>p<sub>y</sub><input type="number" step="0.0001" bind:value={vy} /></label>
          <label>p<sub>z</sub><input type="number" step="0.0001" bind:value={vz} /></label>
        </div>
      {:else}
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
      {/if}
    {/if}
  </div>

  <div class="grp">
    <div class="hd">Run</div>
    <label>Rounds<input type="number" min="1" step="1" bind:value={rounds} /></label>
    <label>Shots<input type="number" min="1" step="1000" bind:value={shots} /></label>
    <label>
      Decoder
      <select
        bind:value={decoder}
        onchange={() => (decoderTouched = true)}
      >
        <option value="" disabled selected>— select a decoder —</option>
        {#each decoders as d (d.name)}
          <option value={d.name}>{d.label}{d.pauli_only ? "" : " ◇"}</option>
        {/each}
      </select>
    </label>
    {#if decoderInfo !== null}
      <p class="hint">{decoderInfo.note}</p>
    {/if}
  </div>

  <div class="grp">
    <div class="actions">
      {#if running}
        <button class="run stop" onclick={onstop}>Stop</button>
      {:else}
        <button class="run" onclick={fire} disabled={!canRun}>Run</button>
      {/if}
    </div>

    {#if !canRun && !running}
      <p class="hint">Pick a code, a noise channel, and a decoder to run.</p>
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
    border-color: color-mix(in srgb, var(--x) 55%, transparent);
    color: var(--muted);
  }

  .readout.err {
    border-color: var(--x);
    color: var(--x);
  }

  /* two-column label/value grid for the Surface stats */
  .readout.grid2 {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 2px 12px;
  }

  .readout.grid2 span {
    color: var(--muted);
  }

  .readout.grid2 b {
    color: var(--fg);
    text-align: right;
  }

  /* zeroed stats when nothing is chosen/drawn: read as inactive, never stale. */
  .readout.grid2.empty,
  .readout.grid2.empty b {
    color: var(--faint);
  }

  /* the ◇ marker on non-Pauli channels/decoders */
  sub {
    font-size: 0.7em;
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

  .hint b {
    color: var(--fg);
    font-variant-numeric: tabular-nums;
  }

  .warntext {
    display: block;
    margin-top: 4px;
    color: var(--x);
  }
</style>
