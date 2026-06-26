<script lang="ts">
  // Aside box for a key idea, definition, or caution. Renders with VitePress' OWN
  // custom-block classes (.custom-block.info / .tip / .warning), so it is visually
  // identical to a native `::: tip` container in the prose docs and follows the
  // light/dark toggle for free -- the default theme's custom-block.css does all
  // the styling, this component adds (almost) none.
  //   <Callout kind="key" title="Why log-odds?">...</Callout>
  import type { Snippet } from "svelte";

  let {
    kind = "note",
    title = "",
    children,
  }: {
    kind?: "note" | "key" | "warn";
    title?: string;
    children: Snippet;
  } = $props();

  // map our semantic kinds onto VitePress' custom-block variants
  const vp = {
    note: "info",
    key: "tip",
    warn: "warning",
  } as const;
</script>

<div class="custom-block {vp[kind]}">
  {#if title}<p class="custom-block-title">{title}</p>{/if}
  {@render children()}
</div>

<style>
  /* The look comes entirely from VitePress' global custom-block.css; we only set
     the vertical rhythm and drop the trailing margin so the box stays tight. */
  .custom-block {
    margin: 1.4em 0;
  }

  .custom-block :global(p:last-child) {
    margin-bottom: 0;
  }
</style>
