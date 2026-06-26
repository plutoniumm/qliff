<script lang="ts">
  // A framed interactive panel: optional in-frame title + legend (so the reader
  // always knows WHAT they're looking at and what each colour means), the vis
  // itself, then a caption below. `wide` lets it span past the prose column.
  //   <Figure title="Matching graph" legend={[{color: C.x, label: "X error"}]}
  //           caption="Hover an edge to read its chain.">...</Figure>
  import type { Snippet } from "svelte";
  import Legend, { type LegendItem } from "./Legend.svelte";

  let {
    title = "",
    caption = "",
    legend = [],
    wide = false,
    pad = true,
    children,
  }: {
    title?: string;
    caption?: string;
    legend?: LegendItem[];
    wide?: boolean;
    pad?: boolean;
    children: Snippet;
  } = $props();
</script>

<figure class="figure" class:wide>
  <div class="frame glass" class:pad>
    {#if title || legend.length}
      <div class="cap-head">
        {#if title}<span class="cap-title">{title}</span>{/if}
        {#if legend.length}<Legend items={legend} />{/if}
      </div>
    {/if}
    {@render children()}
  </div>
  {#if caption}<figcaption>{caption}</figcaption>{/if}
</figure>

<style>
  .figure {
    margin: 1.6em 0;
  }

  .figure.wide {
    margin-inline: auto;
  }

  .frame {
    overflow: hidden;
  }

  .frame.pad {
    padding: 16px;
  }

  .cap-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px 16px;
    margin: -2px 0 14px;
    padding-bottom: 11px;
    border-bottom: 1px solid var(--line);
  }

  .cap-title {
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }

  figcaption {
    margin-top: 0.7em;
    font-size: 13px;
    color: var(--faint);
    text-align: center;
    line-height: 1.5;
  }
</style>
