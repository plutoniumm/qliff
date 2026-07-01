<script lang="ts">
  // Section 5 island: build your own perfect matching, then reveal the optimum
  // and see whether you beat it. Click two nodes (defects or L/R boxes) to pair
  // them; the scoreboard compares your total weight to the min-weight matching.
  import RepCode from "./RepCode.svelte";
  import {
    LEFT,
    RIGHT,
    syndrome,
    minWeightMatching,
    matchingWeight,
    type MatchResult,
  } from "./matching";
  import { mulberry32, bernoulli } from "$lib/rng";

  const D = 9;
  const p = 0.08;

  function buildErrors(): boolean[] {
    const e = new Array(D).fill(false);
    // qubits {2, 6, 7} -> defects at gaps {1,2,5,7}: two short chains to pair.
    for (const q of [2, 6, 7]) {
      e[q] = true;
    }

    return e;
  }

  let errors = $state<boolean[]>(buildErrors());
  const defects = $derived(syndrome(errors));

  // user's in-progress matching: list of selected node ids; pair them up FIFO.
  let userSel = $state<number[]>([]);
  let userPairs = $state<[number, number][]>([]);

  function pickNode(id: number): void {
    // ignore if this node is already matched.
    if (userPairs.some(([a, b]) => a === id || b === id)) {
      return;
    }
    if (userSel.includes(id)) {
      userSel = userSel.filter((x) => x !== id);

      return;
    }
    const sel = [...userSel, id];
    if (sel.length === 2) {
      userPairs = [...userPairs, [sel[0], sel[1]]];
      userSel = [];
    } else {
      userSel = sel;
    }
  }

  function resetUser(): void {
    userSel = [];
    userPairs = [];
  }

  // which defects are still unmatched by the user?
  const userMatchedNodes = $derived.by(() => {
    const s = new Set<number>();
    for (const [a, b] of userPairs) {
      s.add(a);
      s.add(b);
    }

    return s;
  });
  const userComplete = $derived(defects.every((g) => userMatchedNodes.has(g)));
  const userWeight = $derived(userComplete ? matchingWeight(userPairs, D, p) : null);

  const optimal = $derived<MatchResult>(minWeightMatching(defects, D, p));
  let revealOpt = $state(false);

  function reseed(): void {
    const rng = mulberry32((Math.random() * 1e9) | 0);
    const e = new Array(D).fill(false);
    for (let q = 0; q < D; q += 1) {
      e[q] = bernoulli(rng, 0.18);
    }
    errors = e;
    resetUser();
    revealOpt = false;
  }

  const userOverlay = $derived<[number, number][]>(userPairs);
</script>

<RepCode
  d={D}
  {errors}
  {defects}
  matching={userOverlay}
  interactive={true}
  onClickDefect={pickNode}
  onToggleQubit={(q) => (errors = errors.map((e, i) => (i === q ? !e : e)))}
  height={34}
/>
<div class="row gap wrap">
  <button onclick={() => pickNode(LEFT)} disabled={userMatchedNodes.has(LEFT)}>pair to L boundary</button>
  <button onclick={() => pickNode(RIGHT)} disabled={userMatchedNodes.has(RIGHT)}>pair to R boundary</button>
  <button onclick={resetUser}>reset matching</button>
  <button onclick={reseed}>new errors</button>
</div>
<div class="scoreboard">
  <div class="score">
    <span class="k">your cost</span>
    <span class="v mono" style="color:var(--accent2)">
      {userWeight === null ? "-- match all defects --" : userWeight.toFixed(2)}
    </span>
  </div>
  <button class="reveal" onclick={() => (revealOpt = !revealOpt)}>
    {revealOpt ? "hide" : "reveal"} optimum
  </button>
  <div class="score">
    <span class="k">min weight</span>
    <span class="v mono" style="color:{revealOpt ? 'var(--ok)' : 'var(--muted)'}">
      {revealOpt ? optimal.weight.toFixed(2) : "???"}
    </span>
  </div>
  {#if revealOpt && userWeight !== null}
    <div class="verdict mono" class:win={userWeight <= optimal.weight + 1e-6}>
      {userWeight <= optimal.weight + 1e-6
        ? "optimal!"
        : `+${(userWeight - optimal.weight).toFixed(2)} over`}
    </div>
  {/if}
</div>
{#if revealOpt}
  <div class="prose-inline">
    <span class="tag">optimum:</span>
    <RepCode
      d={D}
      {errors}
      {defects}
      matching={optimal.pairs}
      correction={optimal.correction}
      interactive={false}
      height={34}
    />
  </div>
{/if}

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
    flex-wrap: wrap;
  }

  .tag {
    font-size: 12px;
    color: var(--muted);
  }

  .mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }

  .scoreboard {
    display: flex;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
    margin-top: 14px;
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: color-mix(in srgb, var(--bg-2) 55%, transparent);
  }

  .score {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .score .k {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .score .v {
    font-size: 22px;
    font-weight: 700;
  }

  .reveal {
    margin-left: auto;
  }

  .verdict {
    font-size: 15px;
    font-weight: 700;
    color: var(--bad);
  }

  .verdict.win {
    color: var(--ok);
  }

  .prose-inline {
    margin-top: 14px;
  }
</style>
