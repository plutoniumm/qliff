<script lang="ts">
  // A worked example: the cheapest way to explain anything. Plug concrete numbers
  // into the page's governing equation and walk the arithmetic step by step. It now
  // renders inside VitePress' NATIVE custom-block chrome (the same box as a
  // `::: info` container -- bg / border / radius / padding / title all come from
  // VP's custom-block.css), so only the numbered steps + result line are bespoke.
  //   <Worked title="Cost of pairing g1-g3 at p = 0.08">
  //     <ol><li>...</li></ol>
  //     {#snippet result()}cheapest matching costs <b>4.88</b>{/snippet}
  //   </Worked>
  import type { Snippet } from "svelte";

  let {
    title = "Worked example",
    children,
    result,
  }: {
    title?: string;
    children: Snippet;
    result?: Snippet;
  } = $props();
</script>

<div class="custom-block info worked">
  <p class="custom-block-title">
    <span class="tag mono">worked example</span>
    <span class="t">{title}</span>
  </p>
  <div class="body">
    {@render children()}
  </div>
  {#if result}
    <p class="result">{@render result()}</p>
  {/if}
</div>

<style>
  /* The box -- bg / border / radius / padding / title weight -- is VitePress'
     native .custom-block.info; only the worked-example specifics live here. */
  .worked {
    margin: 1.6em 0;
  }

  .custom-block-title {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .tag {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--accent-2);
    padding: 3px 8px;
    border-radius: 99px;
    border: 1px solid color-mix(in srgb, var(--accent-2) 45%, transparent);
    flex: none;
  }

  .t {
    font-size: 14.5px;
  }

  /* numbered steps -- each <li> is one line of the calculation */
  .body :global(ol) {
    margin: 0.6em 0;
    padding-left: 0;
    list-style: none;
    counter-reset: step;
  }

  .body :global(ol > li) {
    position: relative;
    counter-increment: step;
    margin: 0.55em 0;
    padding-left: 34px;
    min-height: 22px;
  }

  .body :global(ol > li)::before {
    content: counter(step);
    position: absolute;
    left: 0;
    top: 0;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--accent-2) 18%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-2) 45%, transparent);
    color: var(--accent-2);
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 700;
    display: grid;
    place-items: center;
  }

  .body :global(table) {
    width: auto;
    margin: 0.5em 0;
    font-size: 13.5px;
  }

  .result {
    margin: 10px 0 4px;
    padding: 9px 13px;
    border-radius: var(--r-sm);
    border-left: 3px solid var(--ok);
    background: color-mix(in srgb, var(--ok) 10%, transparent);
    font-size: 14.5px;
    color: var(--fg);
  }

  .result :global(b),
  .result :global(strong) {
    color: var(--ok);
  }
</style>
