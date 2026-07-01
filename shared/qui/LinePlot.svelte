<script lang="ts" module>
  // One reusable uPlot (canvas) line chart shared by the docs explainers and the
  // studio SPA. It replaces four hand-rolled SVG plots: hand it series in DATA
  // coordinates, a per-axis scale (lin/log), explicit ranges + labels, and an
  // optional draw-hook callback for custom overlays (threshold lines, error bars,
  // markers, ...). It sizes itself to its container, resolves CSS color tokens to
  // concrete colors so canvas can use them, and re-resolves on the VitePress
  // light/dark toggle. Import via `$shared/LinePlot.svelte`.

  // One plotted line. `pts` are [x, y] pairs in data coordinates. An optional
  // `band` (per-point lo/hi, index-aligned to pts) draws a filled +/- region.
  export interface PlotSeries {
    pts: [number, number][];
    color: string; // CSS expr (var(--x), color-mix(...)) OR a concrete color
    label?: string;
    width?: number; // line width in px (default 2)
    dash?: boolean; // dashed line
    showPoints?: boolean; // draw a marker dot at each point
    band?: { lo: number[]; hi: number[] }; // filled band around the line
    bandColor?: string; // band fill (default: 16% alpha of `color`)
  }

  // Everything a draw-hook needs to paint overlays on the canvas, in canvas
  // pixels. `x`/`y` map data coordinates to canvas pixels; `color` resolves a CSS
  // token; `pxr` is the device pixel ratio (multiply line widths by it).
  export interface DrawKit {
    ctx: CanvasRenderingContext2D;
    x: (v: number) => number;
    y: (v: number) => number;
    bbox: { left: number; top: number; width: number; height: number };
    color: (css: string) => string;
    pxr: number;
  }
</script>

<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import type uPlotType from "uplot";
  import "uplot/dist/uPlot.min.css";
  import { C, withAlpha } from "./colors";

  type Scale = "lin" | "log";

  interface Props {
    series: PlotSeries[];
    xScale?: Scale;
    yScale?: Scale;
    xRange?: [number, number];
    yRange?: [number, number];
    xLabel?: string;
    yLabel?: string;
    xFmt?: (v: number) => string;
    yFmt?: (v: number) => string;
    height?: number;
    legend?: boolean;
    annotate?: (k: DrawKit) => void;
  }

  let {
    series,
    xScale = "lin",
    yScale = "lin",
    xRange,
    yRange,
    xLabel = "",
    yLabel = "",
    xFmt,
    yFmt,
    height = 320,
    legend = false,
    annotate,
  }: Props = $props();

  let host: HTMLDivElement | null = $state(null);
  let uplib: typeof uPlotType | null = null;
  let plot: uPlotType | null = null;
  let ro: ResizeObserver | undefined;
  let themeObs: MutationObserver | undefined;
  let probe: HTMLSpanElement | undefined;
  let destroyed = false;

  // Non-reactive mirrors of the reactive props, read by uPlot's range fns and the
  // draw hook. onMount seeds them and the $effect below refreshes them BEFORE
  // calling setData/redraw, so we never write $state that the effect also reads
  // (the effect_update_depth trap). Seeded to benign defaults here so the reactive
  // props are only ever read inside onMount/effect, not captured at init.
  let curW = 600;
  let curH = 320;
  let curX: [number, number] | undefined = undefined;
  let curY: [number, number] | undefined = undefined;
  let curSeries: PlotSeries[] = [];
  let curAnnotate: ((k: DrawKit) => void) | undefined = undefined;
  let lastSig = "";

  // Resolve a CSS color expression to a concrete rgb(a) string via a hidden probe
  // under host (which inherits the theme tokens), the trick Bloch.svelte uses.
  // Cached; the cache is cleared on theme toggle so colors re-resolve.
  const cache = new Map<string, string>();
  function resolve(expr: string): string {
    if (!expr || !host) {
      return expr;
    }
    const hit = cache.get(expr);
    if (hit !== undefined) {
      return hit;
    }
    if (!probe) {
      probe = document.createElement("span");
      probe.style.display = "none";
    }
    probe.style.color = "";
    probe.style.color = expr;
    host.appendChild(probe);
    const rgb = getComputedStyle(probe).color || expr;
    host.removeChild(probe);
    cache.set(expr, rgb);

    return rgb;
  }

  // Unicode-superscript exponent, for "10^n" log-axis tick labels.
  function sup(e: number): string {
    const map: Record<string, string> = {
      "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³",
      "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    };

    return String(e).split("").map((ch) => map[ch] ?? ch).join("");
  }
  function pow10(v: number): string {
    return `10${sup(Math.round(Math.log10(v)))}`;
  }
  function isDecade(v: number): boolean {
    const l = Math.log10(v);

    return v > 0 && Math.abs(l - Math.round(l)) < 1e-6;
  }

  // Union of all series x-values, ascending (uPlot needs one shared, sorted x).
  function unionXs(list: PlotSeries[]): number[] {
    const set = new Set<number>();
    for (const s of list) {
      for (const p of s.pts) {
        set.add(p[0]);
      }
    }

    return [...set].sort((a, b) => a - b);
  }

  // A column aligned to `xs`: value at each x, or null (gap) where the series has
  // no point. `pts` supplies the x keys; `vals` the values to place (index-aligned
  // to pts, so a band lo/hi can reuse its series' x keys).
  function column(xs: number[], pts: [number, number][], vals: number[]): (number | null)[] {
    const m = new Map<number, number>();
    pts.forEach((p, i) => m.set(p[0], vals[i]));

    return xs.map((x) => (m.has(x) ? (m.get(x) as number) : null));
  }

  function buildData(): uPlotType.AlignedData {
    const xs = unionXs(curSeries);
    const cols: (number | null)[][] = [xs];
    for (const s of curSeries) {
      if (s.band) {
        cols.push(column(xs, s.pts, s.band.lo));
        cols.push(column(xs, s.pts, s.band.hi));
      }
      cols.push(column(xs, s.pts, s.pts.map((p) => p[1])));
    }

    return cols as uPlotType.AlignedData;
  }

  // Structure signature: a rebuild (vs a cheap setData) is needed when the series
  // count, colors, or line styling change -- these are baked into the uPlot opts.
  function sig(list: PlotSeries[]): string {
    const parts = list.map(
      (s) =>
        `${s.color}|${s.width ?? 2}|${s.dash ? 1 : 0}|${s.showPoints ? 1 : 0}|${s.band ? 1 : 0}|${s.label ?? ""}`,
    );

    return `${parts.join(";")}#${legend}#${xScale}#${yScale}`;
  }

  function axisFmt(scale: Scale, custom?: (v: number) => string): uPlotType.Axis.Values {
    if (custom) {
      return (u, splits) => splits.map((v) => (v == null ? "" : custom(v)));
    }
    if (scale === "log") {
      return (u, splits) => splits.map((v) => (v != null && isDecade(v) ? pow10(v) : ""));
    }

    return (u, splits) => splits.map((v) => (v == null ? "" : String(v)));
  }

  function axisFilter(scale: Scale): uPlotType.Axis.Filter | undefined {
    // Log axes: keep only decade splits so grid/ticks match the old plots.
    if (scale === "log") {
      return (u, splits) => splits.map((v) => (isDecade(v) ? v : null));
    }

    return undefined;
  }

  function buildOpts(): uPlotType.Options {
    const sers: uPlotType.Series[] = [{}];
    const bands: uPlotType.Band[] = [];
    for (const s of curSeries) {
      const strokeFn = () => resolve(s.color);
      if (s.band) {
        const lo = sers.length;
        const bandFill = () => resolve(s.bandColor ?? withAlpha(s.color, 0.16));
        sers.push({ stroke: "transparent", fill: bandFill, points: { show: false } });
        sers.push({ stroke: "transparent", fill: bandFill, points: { show: false } });
        bands.push({ series: [lo, lo + 1], fill: bandFill });
      }
      sers.push({
        label: s.label,
        stroke: strokeFn,
        width: s.width ?? 2,
        dash: s.dash ? [6, 4] : undefined,
        points: s.showPoints
          ? { show: true, size: 7, stroke: strokeFn, fill: strokeFn }
          : { show: false },
      });
    }

    const axisBase = {
      stroke: () => resolve(C.muted),
      grid: { stroke: () => resolve(withAlpha(C.line, 0.6)), width: 1 },
      ticks: { stroke: () => resolve(withAlpha(C.line, 0.6)), width: 1, size: 5 },
      font: "11px ui-monospace, monospace",
      labelFont: "12px ui-monospace, monospace",
    };

    return {
      width: curW,
      height: curH,
      scales: {
        x: { time: false, distr: xScale === "log" ? 3 : 1, range: (u, a, b) => curX ?? [a, b] },
        y: { distr: yScale === "log" ? 3 : 1, range: (u, a, b) => curY ?? [a, b] },
      },
      axes: [
        { ...axisBase, scale: "x", label: xLabel || undefined, values: axisFmt(xScale, xFmt), filter: axisFilter(xScale) },
        { ...axisBase, scale: "y", label: yLabel || undefined, values: axisFmt(yScale, yFmt), filter: axisFilter(yScale) },
      ],
      series: sers,
      bands,
      legend: { show: legend },
      cursor: { show: false },
      hooks: {
        draw: [
          (u) => {
            if (curAnnotate) {
              curAnnotate({
                ctx: u.ctx,
                x: (v) => u.valToPos(v, "x", true),
                y: (v) => u.valToPos(v, "y", true),
                bbox: u.bbox,
                color: resolve,
                pxr: uplib ? uplib.pxRatio : window.devicePixelRatio || 1,
              });
            }
          },
        ],
      },
    };
  }

  function rebuild(): void {
    if (!uplib || !host) {
      return;
    }
    plot?.destroy();
    plot = new uplib(buildOpts(), buildData(), host);
    lastSig = sig(curSeries);
  }

  onMount(() => {
    void (async () => {
      const mod = await import("uplot");
      if (destroyed || !host) {
        return;
      }
      uplib = mod.default;
      curW = host.clientWidth || 600;
      curH = height;
      curX = xRange;
      curY = yRange;
      curSeries = series;
      curAnnotate = annotate;
      rebuild();
      ro = new ResizeObserver(() => {
        if (plot && host) {
          const w = host.clientWidth;
          if (w > 0 && w !== curW) {
            curW = w;
            plot.setSize({ width: curW, height: curH });
          }
        }
      });
      ro.observe(host);
      themeObs = new MutationObserver(() => {
        cache.clear();
        plot?.redraw();
      });
      themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    })();
  });

  onDestroy(() => {
    destroyed = true;
    ro?.disconnect();
    themeObs?.disconnect();
    plot?.destroy();
    plot = null;
  });

  // Push prop changes into uPlot. Structural changes (series count/style) rebuild;
  // everything else is a cheap setData. Reads props so it re-runs on any change,
  // and only WRITES the non-reactive mirrors -- never the state it reads.
  $effect(() => {
    void series;
    void xRange;
    void yRange;
    void annotate;
    const h = height;
    curSeries = series;
    curX = xRange;
    curY = yRange;
    curAnnotate = annotate;
    if (!plot) {
      return;
    }
    if (h !== curH) {
      curH = h;
      plot.setSize({ width: curW, height: curH });
    }
    if (sig(series) !== lastSig) {
      rebuild();
    } else {
      plot.setData(buildData());
    }
  });
</script>

<div class="lineplot" bind:this={host} style="height:{height}px"></div>

<style>
  .lineplot {
    width: 100%;
  }
  /* keep the (optional) uPlot legend legible on either theme */
  .lineplot :global(.u-legend) {
    color: var(--fg);
    font-size: 12px;
  }
</style>
