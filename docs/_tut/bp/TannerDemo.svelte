<script lang="ts">
  // Section 2 island: the interactive Tanner graph. Toggle chips light detectors
  // (that is the syndrome) and hovering a node highlights its edges. Wraps the
  // kept TannerGraph so the toggle state can live next to it in one self-contained
  // island (markdown cannot hold Svelte state).
  import TannerGraph from "./TannerGraph.svelte";
  import { makeCode, type Code } from "./bp";

  const tannerCode: Code = makeCode(
    [
      [1, 1, 0, 0, 0],
      [0, 1, 1, 1, 0],
      [0, 0, 0, 1, 1],
    ],
    [0.06, 0.06, 0.06, 0.06, 0.06],
  );

  let litChecks = $state<boolean[]>([false, true, false]);
  const tannerSyndrome = $derived(litChecks.map((b) => (b ? 1 : 0)));
  let tannerHover = $state<{ kind: "var" | "check"; idx: number } | null>(null);

  function toggleCheck(c: number): void {
    litChecks = litChecks.map((b, i) => (i === c ? !b : b));
  }
</script>

<TannerGraph
  code={tannerCode}
  syndrome={tannerSyndrome}
  bind:hover={tannerHover}
  height={250}
/>
<div class="check-toggles">
  {#each litChecks as lit, c (c)}
    <button class="chip" class:on={lit} onclick={() => toggleCheck(c)}>
      detector d{c}: {lit ? "lit" : "quiet"}
    </button>
  {/each}
</div>

<style>
  .check-toggles {
    margin-top: 14px;
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
  }

  .chip {
    font-size: 12.5px;
    padding: 6px 12px;
    border-radius: 99px;
    border: 1px solid var(--line);
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
    color: var(--muted);
  }

  .chip.on {
    border-color: color-mix(in srgb, var(--accent-3) 55%, transparent);
    background: color-mix(in srgb, #ffd166 16%, transparent);
    color: var(--fg);
  }
</style>
