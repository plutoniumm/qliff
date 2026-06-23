<script lang="ts">
  // App shell: switches between Part A (Diagrams) and Part B (Builder). These two
  // entry components are owned by separate agents; keep their paths stable. The
  // tab swap goes through the View Transitions API so the content cross-fades.
  import Diagrams from "./routes/diagrams/Diagrams.svelte";
  import Builder from "./routes/builder/Builder.svelte";
  import { viewTransition } from "$lib/transition";

  let view = $state<"diagrams" | "builder">("diagrams");

  function show(next: "diagrams" | "builder"): void {
    if (next === view) {
      return;
    }

    viewTransition(() => {
      view = next;
    });
  }
</script>

<nav class="topnav">
  <span class="brand gradient-text">qliff studio</span>
  <div class="tabs">
    <button
      class="tab"
      class:active={view === "diagrams"}
      onclick={() => show("diagrams")}
    >
      Diagrams
    </button>
    <button
      class="tab"
      class:active={view === "builder"}
      onclick={() => show("builder")}
    >
      Builder
    </button>
  </div>
  <span class="tagline">scalable stabilizer QEC studio</span>
</nav>

{#if view === "diagrams"}
  <Diagrams />
{:else}
  <Builder />
{/if}

<style>
  .tagline {
    margin-left: auto;
    color: var(--faint);
    font-size: 12px;
    letter-spacing: 0.03em;
  }
  @media (max-width: 640px) {
    .tagline {
      display: none;
    }
  }
</style>
