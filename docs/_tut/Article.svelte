<script lang="ts">
  // The body of one explainer route. The page's title, step Badge and lead tagline
  // are now real markdown in tutorials/<id>.md (so VitePress server-renders them --
  // they land in the static HTML, the local search index and the document title),
  // and VitePress provides the chrome (top nav, sidebar, "on this page" outline,
  // prev/next pager). So this only wraps the explainer itself, which is mounted as
  // a Svelte island by ../.vitepress/theme/SvelteIsland.vue.
  import type { Component } from "svelte";

  let { page: Page }: { page: Component } = $props();
</script>

<article class="article">
  <Page />
</article>

<style>
  .article {
    padding-top: 4px;
  }
</style>
