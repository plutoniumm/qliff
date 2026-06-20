<script lang="ts">
  // SVG editing surface. Renders placed tiles, draws the selection highlight,
  // supports Finder-style marquee multi-select on empty space, drag-to-move of
  // the selection (snapped to the grid), palette drag/drop and click-to-place,
  // and the full keyboard set (delete / copy / paste / undo / redo / rotate).
  //
  // The CanvasModel holds all state; we bump a `tick` counter after every
  // mutation to force Svelte to re-read it (the model mutates in place).
  import type { TileKind } from "$lib/schema";
  import {
    CanvasModel,
    tilePolygon,
    pixelToGrid,
    gridToPixel,
    normalizeRect,
    CELL,
    type Point,
    type Rect,
  } from "$lib/canvas";

  interface Props {
    model: CanvasModel;
    armed: TileKind | null;
    onarm: (kind: TileKind | null) => void;
    onchange: () => void;
  }

  let { model, armed, onarm, onchange }: Props = $props();

  // Re-render trigger; mutating methods bump this via touch().
  let tick = $state(0);

  function touch(): void {
    tick += 1;
    onchange();
  }

  const W = 760;
  const H = 560;

  let svgEl: SVGSVGElement | null = $state(null);

  // Interaction state.
  type Drag =
    | { kind: "none" }
    | { kind: "marquee"; start: Point; cur: Point; additive: boolean }
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
        const g = pixelToGrid(p);
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
    if (drag.kind === "marquee") {
      const r = marqueeRect();

      if (r.w > 3 || r.h > 3) {
        model.selectInRect(r, drag.additive);
        touch();
      }
    }

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

    const g = pixelToGrid({ x: ev.clientX - rect.left, y: ev.clientY - rect.top });
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
  function gridLines(): { major: boolean; x1: number; y1: number; x2: number; y2: number }[] {
    const out: { major: boolean; x1: number; y1: number; x2: number; y2: number }[] = [];

    for (let x = gridToPixel(0, 0).x; x < W; x += CELL) {
      out.push({
        major: false,
        x1: x,
        y1: 0,
        x2: x,
        y2: H,
      });
    }

    for (let y = gridToPixel(0, 0).y; y < H; y += CELL) {
      out.push({
        major: false,
        x1: 0,
        y1: y,
        x2: W,
        y2: y,
      });
    }

    return out;
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<svg
  bind:this={svgEl}
  class="canvas"
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
>
  <!-- track tick so the model's in-place mutations re-render -->
  {#key tick}
    <g class="grid">
      {#each gridLines() as l}
        <line x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} />
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

<style>
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

  .grid line {
    stroke: var(--line);
    stroke-width: 1;
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
</style>
