<script lang="ts">
  // Local KaTeX wrapper for the tn interactives -- an in-tree copy of the shared
  // Math wrapper, so the islands keep rendering their live math after the shared
  // lib wrappers are removed. Inline by default; add `display` for a centered
  // block. Pass TeX via a raw string so backslashes survive. Errors render red
  // rather than throwing, so a typo never white-screens the page.
  import katex from "katex";

  let { expr, display = false }: { expr: string; display?: boolean } = $props();

  const html = $derived(
    katex.renderToString(expr, {
      displayMode: display,
      throwOnError: false,
      errorColor: "#ff6b6b",
      output: "html",
    }),
  );
</script>

{#if display}
  <div class="math-block">{@html html}</div>
{:else}<span class="math-inline">{@html html}</span>{/if}

<style>
  .math-block {
    margin: 1.2em 0;
    overflow-x: auto;
    overflow-y: hidden;
  }
</style>
