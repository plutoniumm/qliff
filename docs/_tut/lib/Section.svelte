<script lang="ts">
  // One numbered step of an explainer. Provides the consistent heading + prose
  // column. Wrap each stage of your top-to-bottom narrative in a <Section>:
  //   <Section id="matching-graph" step="02" title="The matching graph">...</Section>
  // Add `wide` for a full-bleed interactive panel that should escape the prose
  // measure. The `id` lands on the <h2> itself so VitePress' "on this page"
  // outline (which scans .VPDoc headings with an id) picks the section up.
  import { type Snippet } from "svelte";

  let {
    id,
    title,
    step = "",
    wide = false,
    children,
  }: {
    id: string;
    title: string;
    step?: string | number;
    wide?: boolean;
    children: Snippet;
  } = $props();
</script>

<section class="section" class:wide>
  <header class="head">
    {#if step !== ""}<span class="step mono">{step}</span>{/if}
    <h2 {id}>{title}</h2>
  </header>
  <div class="body" class:prose={!wide}>
    {@render children()}
  </div>
</section>

<style>
  .section {
    scroll-margin-top: 24px;
    margin: 0 auto;
    padding: 38px 0 10px;
  }

  .section.wide {
    max-width: min(1180px, 100%);
  }

  .head {
    max-width: var(--col);
    margin: 0 auto 18px;
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .section.wide .head {
    max-width: 1180px;
  }

  .step {
    font-size: 13px;
    font-weight: 700;
    color: var(--accent);
    padding: 4px 9px;
    border-radius: 99px;
    border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
    background: var(--grad-soft);
    flex: none;
  }

  .head :global(h2) {
    font-size: 26px;
    line-height: 1.2;
    margin: 0;
    letter-spacing: -0.01em;
    scroll-margin-top: 90px;
  }
</style>
