<script module lang="ts">
  // Single source for the phase-wheel hues (cyan / violet / magenta) shared by
  // the hex + triangular color codes and the square X/Z subset. `<input type=color>`
  // needs a concrete hex, so these stay literal -- the $shared `C` map only carries
  // `var(--..)` references (which a color input rejects) -- but they intentionally
  // mirror --accent-2 / --accent / --accent-3 from shared/qui/palette.css.
  export const PHASE_HUES = {
    A: "#4cc9f0",
    B: "#8b6cff",
    C: "#ff5d8f",
  } as const;
</script>

<script lang="ts">
  // Shared chrome for the three lattice diagrams (square / triangular / hex). Owns
  // the .diagram-layout + sidebar, the header, the four common view toggles, the
  // color fieldset wrapper, and the LatticeView. Each lattice supplies its own
  // number inputs / selects (`controls`), its color pickers (`colors`), any extra
  // toggle (`extraChecks`), and its SVG marks (`children`) -- the last receives two
  // reusable mark snippets so every lattice draws data qubits + polygon faces from
  // one definition (see the {#snippet}s below).
  import type { Snippet } from "svelte";
  import LatticeView from "./LatticeView.svelte";

  type Pt = { x: number; y: number };
  type Face = { pointsString: string; color: string };

  export type QubitsMark = Snippet<[pts: Pt[], r: number]>;
  export type FacesMark = Snippet<[list: Face[]]>;

  interface Props {
    title: string;
    subtitle: Snippet;
    colorLegend: string;
    viewBox: string;
    name: string; // download stem, passed through to LatticeView
    showFaces?: boolean;
    showVertices?: boolean;
    showEdges?: boolean;
    showLabels?: boolean;
    controls: Snippet; // number inputs + any diagram-specific selects
    colorPickers: Snippet; // the .color pickers inside the fieldset
    extraChecks?: Snippet; // optional extra toggle (kagome / rotated)
    children: Snippet<[qubits: QubitsMark, faces: FacesMark]>;
  }

  let {
    title,
    subtitle,
    colorLegend,
    viewBox,
    name,
    showFaces = $bindable(true),
    showVertices = $bindable(true),
    showEdges = $bindable(true),
    showLabels = $bindable(false),
    controls,
    colorPickers,
    extraChecks,
    children,
  }: Props = $props();
</script>

{#snippet qubits(pts: Pt[], r: number)}
  {#each pts as p, i (i)}
    <circle class="diagram-qubit" cx={p.x} cy={p.y} r={r} fill="var(--fg)" />
  {/each}
{/snippet}

{#snippet faces(list: Face[])}
  {#each list as f, i (i)}
    <polygon
      class="diagram-face"
      points={f.pointsString}
      fill={f.color}
      fill-opacity="0.28"
      stroke={f.color}
      stroke-width="1"
    />
  {/each}
{/snippet}

<div class="diagram-layout">
  <aside class="diagram-sidebar glass">
    <header class="head">
      <h3 class="gradient-text">{title}</h3>
      <p class="sub">{@render subtitle()}</p>
    </header>
    {@render controls()}
    <label class="chk"><input type="checkbox" bind:checked={showFaces} />Faces</label>
    <label class="chk"><input type="checkbox" bind:checked={showVertices} />Data qubits</label>
    <label class="chk"><input type="checkbox" bind:checked={showEdges} />Edges</label>
    <label class="chk"><input type="checkbox" bind:checked={showLabels} />Labels</label>
    {@render extraChecks?.()}
    <fieldset class="colors">
      <legend>{colorLegend}</legend>
      {@render colorPickers()}
    </fieldset>
  </aside>

  <LatticeView {viewBox} {name}>
    {@render children(qubits, faces)}
  </LatticeView>
</div>
