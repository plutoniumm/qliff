<script lang="ts">
  // Section-02 cluster: the interactive Bloch playground. Discrete Cliffords mutate
  // a base state; a live continuous RZ(theta) rides on top. This wrapper owns the
  // control state (was in the old Coherent.svelte page component) so the markdown
  // page can mount it as ONE self-contained island.
  import { C } from "$shared/colors";
  import Bloch from "./Bloch.svelte";
  import Range from "./Range.svelte";
  import { applyGate, applyRz, type Vec3, type GateName } from "./bloch";

  const fmtAngle = (v: number) => `${v.toFixed(2)} rad`;

  // base = state after clicked gates; live = after the RZ(theta) slider.
  let base = $state<Vec3>([1, 0, 0]); // start at |+> so a z-rotation is visible
  let thetaPlay = $state(0.9);

  const livePlay = $derived(applyRz(thetaPlay, base));

  function gate(g: GateName) {
    base = applyGate(g, base);
  }

  function reset() {
    base = [1, 0, 0];
    thetaPlay = 0.9;
  }
</script>

<div class="panel">
  <div class="stage">
    <Bloch vec={livePlay} ghost={thetaPlay !== 0 ? base : null} sweep={thetaPlay} label="interactive Bloch sphere" />
  </div>
  <div class="controls">
    <div class="btnrow">
      <button onclick={() => gate("X")} style="--bc:{C.x}">X</button>
      <button onclick={() => gate("Z")} style="--bc:{C.z}">Z</button>
      <button onclick={() => gate("H")} style="--bc:{C.accent}">H</button>
      <button onclick={() => gate("S")} style="--bc:{C.accent2}">S</button>
      <button class="ghost" onclick={reset}>reset</button>
    </div>
    <Range bind:value={thetaPlay} min={0} max={2 * Math.PI} step={0.01} label="coherent RZ(θ)" format={fmtAngle} />
    <p class="hint">
      A <em>tiny</em> θ looks harmless. But the same miscalibration fires every round: apply it
      repeatedly and the arrow sweeps all the way around. Coherent errors accumulate in the
      <strong style="color:{C.accent2}">amplitude</strong>, not the probability.
    </p>
  </div>
</div>

<style>
  .panel {
    display: grid;
    grid-template-columns: minmax(280px, 1fr) minmax(300px, 1fr);
    gap: 22px;
    align-items: center;
  }

  @media (max-width: 760px) {
    .panel {
      grid-template-columns: 1fr;
    }
  }

  .stage {
    /* EXPLICIT modest height so the 3D sphere always fits a laptop viewport.
       No aspect-ratio: in a 1fr grid column that let the canvas balloon past
       the global 62vh cap on wide screens. The Bloch canvas fills this box. */
    height: 360px;
    max-height: 50vh;
    border-radius: var(--r-md);
    background:
      radial-gradient(120% 120% at 50% 0%, color-mix(in srgb, var(--accent) 8%, transparent), transparent 70%);
  }

  .controls {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .btnrow {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .btnrow button {
    font-family: ui-monospace, monospace;
    font-weight: 700;
    font-size: 14px;
    padding: 7px 14px;
    border-radius: 8px;
    color: var(--fg);
    background: color-mix(in srgb, var(--bc, var(--accent)) 14%, transparent);
    border: 1px solid color-mix(in srgb, var(--bc, var(--accent)) 55%, transparent);
    cursor: pointer;
    transition:
      background var(--dur-fast) var(--ease-out),
      transform var(--dur-fast) var(--ease-out);
  }

  .btnrow button:hover {
    background: color-mix(in srgb, var(--bc, var(--accent)) 26%, transparent);
  }

  .btnrow button:active {
    transform: translateY(1px);
  }

  .btnrow button.ghost {
    --bc: var(--muted);
    font-weight: 600;
  }

  .hint {
    font-size: 13.5px;
    line-height: 1.55;
    color: var(--muted);
    margin: 0;
  }
</style>
