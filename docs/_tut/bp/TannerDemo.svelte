<script lang="ts">
  // Section 2 island: the interactive Tanner graph. Toggle chips light detectors
  // (that is the syndrome). The readout then decodes by brute force: it tests
  // all 2^5 = 32 error sets against H e = s over GF(2) and ranks the consistent
  // ones by posterior probability. Real codes are too big for this; BP is how
  // the same ranking is found without enumeration.
  import TannerGraph from "./TannerGraph.svelte";
  import { makeCode, type Code } from "./bp";

  const H: number[][] = [
    [1, 1, 0, 0, 0],
    [0, 1, 1, 1, 0],
    [0, 0, 0, 1, 1],
  ];
  const N = 5;
  const P = 0.06;

  const tannerCode: Code = makeCode(H, Array(N).fill(P));

  let litChecks = $state<boolean[]>([false, true, false]);
  const tannerSyndrome = $derived(litChecks.map((b) => (b ? 1 : 0)));
  let tannerHover = $state<{ kind: "var" | "check"; idx: number } | null>(null);

  function toggleCheck(c: number): void {
    litChecks = litChecks.map((b, i) => (i === c ? !b : b));
  }

  interface Explanation {
    bits: number[];
    weight: number;
    share: number; // probability of this error set given the syndrome
  }

  const explanations = $derived.by((): Explanation[] => {
    const found: { bits: number[]; weight: number; prob: number }[] = [];

    for (let mask = 0; mask < 1 << N; mask += 1) {
      const bits = Array.from({ length: N }, (_, m) => (mask >> m) & 1);
      const consistent = H.every(
        (row, c) => row.reduce((s, h, m) => s ^ (h & bits[m]), 0) === tannerSyndrome[c],
      );
      if (!consistent) {
        continue;
      }
      const weight = bits.reduce((s, b) => s + b, 0);

      found.push({
        bits,
        weight,
        prob: P ** weight * (1 - P) ** (N - weight),
      });
    }
    const total = found.reduce((s, f) => s + f.prob, 0);

    return found
      .sort((a, b) => a.weight - b.weight)
      .map((f) => ({
        bits: f.bits,
        weight: f.weight,
        share: f.prob / total,
      }));
  });

  const bestShare = $derived(explanations[0]?.share ?? 0);

  function labelOf(ex: Explanation): string {
    const names = ex.bits.flatMap((b, m) => (b === 1 ? [`e${m}`] : []));

    return names.length === 0 ? "no error" : names.join(" + ");
  }
</script>

<TannerGraph
  code={tannerCode}
  syndrome={tannerSyndrome}
  bind:hover={tannerHover}
  height={250}
/>
<div class="check-toggles">
  {#each litChecks as lit, c (c)}
    <button class="chip" class:on={lit} onclick={() => toggleCheck(c)}>
      detector d{c}: {lit ? "lit" : "quiet"}
    </button>
  {/each}
</div>
<div class="explain">
  <div class="head">
    error sets consistent with syndrome {tannerSyndrome.join("")}:
    {explanations.length} of 32
  </div>
  {#each explanations as ex (labelOf(ex))}
    <div class="row" class:best={ex.share === bestShare}>
      <code>{labelOf(ex)}</code>
      <span class="w">weight {ex.weight}</span>
      <span class="track"><i style:width="{(100 * ex.share).toFixed(1)}%"></i></span>
      <span class="p">{(100 * ex.share).toFixed(1)}%</span>
    </div>
  {/each}
  <div class="note">
    % = probability given the syndrome (each mechanism fires with p = {P}).
    The decoder's job is to return the top row.
  </div>
</div>

<style>
  .check-toggles {
    margin-top: 14px;
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
  }

  .chip {
    font-size: 12.5px;
    padding: 6px 12px;
    border-radius: 99px;
    border: 1px solid var(--line);
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
    color: var(--muted);
  }

  .chip.on {
    border-color: color-mix(in srgb, var(--accent-3) 55%, transparent);
    background: color-mix(in srgb, #ffd166 16%, transparent);
    color: var(--fg);
  }

  .explain {
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .head {
    font-size: 11.5px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 2px;
  }

  .row {
    display: grid;
    grid-template-columns: minmax(130px, auto) 66px 1fr 46px;
    align-items: center;
    gap: 10px;
    font-size: 12.5px;
    padding: 4px 9px;
    border-radius: 6px;
    border: 1px solid transparent;
  }

  .row code {
    color: var(--fg);
  }

  .row .w {
    color: var(--muted);
    font-size: 11.5px;
  }

  .row .track {
    height: 6px;
    border-radius: 3px;
    background: color-mix(in srgb, var(--line) 55%, transparent);
    overflow: hidden;
  }

  .row .track i {
    display: block;
    height: 100%;
    background: color-mix(in srgb, var(--accent) 75%, transparent);
  }

  .row .p {
    text-align: right;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }

  .row.best {
    border-color: color-mix(in srgb, var(--ok) 45%, transparent);
    background: color-mix(in srgb, var(--ok) 7%, transparent);
  }

  .row.best .track i {
    background: var(--ok);
  }

  .note {
    font-size: 11.5px;
    color: var(--faint);
    margin-top: 4px;
  }
</style>
