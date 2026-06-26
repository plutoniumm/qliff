<script lang="ts">
  // A tiny inline legend: name every colour / mark a visualization uses, so the
  // reader never has to guess what they're looking at. Use it standalone inside a
  // `wide` custom layout, or let <Figure legend={...}> render one for you.
  //   <Legend items={[{ color: C.x, label: "X error" }, { mark: "dash", label: "candidate edge" }]} />
  export interface LegendItem {
    /** swatch colour (hex or CSS var). Defaults to a muted line colour. */
    color?: string;
    /** swatch shape. box = filled square, line/dash = stroke, dot = filled disc, ring = outline. */
    mark?: "box" | "line" | "dash" | "dot" | "ring";
    label: string;
  }

  let { items = [] }: { items?: LegendItem[] } = $props();
</script>

<div class="legend">
  {#each items as it, i (i)}
    <span class="item">
      <span class="sw {it.mark ?? 'box'}" style="--c:{it.color ?? 'var(--faint)'}"></span>
      <span class="lbl">{it.label}</span>
    </span>
  {/each}
</div>

<style>
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    align-items: center;
  }

  .item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
    line-height: 1.3;
  }

  .sw {
    flex: none;
    display: inline-block;
  }

  .sw.box {
    width: 11px;
    height: 11px;
    border-radius: 3px;
    background: var(--c);
  }

  .sw.dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--c);
  }

  .sw.ring {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 2px solid var(--c);
  }

  .sw.line,
  .sw.dash {
    width: 16px;
    height: 0;
    border-top: 2px solid var(--c);
  }

  .sw.dash {
    border-top-style: dashed;
  }
</style>
