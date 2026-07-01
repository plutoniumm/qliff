<script lang="ts">
  // Section-05 cluster: the negativity gamma(theta) = sum |w_k| for the RZ
  // decomposition. A gauge shows gamma at the current angle; the slider scrubs the
  // marker along the curve. (In the old page component this slider shared its state
  // with the section-04 decomposition; as a self-contained island it owns its own.)
  import { C } from "$shared/colors";
  import Plot, { type Series } from "./Plot.svelte";
  import Range from "./Range.svelte";
  import { rotationGamma } from "./channel";

  const PI = Math.PI;
  const fmtAngle = (v: number) => `${v.toFixed(2)} rad`;

  let thetaDec = $state(0.6);
  const rotGamma = $derived(rotationGamma(thetaDec));

  const gammaCurve: Series[] = (() => {
    const pts: [number, number][] = [];
    for (let i = 0; i <= 80; i++) {
      const th = (i / 80) * 2 * PI;
      pts.push([th, rotationGamma(th)]);
    }

    return [{ pts, color: C.accent, label: "γ(θ)" }];
  })();
</script>

<div class="plotwrap">
  <div class="gauge">
    <span class="gnum mono" style="color:{rotGamma > 1.001 ? C.accent : C.ok}">γ = {rotGamma.toFixed(3)}</span>
    <span class="gsub">at θ = {thetaDec.toFixed(2)} rad</span>
  </div>
  <Plot
    series={gammaCurve}
    xmin={0}
    xmax={2 * PI}
    ymin={1}
    ymax={2.2}
    marker={thetaDec}
    xlabel="rotation angle θ"
    ylabel="γ"
    height={160}
  />
  <Range bind:value={thetaDec} min={0} max={2 * PI} step={0.01} label="rotation angle θ" format={fmtAngle} />
</div>

<style>
  .plotwrap {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .gauge {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }

  .gnum {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .gsub {
    font-size: 12.5px;
    color: var(--muted);
  }
</style>
