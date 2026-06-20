<script lang="ts">
  // Shared chrome for a diagram: holds the <svg> ref, fits it to the supplied
  // viewBox, and wires SVG / PNG export. The actual lattice marks are passed in
  // as a snippet so each lattice owns its own rendering.
  import type { Snippet } from "svelte";
  import { downloadSVG, downloadPNG } from "$lib/download";

  interface Props {
    viewBox: string;
    name: string; // download stem, e.g. "surface_code_5x5"
    children: Snippet;
  }

  let { viewBox, name, children }: Props = $props();

  let svgEl = $state<SVGSVGElement | null>(null);

  function saveSVG() {
    if (svgEl) downloadSVG(svgEl, `${name}.svg`);
  }

  function savePNG() {
    if (svgEl) downloadPNG(svgEl, `${name}.png`);
  }
</script>

<div class="view">
  <div class="canvas glass">
    <svg
      bind:this={svgEl}
      {viewBox}
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
    >
      {@render children()}
    </svg>
  </div>
  <div class="exports">
    <span class="hint mono">{name}</span>
    <button class="export" onclick={saveSVG}>Download SVG</button>
    <button class="export" onclick={savePNG}>Download PNG</button>
  </div>
</div>

<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .canvas {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 22px;
    min-height: 0;
  }

  svg {
    width: 100%;
    height: 100%;
    max-height: 70vh;
    display: block;
  }

  .exports {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .hint {
    margin-right: auto;
    font-size: 12px;
    color: var(--faint);
    letter-spacing: 0.02em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .export {
    font-size: 13px;
    color: var(--muted);
  }

  .export:hover {
    color: var(--fg);
  }
</style>
