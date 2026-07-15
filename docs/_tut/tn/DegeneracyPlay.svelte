<script lang="ts">
  // Section 2 island -- degeneracy made visible. A 3-data-qubit repetition code
  // (2 detectors) PLUS one measurement-error mechanism per detector, so a lit
  // syndrome (1,1) is explainable many ways and each logical class holds several
  // patterns: real intra-class degeneracy to sum over. Two sliders (data error p,
  // measurement error) drive the enumeration; check/uncheck rows to build the
  // class sums by hand and watch which one the argmax picks. Self-contained: all
  // state lives here (this was prose-coupled in the old page component), no
  // $effect writes back into shared state.
  import TnSlider from "./TnSlider.svelte";
  import { C } from "$lib/colors";
  import {
    repetitionDem,
    enumerateErrors,
    minWeightPick,
    type Dem,
  } from "./decoder";

  let p = $state(0.15); // data-qubit error probability
  let measP = $state(0.3); // measurement-error probability

  const demDeg: Dem = $derived(repetitionDem(3, p, measP));
  // syndrome (1,1): both checks lit.
  const synDeg = [1, 1];
  const enumDeg = $derived(enumerateErrors(demDeg, synDeg));
  const consistentConfigs = $derived(enumDeg.configs.filter((c) => c.detsOk));

  // user toggles which consistent configs to EXCLUDE from the running sum
  // (keyed by config id so the set survives length changes; no effect writes).
  let excluded = $state<Set<number>>(new Set());
  function toggleConfig(id: number): void {
    const next = new Set(excluded);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    excluded = next;
  }

  const sumByClass = $derived.by(() => {
    const w = [0, 0];
    consistentConfigs.forEach((cfg) => {
      if (!excluded.has(cfg.id)) {
        w[cfg.logical] += cfg.prob;
      }
    });

    return w;
  });
  const degVerdict = $derived(sumByClass[1] > sumByClass[0] ? 1 : 0);
  const mwVerdict = $derived(minWeightPick(demDeg, synDeg));
  const degDisagree = $derived(
    mwVerdict.logical !== null && mwVerdict.logical !== degVerdict,
  );
  const winClassConfigs = $derived(
    consistentConfigs.filter((c) => c.logical === degVerdict),
  );
  const winBestSingle = $derived(
    winClassConfigs.reduce((m, c) => Math.max(m, c.prob), 0),
  );
  const winSum = $derived(sumByClass[degVerdict]);
  const degBoost = $derived(winBestSingle > 0 ? winSum / winBestSingle : 1);

  function classLabel(c: number): string {
    return c === 0 ? "I (no logical flip)" : "L (logical flip)";
  }

  // pretty-print which mechanisms fired in a config (q = data, m = measurement).
  function configLabel(cfg: { bits: number[] }): string {
    const names = cfg.bits
      .map((b, idx) => (b ? demDeg.mechanisms[idx].label : null))
      .filter(Boolean);

    return names.length ? names.join(" ") : "(none)";
  }

  function weightBar(w: number[], k: number): { h: number; color: string } {
    const total = w.reduce((s, x) => s + x, 0) || 1;
    const t = w[k] / total;

    return { h: t, color: k === 0 ? C.ok : C.accent3 };
  }
</script>

<div class="ctrl-row">
  <TnSlider bind:value={p} min={0.02} max={0.4} step={0.01} label="data error p" />
  <TnSlider bind:value={measP} min={0.0} max={0.4} step={0.01} label="measurement error" />
</div>

<div class="cfg-table">
  <div class="cfg-head mono">
    <span>in sum</span><span>error pattern</span><span>P(e)</span><span>logical class</span>
  </div>
  {#each consistentConfigs as cfg (cfg.id)}
    <label class="cfg-row">
      <input
        type="checkbox"
        checked={!excluded.has(cfg.id)}
        onchange={() => toggleConfig(cfg.id)}
      />
      <span class="mono err">{configLabel(cfg)}</span>
      <span class="mono">{cfg.prob.toFixed(5)}</span>
      <span class="mono cls" style="color:{cfg.logical === 0 ? C.ok : C.accent3}"
        >{classLabel(cfg.logical)}</span
      >
    </label>
  {/each}

  <div class="cfg-totals">
    {#each [0, 1] as k}
      {@const bar = weightBar(sumByClass, k)}
      <div class="tot">
        <div class="tot-name" style="color:{bar.color}">
          {classLabel(k)}{k === degVerdict ? "  ◀ argmax" : ""}
        </div>
        <div class="tot-track">
          <div
            class="tot-fill"
            style="width:{(bar.h * 100).toFixed(1)}%; background:{bar.color}"
          ></div>
        </div>
        <div class="mono tot-val">{sumByClass[k].toExponential(2)}</div>
      </div>
    {/each}
  </div>
</div>

<p class="verdict-prose">
  A min-weight decoder commits to the single most probable pattern,
  <span class="mono">{mwVerdict.bits ? configLabel({ bits: mwVerdict.bits }) : "--"}</span>
  (probability <span class="mono">{mwVerdict.prob.toExponential(2)}</span>), and reads its class,
  <strong style="color:{mwVerdict.logical === 0 ? C.ok : C.accent3}"
    >{mwVerdict.logical === null ? "--" : classLabel(mwVerdict.logical)}</strong
  >, off that one error. But maximum likelihood compares the
  <em>total</em> weight of each class. Class
  <strong style="color:{degVerdict === 0 ? C.ok : C.accent3}">{classLabel(degVerdict)}</strong>
  gathers <strong>{winClassConfigs.length}</strong> consistent patterns summing to
  <span class="mono">{winSum.toExponential(2)}</span>, a
  <strong>{degBoost.toFixed(1)}×</strong> boost over its single best member.
  {#if degDisagree}
    <strong style="color:{C.accent}"
      >Here that summed weight overturns the min-weight verdict</strong
    >: the two decoders disagree, and MLD is the optimal answer.
  {:else}
    Raise the measurement error and the boosted class will overtake the single cheapest error, and the
    two decoders flip apart.
  {/if}
</p>

<style>
  .ctrl-row {
    display: flex;
    flex-wrap: wrap;
    gap: 18px 28px;
    align-items: center;
    margin-bottom: 14px;
  }

  .cfg-table {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .cfg-head,
  .cfg-row {
    display: grid;
    grid-template-columns: 60px 1fr 90px 1.4fr;
    align-items: center;
    gap: 10px;
    padding: 7px 10px;
    font-size: 13px;
  }

  .cfg-head {
    color: var(--faint);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .cfg-row {
    border-radius: 8px;
    background: color-mix(in srgb, var(--bg-2) 50%, transparent);
    cursor: pointer;
  }

  .cfg-row:hover {
    background: color-mix(in srgb, var(--bg-2) 75%, transparent);
  }

  .cfg-row .err {
    color: var(--fg);
  }

  .cfg-totals {
    margin-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .tot {
    display: grid;
    grid-template-columns: 180px 1fr 96px;
    align-items: center;
    gap: 12px;
  }

  .tot-name {
    font-size: 13px;
    font-weight: 600;
  }

  .tot-track {
    height: 16px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    overflow: hidden;
  }

  .tot-fill {
    height: 100%;
    border-radius: 6px;
    transition: width 200ms var(--ease-out);
  }

  .tot-val {
    font-size: 12px;
    color: var(--muted);
    text-align: right;
  }

  .verdict-prose {
    margin-top: 20px;
    line-height: 1.6;
  }
</style>
