<script lang="ts">
  // SVG editing surface. Renders placed tiles + the edge-adjacency links between
  // them, draws the selection highlight, supports Finder-style marquee
  // multi-select on empty space (live), drag-to-move of the selection (grid
  // snapped), palette drag/drop and click-to-place, and the full keyboard set
  // (delete / copy / paste / undo / redo / rotate). A HUD shows live tile/group
  // counts and the current selection so the lattice is never a black box.
  //
  // The CanvasModel holds all state; we bump a `tick` counter after every
  // mutation to force Svelte to re-read it (the model mutates in place).
  import type { TileKind } from "$lib/schema";
  import {
    CanvasModel,
    tilePolygon,
    pixelToGridFor,
    gridToPixel,
    normalizeRect,
    CELL,
    type Point,
    type Rect,
  } from "$lib/canvas";

  interface Props {
    model: CanvasModel;
    armed: TileKind | null;
    rev: number; // external model-version from the parent (e.g. template loads)
    onarm: (kind: TileKind | null) => void;
    onchange: () => void;
  }

  let { model, armed, rev, onarm, onchange }: Props = $props();

  // Re-render trigger. Internal edits bump `tick`; external model mutations (a
  // template construction in the parent) arrive as a changed `rev`. Both must
  // force a re-read of the in-place model, so everything keys on their sum.
  let tick = $state(0);
  let version = $derived(tick + rev);

  function touch(): void {
    tick += 1;
    onchange();
  }

  // Live, derived views of the (non-reactive) model, recomputed on every change.
  let stats = $derived.by(() => {
    void version;

    return model.stats();
  });
  let selectedCount = $derived.by(() => {
    void version;

    return model.selected.size;
  });
  let links = $derived.by(() => {
    void version;

    return model.links();
  });

  const W = 760;
  const H = 560;

  let svgEl: SVGSVGElement | null = $state(null);

  // Interaction state.
  type Drag =
    | { kind: "none" }
    | { kind: "marquee"; start: Point; cur: Point; additive: boolean; base: Set<string> }
    | { kind: "move"; last: Point; moved: boolean };
  let drag: Drag = $state({ kind: "none" });

  // Map screen coords -> SVG user space via the CTM, so hit-testing and tile
  // placement stay correct even when the SVG is scaled to fit (rendered size !=
  // viewBox). A plain clientX-rect.left is only right at 1:1 scale, which broke
  // single-click selection when the canvas was squished to fit its panel.
  function localPoint(ev: PointerEvent): Point {
    const ctm = svgEl?.getScreenCTM();

    if (
      svgEl === null ||
      ctm === null ||
      ctm === undefined
    ) {
      return { x: 0, y: 0 };
    }

    const sp = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(ctm.inverse());

    return { x: sp.x, y: sp.y };
  }

  function polyPoints(points: Point[]): string {
    return points.map((p) => `${p.x},${p.y}`).join(" ");
  }

  // Fill colour: alternate X/Z tint by grid parity so the lattice reads as a
  // checkerboard of stabiliser types.
  function fill(row: number, col: number): string {
    return (row + col) % 2 === 0 ? "var(--z)" : "var(--x)";
  }

  // -- pointer interaction --------------------------------------------------

  function onPointerDown(ev: PointerEvent): void {
    const p = localPoint(ev);
    svgEl?.setPointerCapture(ev.pointerId);
    const hit = model.hitTest(p);
    const additive =
      ev.shiftKey ||
      ev.metaKey ||
      ev.ctrlKey;

    if (hit === null) {
      // Empty space: either drop an armed tile, or begin a marquee.
      if (armed !== null) {
        const g = pixelToGridFor(armed, p);
        model.addTile(armed, g.row, g.col);
        model.select(model.tiles[model.tiles.length - 1].id);
        touch();

        return;
      }

      drag = {
        kind: "marquee",
        start: p,
        cur: p,
        additive,
        base: new Set(model.selected),
      };

      if (!additive) {
        model.clearSelection();
        touch();
      }

      return;
    }

    // Hit a tile. If unselected, select it (replace unless additive). Then begin
    // a move drag carrying the whole selection.
    if (additive) {
      model.toggle(hit);
    } else if (!model.selected.has(hit)) {
      model.select(hit);
    }

    drag = {
      kind: "move",
      last: p,
      moved: false,
    };
    touch();
  }

  function onPointerMove(ev: PointerEvent): void {
    if (drag.kind === "none") {
      return;
    }

    const p = localPoint(ev);

    if (drag.kind === "marquee") {
      drag = { ...drag, cur: p };
      const r = normalizeRect(drag.start, p);

      // live selection feedback: re-evaluate every move from the captured base.
      if (r.w > 3 || r.h > 3) {
        model.selectInRect(r, true, drag.base);
        touch();
      }

      return;
    }

    // move: translate selection by whole grid cells once the pointer crosses a
    // cell boundary, keeping everything snapped.
    const dcol = Math.round((p.x - drag.last.x) / CELL);
    const drow = Math.round((p.y - drag.last.y) / CELL);

    if (dcol !== 0 || drow !== 0) {
      model.move(drow, dcol);
      drag = {
        kind: "move",
        last: { x: drag.last.x + dcol * CELL, y: drag.last.y + drow * CELL },
        moved: true,
      };
      touch();
    }
  }

  function onPointerUp(ev: PointerEvent): void {
    svgEl?.releasePointerCapture(ev.pointerId);
    drag = { kind: "none" };
  }

  function marqueeRect(): Rect {
    if (drag.kind !== "marquee") {
      return {
        x: 0,
        y: 0,
        w: 0,
        h: 0,
      };
    }

    return normalizeRect(drag.start, drag.cur);
  }

  // -- palette drop ---------------------------------------------------------

  function onDrop(ev: DragEvent): void {
    ev.preventDefault();
    const kind = ev.dataTransfer?.getData("application/x-tile-kind") as
      | TileKind
      | "";

    if (kind === "" || kind === undefined) {
      return;
    }

    const rect = svgEl?.getBoundingClientRect();

    if (rect === undefined) {
      return;
    }

    const g = pixelToGridFor(kind, { x: ev.clientX - rect.left, y: ev.clientY - rect.top });
    model.addTile(kind, g.row, g.col);
    model.select(model.tiles[model.tiles.length - 1].id);
    touch();
  }

  function onDragOver(ev: DragEvent): void {
    ev.preventDefault();

    if (ev.dataTransfer) {
      ev.dataTransfer.dropEffect = "copy";
    }
  }

  // Right-click anywhere disarms the palette (so you can switch to selecting).
  function onContextMenu(ev: MouseEvent): void {
    if (armed !== null) {
      ev.preventDefault();
      onarm(null);
    }
  }

  // -- keyboard -------------------------------------------------------------

  function onKeyDown(ev: KeyboardEvent): void {
    const meta = ev.metaKey || ev.ctrlKey;

    if (ev.key === "Delete" || ev.key === "Backspace") {
      model.delete();
      touch();
      ev.preventDefault();
    } else if (ev.key === "Escape") {
      onarm(null);
      model.clearSelection();
      touch();
    } else if (ev.key === "r" || ev.key === "R") {
      model.rotate();
      touch();
    } else if (meta && (ev.key === "a" || ev.key === "A")) {
      model.selectAll();
      touch();
      ev.preventDefault();
    } else if (meta && (ev.key === "c" || ev.key === "C")) {
      model.copy();
    } else if (meta && (ev.key === "v" || ev.key === "V")) {
      model.paste();
      touch();
    } else if (
      meta &&
      ev.shiftKey &&
      (ev.key === "z" || ev.key === "Z")
    ) {
      model.redo();
      touch();
      ev.preventDefault();
    } else if (meta && (ev.key === "z" || ev.key === "Z")) {
      model.undo();
      touch();
      ev.preventDefault();
    }
  }

  // Grid backdrop lines.
  function gridLines(): { x1: number; y1: number; x2: number; y2: number }[] {
    const out: { x1: number; y1: number; x2: number; y2: number }[] = [];

    for (let x = gridToPixel(0, 0).x; x < W; x += CELL) {
      out.push({
        x1: x,
        y1: 0,
        x2: x,
        y2: H,
      });
    }

    for (let y = gridToPixel(0, 0).y; y < H; y += CELL) {
      out.push({
        x1: 0,
        y1: y,
        x2: W,
        y2: y,
      });
    }

    return out;
  }
</script>

<div class="canvas-wrap">
  <div class="hud">
    <span class="stat">tiles <b>{stats.count}</b></span>
    <span class="stat" class:warn={stats.groups > 1}>
      groups <b>{stats.groups}</b>
    </span>
    {#if stats.count > 0}
      <span class="stat">bbox <b>{stats.rows}×{stats.cols}</b></span>
    {/if}
    <span class="stat sel" class:on={selectedCount > 0}>
      selected <b>{selectedCount}</b>
    </span>
  </div>

  {#if armed !== null}
    <div class="armband">
      Placing <b>{armed}</b> — click empty grid to drop · <kbd>Esc</kbd> or
      right-click to stop
    </div>
  {/if}

  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <svg
    bind:this={svgEl}
    class="canvas"
    class:placing={armed !== null}
    width={W}
    height={H}
    viewBox={`0 0 ${W} ${H}`}
    tabindex="0"
    role="application"
    aria-label="Lattice editing canvas"
    onpointerdown={onPointerDown}
    onpointermove={onPointerMove}
    onpointerup={onPointerUp}
    onkeydown={onKeyDown}
    ondrop={onDrop}
    ondragover={onDragOver}
    oncontextmenu={onContextMenu}
  >
    <!-- track version so the model's in-place mutations re-render -->
    {#key version}
      <g class="grid">
        {#each gridLines() as l}
          <line x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} />
        {/each}
      </g>

      <!-- adjacency links: shows which tiles actually touch (share an edge) -->
      <g class="links">
        {#each links as ln, i (i)}
          <line x1={ln.a.x} y1={ln.a.y} x2={ln.b.x} y2={ln.b.y} />
        {/each}
      </g>

      {#each model.tiles as t (t.id)}
        <polygon
          points={polyPoints(tilePolygon(t))}
          fill={fill(t.row, t.col)}
          class="tile"
          class:selected={model.selected.has(t.id)}
        />
      {/each}

      {#if drag.kind === "marquee"}
        {@const r = marqueeRect()}
        <rect
          class="marquee"
          x={r.x}
          y={r.y}
          width={r.w}
          height={r.h}
        />
      {/if}
    {/key}
  </svg>

  <div class="hint">
    <span>drag empty space → <b>select</b></span>
    <span>drag a tile → <b>move</b></span>
    <span><kbd>R</kbd> rotate</span>
    <span><kbd>⌘A</kbd> all</span>
    <span><kbd>⌘C</kbd>/<kbd>⌘V</kbd> copy</span>
    <span><kbd>Del</kbd> delete</span>
    <span><kbd>⌘Z</kbd> undo</span>
  </div>
</div>

<style>
  .canvas-wrap {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 10px;
    width: 100%;
  }

  .hud {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    font-size: 11.5px;
  }

  .stat {
    padding: 3px 9px;
    border-radius: 99px;
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
    border: 1px solid var(--line);
    color: var(--muted);
    letter-spacing: 0.02em;
  }

  .stat b {
    color: var(--fg);
    font-variant-numeric: tabular-nums;
  }

  .stat.warn {
    border-color: color-mix(in srgb, var(--x) 55%, transparent);
    color: var(--x);
  }

  .stat.warn b {
    color: var(--x);
  }

  .stat.sel.on {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    color: var(--fg);
    box-shadow: var(--glow-accent);
  }

  .armband {
    position: absolute;
    top: 38px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 2;
    padding: 6px 14px;
    border-radius: 99px;
    font-size: 12px;
    color: var(--fg);
    background: var(--grad-phase-soft);
    border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
    box-shadow: var(--glow-accent);
    pointer-events: none;
    white-space: nowrap;
  }

  .armband b {
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .canvas {
    width: 100%;
    height: auto;
    background:
      radial-gradient(120% 90% at 50% 0%, color-mix(in srgb, var(--accent) 7%, transparent), transparent 60%),
      color-mix(in srgb, var(--bg) 75%, transparent);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    display: block;
    outline: none;
    touch-action: none;
  }

  .canvas.placing {
    cursor: crosshair;
    border-color: color-mix(in srgb, var(--accent) 50%, transparent);
  }

  .grid line {
    stroke: var(--line);
    stroke-width: 1;
  }

  .links line {
    stroke: color-mix(in srgb, var(--accent) 55%, transparent);
    stroke-width: 2;
    stroke-linecap: round;
  }

  .tile {
    stroke: var(--fg);
    stroke-width: 1.5;
    fill-opacity: 0.5;
    cursor: pointer;
    transition:
      fill-opacity var(--dur-fast) var(--ease-out),
      stroke var(--dur-fast) var(--ease-out),
      filter var(--dur-fast) var(--ease-out);
  }

  .tile:hover {
    fill-opacity: 0.72;
  }

  .tile.selected {
    stroke: var(--accent);
    stroke-width: 3;
    fill-opacity: 0.9;
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--accent) 70%, transparent));
  }

  .marquee {
    fill: color-mix(in srgb, var(--accent) 14%, transparent);
    stroke: var(--accent);
    stroke-width: 1;
    stroke-dasharray: 4 3;
  }

  .hint {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    font-size: 11px;
    color: var(--faint);
  }

  .hint b {
    color: var(--muted);
    font-weight: 600;
  }

  kbd {
    font-family: var(--font-mono);
    font-size: 10.5px;
    padding: 1px 5px;
    border-radius: 5px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    color: var(--muted);
  }
</style>
