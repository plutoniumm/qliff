<script lang="ts">
  // Part A entry: passive lattice diagram generators. Sub-tab switcher between
  // the square (surface code), triangular (+ Kagome), and hexagonal (color code)
  // lattices. Each tab owns its own controls + SVG view and SVG/PNG export.
  import RectDiagram from "./RectDiagram.svelte";
  import TriDiagram from "./TriDiagram.svelte";
  import HexDiagram from "./HexDiagram.svelte";
  import { viewTransition } from "$lib/transition";

  type Tab = "square" | "tri" | "hex";

  let tab = $state<Tab>("square");

  function show(next: Tab): void {
    if (next === tab) {
      return;
    }

    viewTransition(() => {
      tab = next;
    });
  }
</script>

<section class="diagrams">
  <div class="tabs subtabs">
    <button class="tab" class:active={tab === "square"} onclick={() => show("square")}>Square</button>
    <button class="tab" class:active={tab === "tri"} onclick={() => show("tri")}>Triangular</button>
    <button class="tab" class:active={tab === "hex"} onclick={() => show("hex")}>Hexagonal</button>
  </div>

  <div class="body">
    {#if tab === "square"}
      <RectDiagram />
    {:else if tab === "tri"}
      <TriDiagram />
    {:else}
      <HexDiagram />
    {/if}
  </div>
</section>

<style>
  .diagrams {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 18px;
    height: calc(100vh - 56px);
  }

  .subtabs {
    flex: none;
  }

  .body {
    flex: 1;
    min-height: 0;
  }
</style>
