<script lang="ts">
  // KaTeX wrapper. Inline by default; add `display` for a centered block.
  // IMPORTANT: pass the TeX via a raw string so backslashes survive ->
  //   <Math expr={String.raw`\sqrt{1-p}`} />        (correct)
  // A plain quoted attribute with a DOUBLED backslash, expr="\\sqrt{1-p}", reaches
  // KaTeX as `\\sqrt`, where the `\\` is KaTeX's line break, so the command name is
  // eaten and renders as the bare letters "sqrt". Single-backslash quoted
  // (expr="\sqrt{...}") works too, but braces still need String.raw, so just always
  // use String.raw. Errors render in red rather than throwing so a typo never
  // white-screens a page.
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
