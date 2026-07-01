<script lang="ts">
  // Section-03 cluster: coherent amplitude (~ theta) vs the matched Pauli
  // probability (~ theta^2). The two series are static; a slider drives the live
  // marker so the reader can compare the curves at any angle.
  import { C } from "$shared/colors";
  import Plot, { type Series } from "./Plot.svelte";
  import Range from "./Range.svelte";

  const PI = Math.PI;
  const fmtAngle = (v: number) => `${v.toFixed(2)} rad`;

  // Coherent over-rotation: net error amplitude ~ sin(theta) ~ theta (LINEAR). A
  // depolarizing flip of "comparable strength" sin^2(theta/2) grows only ~ theta^2.
  const coVsInc: Series[] = (() => {
    const coh: [number, number][] = [];
    const inc: [number, number][] = [];
    for (let i = 0; i <= 60; i++) {
      const th = (i / 60) * (PI / 2);
      // single-shot infidelity-like measures, normalised to [0,1] at theta=pi/2.
      const ampl = Math.sin(th); // coherent: error amplitude ~ theta (sin)
      const prob = Math.sin(th / 2) ** 2 * 2; // incoherent: ~ theta^2, scaled to meet at pi/2
      coh.push([th, ampl]);
      inc.push([th, Math.min(1, prob)]);
    }

    return [
      { pts: coh, color: C.accent2, label: "coherent (amplitude ∝ θ)" },
      { pts: inc, color: C.muted, label: "Pauli approx (prob ∝ θ²)", dash: true },
    ];
  })();

  let thetaCmp = $state(0.5);
</script>

<div class="plotwrap">
  <Plot
    series={coVsInc}
    xmin={0}
    xmax={PI / 2}
    ymin={0}
    ymax={1}
    marker={thetaCmp}
    xlabel="rotation angle θ"
    ylabel="error size"
    height={170}
  />
  <Range bind:value={thetaCmp} min={0} max={PI / 2} step={0.01} label="θ" format={fmtAngle} />
</div>

<style>
  .plotwrap {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
</style>
