<script lang="ts">
  // Self-contained verdict grid: owns the seeded shot batch + the reshuffle
  // control so the figure is a standalone island (state was in Ler.svelte).
  import ShotsGrid from "./ShotsGrid.svelte";
  import { mulberry32 } from "$lib/rng";

  interface Shot {
    observed: boolean;
    predicted: boolean;
  }

  // Seeded initial grid: ~12% of shots are logical errors (predicted != observed).
  function makeShots(n: number, errFrac: number, seed: number): Shot[] {
    const rng = mulberry32(seed);
    const out: Shot[] = [];
    for (let i = 0; i < n; i += 1) {
      const observed = rng() < 0.3;
      const wrong = rng() < errFrac;
      out.push({ observed, predicted: wrong ? !observed : observed });
    }

    return out;
  }
  let shots = $state(makeShots(48, 0.12, 7));
  function reshuffle(): void {
    shots = makeShots(48, 0.12, Math.floor(Math.random() * 1e9));
  }
</script>

<ShotsGrid bind:shots />
<div class="ctl-row">
  <button onclick={reshuffle}>↻ new random batch</button>
</div>

<style>
  .ctl-row {
    display: flex;
    gap: 10px;
    margin-top: 14px;
  }
</style>
