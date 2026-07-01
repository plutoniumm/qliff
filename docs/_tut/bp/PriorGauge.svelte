<script lang="ts">
  // Section 3 island: prior probability p -> prior LLR gauge. Drag the slider;
  // the gauge shows ell = log((1 - p) / p) in nats, the number qliff seeds BP
  // with per mechanism. Self-contained so its slider lives beside it.
  import { llrFromP } from "./bp";
  import { C, heat, withAlpha } from "$lib/colors";

  let pPrior = $state(0.05);
  const priorLlr = $derived(llrFromP(pPrior));
</script>

<div class="gauge-row">
  <label class="slider">
    <span class="slider-row">
      <span class="slider-label">error prior p</span>
      <span class="slider-value mono">{pPrior}</span>
    </span>
    <input type="range" min={0.001} max={0.5} step={0.001} bind:value={pPrior} />
  </label>
  <div class="gauge">
    <div class="gauge-num mono" style="color:{priorLlr < 0 ? C.bad : C.fg}">
      &#8467; = {priorLlr >= 0 ? "+" : ""}{priorLlr.toFixed(2)}
    </div>
    <div class="gauge-track">
      <div class="gauge-zero"></div>
      <div
        class="gauge-fill"
        class:neg={priorLlr < 0}
        style="width:{Math.min(50, (Math.abs(priorLlr) / 7) * 50).toFixed(1)}%;
               background:{priorLlr < 0 ? C.bad : withAlpha(heat(Math.min(1, priorLlr / 7)), 0.9)}"
      ></div>
    </div>
    <div class="gauge-ends">
      <span style="color:{C.bad}">error</span>
      <span style="color:{C.muted}">no error</span>
    </div>
  </div>
</div>

<style>
  /* slider, inlined from the shared control so this island stands alone */
  .slider {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .slider-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }

  .slider-label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .slider-value {
    font-size: 13px;
    color: var(--fg);
  }

  .gauge-row {
    display: grid;
    grid-template-columns: 1fr 1.2fr;
    gap: 22px;
    align-items: center;
  }

  .gauge-num {
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 8px;
    text-align: center;
  }

  .gauge-track {
    position: relative;
    height: 16px;
    border-radius: 5px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    overflow: hidden;
  }

  .gauge-zero {
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--line-strong);
  }

  .gauge-fill {
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    transition:
      width 0.15s ease,
      background 0.15s ease;
  }

  .gauge-fill.neg {
    left: auto;
    right: 50%;
  }

  .gauge-ends {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    margin-top: 5px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  @media (max-width: 720px) {
    .gauge-row {
      grid-template-columns: 1fr;
    }
  }
</style>
