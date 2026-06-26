<script lang="ts">
  import Section from "$lib/Section.svelte";
  import TeX from "$lib/Math.svelte";
  import Slider from "$lib/Slider.svelte";
  import Toggle from "$lib/Toggle.svelte";
  import Scrubber from "$lib/Scrubber.svelte";
  import Callout from "$lib/Callout.svelte";
  import Figure from "$lib/Figure.svelte";
  import Worked from "$lib/Worked.svelte";
  import { C, withAlpha } from "$lib/colors";
  import { mulberry32, bernoulli } from "$lib/rng";
  import RepCode from "./RepCode.svelte";
  import {
    LEFT,
    RIGHT,
    syndrome,
    minWeightMatching,
    matchingWeight,
    edgeWeight,
    chainLength,
    logicalFailed,
    type MatchResult,
  } from "./matching";

  // ----- Section 1: the problem -----------------------------------------
  const D1 = 9;
  let errors1 = $state<boolean[]>(new Array(D1).fill(false));
  const defects1 = $derived(syndrome(errors1));

  function toggle1(q: number): void {
    errors1 = errors1.map((e, i) => (i === q ? !e : e));
  }

  function clearAll(): void {
    errors1 = new Array(D1).fill(false);
  }

  function makeChain(): void {
    // a contiguous chain in the middle: lights only its two endpoints.
    const next = new Array(D1).fill(false);
    for (let q = 3; q <= 5; q += 1) {
      next[q] = true;
    }
    errors1 = next;
  }

  // ----- Section 2: defects come in pairs -------------------------------
  // Two different error chains that produce the SAME syndrome (gaps 2 and 6).
  const D2 = 9;
  // a fixed syndrome: defects at gaps 2 and 6.
  const syn2: number[] = [2, 6];
  // distinct explanations (sets of flipped qubits) all giving that syndrome.
  // For an interior 2-defect syndrome there are exactly two error classes; they
  // differ by the global (logical) operator -- which is precisely why a wrong
  // pick later becomes a logical error.
  const explanations2: { label: string; qubits: number[] }[] = [
    { label: "inner chain (4 flips)", qubits: [3, 4, 5, 6] },
    { label: "outer chain (5 flips)", qubits: [0, 1, 2, 7, 8] },
  ];
  let pick2 = $state(0);
  const errors2 = $derived.by(() => {
    const e = new Array(D2).fill(false);
    for (const q of explanations2[pick2].qubits) {
      e[q] = true;
    }

    return e;
  });
  // sanity: every explanation truly yields syn2 (used only for display).
  const defects2 = $derived(syndrome(errors2));

  // ----- Section 3 & 4: the matching graph + weights --------------------
  const D34 = 9;
  let errors34 = $state<boolean[]>(seedErrors(D34, 0x51));
  let p34 = $state(0.08);
  let showWeights34 = $state(true);
  const defects34 = $derived(syndrome(errors34));

  function seedErrors(d: number, seed: number): boolean[] {
    const rng = mulberry32(seed);
    const e = new Array(d).fill(false);
    // a couple of separated short chains so the graph is interesting.
    for (let q = 0; q < d; q += 1) {
      e[q] = bernoulli(rng, 0.16);
    }

    return e;
  }

  // candidate edges of the matching graph: every defect to every other defect,
  // and every defect to its two boundaries.
  const candidateEdges34 = $derived.by<[number, number][]>(() => {
    const ds = defects34;
    const edges: [number, number][] = [];
    for (let i = 0; i < ds.length; i += 1) {
      edges.push([ds[i], LEFT]);
      edges.push([ds[i], RIGHT]);
      for (let j = i + 1; j < ds.length; j += 1) {
        edges.push([ds[i], ds[j]]);
      }
    }

    return edges;
  });

  let hoverEdge34 = $state<[number, number] | null>(null);

  const w34 = $derived(edgeWeight(p34));
  // a small p -> weight table.
  const pTable = [0.5, 0.2, 0.1, 0.05, 0.01, 0.001];

  function reseed34(): void {
    errors34 = seedErrors(D34, (Math.random() * 1e9) | 0);
    hoverEdge34 = null;
  }

  function edgeLabel(a: number, b: number): string {
    const len = chainLength(a, b, D34);
    const bnd = a === LEFT || b === LEFT || a === RIGHT || b === RIGHT;

    return `${bnd ? "boundary, " : ""}len ${len} → ${(len * w34).toFixed(2)}`;
  }

  // ----- Section 5: try-your-own matching vs the optimum ----------------
  const D5 = 9;
  let errors5 = $state<boolean[]>(buildErrors5());
  let p5 = $state(0.08);
  const defects5 = $derived(syndrome(errors5));

  function buildErrors5(): boolean[] {
    const e = new Array(D5).fill(false);
    // qubits {2, 6, 7} -> defects at gaps {1,2,5,7}: two short chains to pair.
    for (const q of [2, 6, 7]) {
      e[q] = true;
    }

    return e;
  }

  // user's in-progress matching: list of selected node ids; pair them up FIFO.
  let userSel = $state<number[]>([]);
  let userPairs = $state<[number, number][]>([]);

  function nodeKey(id: number): string {
    if (id === LEFT) {
      return "L";
    }
    if (id === RIGHT) {
      return "R";
    }

    return `g${id}`;
  }

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
  const userComplete = $derived(defects5.every((g) => userMatchedNodes.has(g)));
  const userWeight = $derived(userComplete ? matchingWeight(userPairs, D5, p5) : null);

  const optimal5 = $derived<MatchResult>(minWeightMatching(defects5, D5, p5));
  let revealOpt = $state(false);

  function reseed5(): void {
    const rng = mulberry32((Math.random() * 1e9) | 0);
    const e = new Array(D5).fill(false);
    for (let q = 0; q < D5; q += 1) {
      e[q] = bernoulli(rng, 0.18);
    }
    errors5 = e;
    resetUser();
    revealOpt = false;
  }

  // selected nodes drawn as candidate edges for feedback isn't needed; we feed
  // userPairs as the matching overlay and highlight current selection.
  const userOverlay = $derived<[number, number][]>(userPairs);

  // ----- Section 6: matching -> correction -> survive? ------------------
  const D6 = 9;
  let errors6 = $state<boolean[]>(scenario6(false));
  const defects6 = $derived(syndrome(errors6));
  const match6 = $derived<MatchResult>(minWeightMatching(defects6, D6, 0.08));
  const failed6 = $derived(logicalFailed(errors6, match6.correction));
  // residual = error XOR correction.
  const residual6 = $derived(errors6.map((e, i) => e !== match6.correction[i]));

  function scenario6(spanning: boolean): boolean[] {
    const e = new Array(D6).fill(false);
    if (spanning) {
      // a long chain past the midpoint: the matcher pairs the lone defect to the
      // WRONG boundary, residual spans the line -> logical error.
      for (let q = 0; q <= 5; q += 1) {
        e[q] = true;
      }
    } else {
      for (let q = 2; q <= 4; q += 1) {
        e[q] = true;
      }
    }

    return e;
  }

  let scen6 = $state<"safe" | "fail">("safe");
  function setScen6(s: "safe" | "fail"): void {
    scen6 = s;
    errors6 = scenario6(s === "fail");
  }

  function toggle6(q: number): void {
    errors6 = errors6.map((e, i) => (i === q ? !e : e));
    scen6 = "safe";
  }

  // ----- Section 7: distance & reliability ------------------------------
  let d7 = $state(5);
  let p7 = $state(0.08);
  const SHOTS7 = 4000;

  // Monte-Carlo logical error rate of the MWPM-decoded rep code at (d, p).
  // Pure function of inputs -> $derived (no effect writing state).
  const ler7 = $derived.by(() => {
    const d = d7;
    const p = p7;
    const rng = mulberry32(0xbeef ^ (d << 8) ^ Math.round(p * 1000));
    let fails = 0;
    for (let s = 0; s < SHOTS7; s += 1) {
      const e: boolean[] = new Array(d);
      for (let q = 0; q < d; q += 1) {
        e[q] = bernoulli(rng, p);
      }
      const defs = syndrome(e);
      const m = minWeightMatching(defs, d, p);
      if (logicalFailed(e, m.correction)) {
        fails += 1;
      }
    }

    return fails / SHOTS7;
  });

  // a sweep of LER vs p at the current distance, for the little curve.
  const sweep7 = $derived.by(() => {
    const d = d7;
    const ps = [0.02, 0.04, 0.06, 0.08, 0.1, 0.13, 0.16, 0.2, 0.25, 0.3];
    const N = 2500;

    return ps.map((p) => {
      const rng = mulberry32(0x1234 ^ (d << 8) ^ Math.round(p * 1000));
      let fails = 0;
      for (let s = 0; s < N; s += 1) {
        const e: boolean[] = new Array(d);
        for (let q = 0; q < d; q += 1) {
          e[q] = bernoulli(rng, p);
        }
        const m = minWeightMatching(syndrome(e), d, p);
        if (logicalFailed(e, m.correction)) {
          fails += 1;
        }
      }

      return { p, ler: fails / N };
    });
  });

  // map a LER in [0,1] (log-ish) to a y in a small plot.
  function plotY(ler: number, h: number): number {
    const lo = 1e-4;
    const v = Math.max(ler, lo);
    const t = (Math.log10(v) - Math.log10(lo)) / (0 - Math.log10(lo));

    return h - t * h;
  }

  // ----- Section 7 scrubber: animate the matching search ----------------
  // We replay the recursive choice on a fixed instance, revealing chosen pairs
  // one at a time as the user scrubs.
  const optSearchPairs = $derived(minWeightMatching(defects34, D34, p34).pairs);
  let frame34 = $state(0);
  const shownPairs34 = $derived<[number, number][]>(optSearchPairs.slice(0, frame34));
</script>

<Section id="problem" step="01" title="Errors you can't see, checks that can talk">
  <p>
    A quantum memory stores information in fragile qubits. We can't peek at them
    directly -- measuring a qubit destroys the superposition it holds. Instead a
    code measures <em>parity checks</em>: each check reports whether a small group
    of qubits has an even or odd number of errors, without revealing the data.
  </p>
  <p>
    The simplest example is the <strong>repetition code</strong>. Lay data qubits
    in a line and put a <span style="color:var(--z)">Z-check</span> in every gap;
    it compares its two neighbours. Click a qubit below to inject an
    <span style="color:var(--x)">X error</span>. A check between a flipped and an
    unflipped qubit disagrees and <span style="color:var(--defect)">lights up</span>
    -- that lit check is a <strong>detection event</strong>, or
    <em>defect</em>.
  </p>

  <Figure
    title="Repetition code"
    legend={[
      { color: C.data, mark: "dot", label: "data qubit" },
      { color: C.x, mark: "dot", label: "X error (flipped qubit)" },
      { color: C.z, mark: "ring", label: "Z-check (quiet)" },
      { color: C.defect, mark: "dot", label: "lit check (defect)" },
      { color: C.muted, mark: "box", label: "boundary node (L / R)" },
    ]}
    caption="Click data qubits to flip them. A check fires iff its two neighbours disagree."
  >
    <RepCode
      d={D1}
      errors={errors1}
      defects={defects1}
      onToggleQubit={toggle1}
      height={48}
    />
    <div class="row gap">
      <button onclick={makeChain}>make a chain</button>
      <button onclick={clearAll}>clear</button>
      <span class="tag mono">{defects1.length} defect{defects1.length === 1 ? "" : "s"} lit</span>
    </div>
  </Figure>

  <Callout kind="key" title="A whole chain lights only its endpoints">
    Try <em>make a chain</em>: three adjacent errors, yet only two checks fire.
    Every interior check sees <em>two</em> flips and cancels. The syndrome never
    tells you the chain -- only where it <em>starts and ends</em>. That is the
    entire problem a decoder must solve.
  </Callout>
</Section>

<Section id="pairs" step="02" title="Defects come in pairs -- pick an explanation">
  <p>
    Because each error toggles the checks on its two sides, defects are always
    created in <strong>pairs</strong> (an end of the line acts as a silent
    partner -- the <em>boundary</em>). The syndrome is just a <em>set of lit
    defects</em>. The catch: different error patterns produce the very same set.
  </p>
  <p>
    Here the syndrome is fixed -- defects at the two highlighted gaps. Flip
    between two completely different error chains that both explain it. They
    differ by flipping the whole register: exactly the code's logical operator.
  </p>

  <Figure
    title="Degenerate syndrome"
    legend={[
      { color: C.x, mark: "dot", label: "X error (flipped qubit)" },
      { color: C.defect, mark: "dot", label: "lit check (defect)" },
      { color: C.data, mark: "dot", label: "untouched qubit" },
    ]}
    caption={`Both patterns light exactly the same defects (gaps ${syn2.join(" and ")}). Which one really happened? The syndrome can't tell us.`}
  >
    <RepCode
      d={D2}
      errors={errors2}
      defects={defects2}
      interactive={false}
      height={48}
    />
    <div class="row gap wrap">
      {#each explanations2 as ex, i (i)}
        <button class:active={pick2 === i} onclick={() => (pick2 = i)}>{ex.label}</button>
      {/each}
    </div>
  </Figure>

  <p>
    All consistent, all different. To <em>decode</em> we must commit to one. The
    guiding principle: pick the <strong>most likely</strong> error. Under
    independent noise with small error probability <TeX expr="p" />, fewer flips
    are exponentially more likely -- so we want the explanation that flips the
    <em>fewest</em> qubits. That is a <strong>minimum-weight</strong> choice, and
    the next sections make "weight" precise.
  </p>
</Section>

<Section id="graph" step="03" title="The syndrome becomes a graph" wide>
  <div class="prose">
    <p>
      Forget the qubits for a moment and keep only the lit defects. Make each
      defect a <strong>node</strong>. Add one virtual <strong>boundary</strong>
      node at each end of the line. Now draw an <strong>edge</strong> between any
      two nodes: an edge represents the error chain that would connect them -- and
      flipping that chain would <em>remove both defects at once</em>.
    </p>
    <p>
      This is exactly what qliff builds. It propagates every possible single
      fault through the circuit, records which detectors it flips, and keeps every
      mechanism that lights <TeX expr="\le 2" /> detectors as a graph edge (a
      fault lighting just one detector connects it to the boundary). MWPM works
      <em>only</em> on this graphlike structure. Hover an edge to read its chain.
    </p>
  </div>

  <Figure
    wide
    title="Matching graph"
    legend={[
      { color: C.defect, mark: "dot", label: "defect node" },
      { color: C.muted, mark: "box", label: "boundary node (L / R)" },
      { color: C.muted, mark: "dash", label: "candidate edge" },
      { color: C.accent, mark: "line", label: "hovered edge" },
    ]}
    caption="Dashed grey = every candidate edge of the matching graph (defect↔defect and defect↔boundary). Hover to inspect a chain."
  >
    <RepCode
      d={D34}
      errors={errors34}
      defects={defects34}
      candidateEdges={candidateEdges34}
      hoverEdge={hoverEdge34}
      interactive={false}
      height={34}
    />
    <div class="edgelist">
      {#each candidateEdges34 as [a, b] (`${a}-${b}`)}
        <button
          class="chip mono"
          onmouseenter={() => (hoverEdge34 = [a, b])}
          onmouseleave={() => (hoverEdge34 = null)}
          onfocus={() => (hoverEdge34 = [a, b])}
          onblur={() => (hoverEdge34 = null)}
        >
          {nodeKey(a)}-{nodeKey(b)} · {edgeLabel(a, b)}
        </button>
      {/each}
      {#if candidateEdges34.length === 0}
        <span class="tag">no defects -- perfect syndrome</span>
      {/if}
    </div>
    <div class="row">
      <button onclick={reseed34}>new random errors</button>
      <span class="tag mono">{defects34.length} defects · {candidateEdges34.length} candidate edges</span>
    </div>
  </Figure>

  <div class="prose">
    <Callout kind="note" title="Boundary node = 'L' / 'R'">
      A defect near an end is often cheapest to cancel by running a short chain
      off the edge of the line. The boundary node lets a <em>single</em>,
      unpaired defect be matched on its own -- essential when an odd number of
      defects fire.
    </Callout>
  </div>
</Section>

<Section id="weights" step="04" title="Edge weight = log-odds of the chain">
  <p>
    What makes one edge "cheaper" than another? Each edge is a chain of
    independent errors. A chain of length <TeX expr={"\\ell"} /> happens with
    probability <TeX expr={"\\propto p^{\\ell}(1-p)^{\\dots}"} />. To turn a
    <em>product</em> of probabilities into a <em>sum</em> we can minimise, take a
    logarithm. qliff assigns every mechanism the weight
  </p>
  <TeX display expr={"w \\;=\\; \\log\\frac{1-p}{p},"} />
  <p>
    per unit of chain length, straight out of
    <code>DetectorErrorModel.weights()</code>. Minimising the total matched
    weight <TeX expr={"\\sum \\log\\frac{1-p}{p}"} /> is the same as
    <strong>maximising the product of error probabilities</strong> -- i.e. finding
    the most likely error. Slide <TeX expr="p" /> and watch the weight move:
  </p>

  <Figure
    title="Edge weight w(p)"
    legend={[
      { color: C.accent2, mark: "box", label: "w = log((1−p)/p)" },
      { color: C.defect, mark: "dot", label: "defect node" },
      { color: C.muted, mark: "dash", label: "candidate edge" },
    ]}
    caption="Lower physical error rate → higher weight per chain step → the matcher fights harder to use short chains."
  >
    <div class="weights-grid">
      <div class="big mono" style="color:var(--accent2)">
        w = {w34.toFixed(2)}
      </div>
      <div class="ctrl">
        <Slider bind:value={p34} min={0.001} max={0.49} step={0.001} label="physical error p" format={(v) => v.toFixed(3)} />
        <Toggle bind:checked={showWeights34} label="show edge weights on graph" />
      </div>
      <table class="ptable mono">
        <thead><tr><th>p</th><th>w = log((1−p)/p)</th></tr></thead>
        <tbody>
          {#each pTable as pv (pv)}
            <tr class:hl={Math.abs(pv - p34) < 0.02}>
              <td>{pv}</td>
              <td>{edgeWeight(pv).toFixed(2)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    {#if showWeights34}
      <RepCode
        d={D34}
        errors={errors34}
        defects={defects34}
        candidateEdges={candidateEdges34}
        interactive={false}
        height={34}
      />
    {/if}
  </Figure>

  <Callout kind="key" title="Low p costs MORE">
    At <TeX expr="p=0.001" /> a single error carries weight <TeX expr="\approx 6.9" />;
    at <TeX expr="p=0.2" /> only <TeX expr="\approx 1.4" />. The cleaner the
    hardware, the more expensive each extra flip -- so the matcher prefers the
    <em>fewest, shortest</em> chains. At <TeX expr="p=0.5" /> the weight is
    <TeX expr="0" /> and every explanation is equally likely: noise has won.
  </Callout>
</Section>

<Section id="matching" step="05" title="Minimum-weight matching -- beat the optimum" wide>
  <div class="prose">
    <p>
      A <strong>perfect matching</strong> pairs up <em>every</em> defect -- with
      another defect or with a boundary -- so all of them are cancelled. The
      <strong>minimum-weight</strong> perfect matching is the cheapest such
      pairing, and PyMatching v2 (qliff's default) finds it exactly. For the
      small syndromes here we brute-force every pairing.
    </p>
    <p>
      Your turn. Click two nodes (defects or the <code>L</code>/<code>R</code>
      boxes) to pair them. Match them all, then reveal the optimum and see if you
      beat it.
    </p>

    <Worked title="Decode the default syndrome at p = 0.08">
      <p>
        The starting errors are on qubits <TeX expr={String.raw`\{2,6,7\}`} />,
        which fire checks at gaps <TeX expr={String.raw`\{1,2,5,7\}`} /> -- call
        them <TeX expr="g_1,g_2,g_5,g_7" />. Each edge costs
        <TeX expr={String.raw`\ell\cdot w`} />, the chain length times the
        per-step weight.
      </p>
      <ol>
        <li>
          Per-step weight:
          <TeX expr={String.raw`w=\log\frac{1-p}{p}=\log\frac{0.92}{0.08}\approx 2.44`} />.
        </li>
        <li>
          Try matching <strong>A</strong>:
          <TeX expr="g_1\!-\!g_2" /> (<TeX expr={String.raw`\ell=1`} />,
          <TeX expr={String.raw`1\cdot 2.44=2.44`} />) and
          <TeX expr="g_5\!-\!g_7" /> (<TeX expr={String.raw`\ell=2`} />,
          <TeX expr={String.raw`2\cdot 2.44=4.88`} />):
          total <TeX expr={String.raw`2.44+4.88=7.33`} />.
        </li>
        <li>
          Try a crossing matching <strong>C</strong>:
          <TeX expr="g_1\!-\!L" /> (<TeX expr={String.raw`\ell=2`} />, 4.88) +
          <TeX expr="g_2\!-\!g_5" /> (<TeX expr={String.raw`\ell=3`} />, 7.33) +
          <TeX expr="g_7\!-\!R" /> (<TeX expr={String.raw`\ell=1`} />, 2.44):
          total <TeX expr={String.raw`14.65`} /> -- far worse.
        </li>
        <li>
          The long-crossing matching <strong>D</strong>
          (<TeX expr="g_1\!-\!g_5" />, <TeX expr="g_2\!-\!g_7" />) flips chains of
          length 4 and 5: total <TeX expr={String.raw`9.77+12.21=21.98`} />,
          worse still.
        </li>
      </ol>
      {#snippet result()}
        Matching <strong>A</strong> wins with total weight
        <strong>7.33</strong> -- the fewest, shortest chains. Click
        <em>reveal optimum</em> below: it shows the same <strong>7.33</strong>
        and the pairs <TeX expr="g_1\!-\!g_2" />, <TeX expr="g_5\!-\!g_7" />.
      {/snippet}
    </Worked>
  </div>

  <Figure
    wide
    title="Build a matching"
    legend={[
      { color: C.defect, mark: "dot", label: "defect to pair" },
      { color: C.muted, mark: "box", label: "boundary node (L / R)" },
      { color: C.accent2, mark: "line", label: "your pairing" },
      { color: C.ok, mark: "box", label: "optimum correction" },
    ]}
    caption="Click defects / boundary boxes to build your own matching. Cyan arcs = your pairs."
  >
    <RepCode
      d={D5}
      errors={errors5}
      defects={defects5}
      matching={userOverlay}
      interactive={true}
      onClickDefect={pickNode}
      onToggleQubit={(q) => (errors5 = errors5.map((e, i) => (i === q ? !e : e)))}
      height={34}
    />
    <div class="row gap wrap">
      <button onclick={() => pickNode(LEFT)} disabled={userMatchedNodes.has(LEFT)}>pair to L boundary</button>
      <button onclick={() => pickNode(RIGHT)} disabled={userMatchedNodes.has(RIGHT)}>pair to R boundary</button>
      <button onclick={resetUser}>reset matching</button>
      <button onclick={reseed5}>new errors</button>
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
          {revealOpt ? optimal5.weight.toFixed(2) : "•••"}
        </span>
      </div>
      {#if revealOpt && userWeight !== null}
        <div class="verdict mono" class:win={userWeight <= optimal5.weight + 1e-6}>
          {userWeight <= optimal5.weight + 1e-6
            ? "optimal! ✓"
            : `+${(userWeight - optimal5.weight).toFixed(2)} over`}
        </div>
      {/if}
    </div>
    {#if revealOpt}
      <div class="prose-inline">
        <span class="tag">optimum:</span>
        <RepCode
          d={D5}
          errors={errors5}
          defects={defects5}
          matching={optimal5.pairs}
          correction={optimal5.correction}
          interactive={false}
          height={34}
        />
      </div>
    {/if}
  </Figure>
</Section>

<Section id="correction" step="06" title="From matching to correction -- did the qubit survive?">
  <p>
    The matched edges <em>are</em> the correction: flip the chain under each arc
    and every defect disappears. qliff reads this straight off the
    <code>faults_matrix</code> -- each matched mechanism maps to the
    <strong>observable flips</strong> it implies, and <code>decode_batch</code>
    returns those predicted flips. But removing the defects is not the same as
    saving the data.
  </p>
  <p>
    Define the <strong>residual</strong> as real error XOR correction,
  </p>
  <TeX display expr={String.raw`r \;=\; e \oplus \hat{e}, \qquad \text{logical error} \iff r = \bar{X} = (1,1,\dots,1).`} />
  <p>
    Here <TeX expr="e" /> is the true error, <TeX expr={String.raw`\hat{e}`} />
    the correction, and <TeX expr={String.raw`\bar X`} /> the rep-code logical
    operator (flip every qubit). If <TeX expr="r=0" /> the qubit survives. If
    <TeX expr="r" /> forms a chain that <em>wraps the whole line</em> -- connecting
    the two boundaries -- it equals <TeX expr={String.raw`\bar X`} /> and the
    logical bit is silently flipped: a
    <span style="color:var(--bad)">logical error</span>.
  </p>

  <Figure
    title="Correction vs residual"
    legend={[
      { color: C.x, mark: "dot", label: "true X error" },
      { color: C.defect, mark: "dot", label: "lit check (defect)" },
      { color: C.accent2, mark: "line", label: "matched pairing" },
      { color: C.ok, mark: "box", label: "MWPM correction chain" },
    ]}
    caption="Green band = MWPM's correction. Compare it with the true error to read the residual."
  >
    <div class="row gap">
      <button class:active={scen6 === "safe"} onclick={() => setScen6("safe")}>short chain (safe)</button>
      <button class:active={scen6 === "fail"} onclick={() => setScen6("fail")}>past-midpoint chain</button>
    </div>
    <RepCode
      d={D6}
      errors={errors6}
      defects={defects6}
      matching={match6.pairs}
      correction={match6.correction}
      onToggleQubit={toggle6}
      height={48}
    />
    <div class="outcome" class:bad={failed6} class:ok={!failed6}>
      {#if failed6}
        <strong>LOGICAL ERROR.</strong> Correction + error wrap the line -- the
        residual is the logical operator. The matcher chose the cheaper pairing,
        but the true chain was longer than half the code, so it guessed the wrong
        side.
      {:else}
        <strong>Survived.</strong> Residual is trivial: error and correction
        cancel. The logical bit is intact.
      {/if}
    </div>
    <div class="residual mono">
      residual = {residual6.map((b) => (b ? "1" : "0")).join("")}
      {residual6.every((b) => !b) ? "(identity)" : residual6.every((b) => b) ? "(spans line → logical!)" : ""}
    </div>
  </Figure>

  <Callout kind="warn" title="The decoder isn't wrong -- it's unlucky">
    With the past-midpoint chain, the <em>shorter</em> way to cancel the defects
    runs off the opposite end. MWPM faithfully returns the most-likely (shortest)
    explanation; it just isn't the one that happened. No graphlike decoder can do
    better on this single shot.
  </Callout>
</Section>

<Section id="distance" step="07" title="Why it can still fail -- and how distance saves you" wide>
  <div class="prose">
    <p>
      A logical error needs the residual to span the line, which takes a chain
      longer than half the code. So failures require roughly
      <TeX expr="\ge d/2" /> errors, where <TeX expr="d" /> is the
      <strong>distance</strong> (here the number of data qubits). More qubits ⇒ a
      longer wall for noise to climb ⇒ exponentially rarer logical errors, as long
      as <TeX expr="p" /> is below threshold. Concretely the logical error rate
      falls like
    </p>
    <TeX display expr={String.raw`P_L \;\sim\; \binom{d}{\lceil d/2\rceil}\,p^{\,\lceil d/2\rceil}\,(1-p)^{\,\lfloor d/2\rfloor} \;\xrightarrow{p<p_{\mathrm{th}}}\; 0,`} />
    <p>
      where <TeX expr="d" /> is the distance and <TeX expr={String.raw`p_{\mathrm{th}}`} />
      the threshold below which growing <TeX expr="d" /> wins. The estimator below
      is just the Monte-Carlo count <TeX expr={String.raw`P_L \approx \text{fails}/N`} />:
      it samples errors, builds the syndrome, runs the same min-weight matching,
      and checks the residual, over thousands of shots.
    </p>
  </div>

  <Figure
    wide
    title="Logical error rate vs p"
    legend={[
      { color: C.accent2, mark: "line", label: "LER sweep (4k-2.5k shots)" },
      { color: C.accent2, mark: "dot", label: "sampled p point" },
      { color: C.accent, mark: "dash", label: "current p marker" },
      { color: C.line, mark: "line", label: "decade gridline" },
    ]}
    caption="Live logical error rate of the MWPM-decoded repetition code. Raise the distance and watch reliability improve while p stays fixed."
  >
    <div class="dist-grid">
      <div class="ctrl">
        <Slider bind:value={d7} min={3} max={11} step={2} label="code distance d" />
        <Slider bind:value={p7} min={0.01} max={0.4} step={0.005} label="physical error p" format={(v) => v.toFixed(3)} />
        <div class="ler-readout">
          <span class="k">logical error rate</span>
          <span class="v mono" style="color:{ler7 < p7 ? 'var(--ok)' : 'var(--bad)'}">
            {ler7 === 0 ? "< 1/" + SHOTS7 : ler7.toExponential(2)}
          </span>
          <span class="sub mono">
            {ler7 < p7 ? "below physical p -- the code helps" : "above physical p -- past threshold"}
          </span>
        </div>
      </div>

      <svg viewBox="0 0 200 120" class="plot" role="img" aria-label="logical error rate vs p">
        <!-- y gridlines at 1e-1, 1e-2, 1e-3 -->
        {#each [0.1, 0.01, 0.001] as gy (gy)}
          <line x1="22" x2="196" y1={plotY(gy, 100) + 6} y2={plotY(gy, 100) + 6} stroke={withAlpha(C.line, 1)} stroke-width="0.4" />
          <text x="2" y={plotY(gy, 100) + 8} class="axlbl">{gy}</text>
        {/each}
        <!-- p = LER break-even reference (y=x is not log-linear; draw the curve) -->
        <polyline
          points={sweep7.map((s) => `${22 + (s.p / 0.3) * 174},${plotY(s.ler, 100) + 6}`).join(" ")}
          fill="none"
          stroke={C.accent2}
          stroke-width="1.4"
        />
        {#each sweep7 as s (s.p)}
          <circle cx={22 + (s.p / 0.3) * 174} cy={plotY(s.ler, 100) + 6} r="1.6" fill={C.accent2} />
        {/each}
        <!-- marker at current p -->
        <line
          x1={22 + (Math.min(p7, 0.3) / 0.3) * 174}
          x2={22 + (Math.min(p7, 0.3) / 0.3) * 174}
          y1="6" y2="106"
          stroke={withAlpha(C.accent, 0.6)}
          stroke-width="0.6"
          stroke-dasharray="2 2"
        />
        <text x="100" y="118" class="axlbl" text-anchor="middle">physical error p →</text>
      </svg>
    </div>
  </Figure>

  <div class="prose">
    <Callout kind="key" title="When two matchings tie, it's a coin flip">
      Exactly at the half-way chain, the two cheapest matchings differ by a
      logical and have <em>equal</em> weight. MWPM must break the tie blindly, so
      it's right half the time -- the irreducible failure floor. Pushing
      <TeX expr="d" /> up moves that knife-edge further away.
    </Callout>

    <p>
      MWPM is fast, optimal for graphlike codes, and the qliff default. But it
      assumes every error lights <TeX expr="\le 2" /> detectors. Codes whose
      faults light three or more checks -- colour codes, many LDPC codes -- break
      that assumption. For those we hand the same graph to
      <strong>belief propagation</strong>, the next decoder, which reasons over
      probabilities instead of pairings.
    </p>
  </div>

  <Figure
    wide
    title="Search replay"
    legend={[
      { color: C.muted, mark: "dash", label: "candidate edge" },
      { color: C.accent2, mark: "line", label: "chosen optimal pair" },
      { color: C.ok, mark: "box", label: "correction (final frame)" },
    ]}
    caption="Optional: step through the brute-force search revealing the optimal pairs one at a time on the graph from step 3/4."
  >
    <RepCode
      d={D34}
      errors={errors34}
      defects={defects34}
      candidateEdges={candidateEdges34}
      matching={shownPairs34}
      correction={frame34 >= optSearchPairs.length ? minWeightMatching(defects34, D34, p34).correction : null}
      interactive={false}
      height={34}
    />
    <Scrubber bind:value={frame34} min={0} max={Math.max(1, optSearchPairs.length)} label="pair" />
  </Figure>
</Section>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 12px;
    flex-wrap: wrap;
  }

  .row.gap {
    gap: 10px;
  }

  .wrap {
    flex-wrap: wrap;
  }

  button.active {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-soft);
  }

  .tag {
    font-size: 12px;
    color: var(--muted);
  }

  .tag.mono,
  .mono {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }

  .edgelist {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 12px 0 4px;
    max-height: 132px;
    overflow-y: auto;
  }

  .chip {
    font-size: 11.5px;
    padding: 4px 8px;
    line-height: 1.1;
  }

  .weights-grid {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 18px;
    align-items: center;
    margin-bottom: 8px;
  }

  .weights-grid .big {
    font-size: 30px;
    font-weight: 700;
  }

  .ctrl {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 180px;
  }

  .ptable {
    font-size: 12px;
    border-collapse: collapse;
  }

  .ptable th,
  .ptable td {
    padding: 2px 10px;
    text-align: right;
    border-bottom: 1px solid var(--line);
  }

  .ptable th {
    color: var(--muted);
    font-weight: 600;
  }

  .ptable tr.hl td {
    color: var(--accent-2);
    background: color-mix(in srgb, var(--accent-2) 10%, transparent);
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

  .outcome {
    margin-top: 14px;
    padding: 12px 14px;
    border-radius: var(--r-md);
    border: 1px solid var(--line);
    border-left-width: 3px;
    font-size: 14.5px;
    line-height: 1.55;
  }

  .outcome.ok {
    border-left-color: var(--ok);
    background: color-mix(in srgb, var(--ok) 8%, transparent);
  }

  .outcome.bad {
    border-left-color: var(--bad);
    background: color-mix(in srgb, var(--bad) 8%, transparent);
  }

  .residual {
    margin-top: 10px;
    font-size: 12.5px;
    color: var(--muted);
  }

  .dist-grid {
    display: grid;
    grid-template-columns: minmax(220px, 320px) 1fr;
    gap: 24px;
    align-items: center;
  }

  .ler-readout {
    display: flex;
    flex-direction: column;
    gap: 3px;
    margin-top: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--line);
  }

  .ler-readout .k {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .ler-readout .v {
    font-size: 26px;
    font-weight: 700;
  }

  .ler-readout .sub {
    font-size: 11.5px;
    color: var(--faint);
  }

  .plot {
    width: 100%;
    height: auto;
    max-height: 300px;
    display: block;
  }

  .axlbl {
    font-size: 5px;
    fill: var(--muted);
    font-family: ui-monospace, monospace;
  }

  @media (max-width: 720px) {
    .weights-grid,
    .dist-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
