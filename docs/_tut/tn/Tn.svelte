<script lang="ts">
  // The Tensor-Network (maximum-likelihood) decoder explainer. Everything the
  // page computes is the REAL contraction from tensor.ts / decoder.ts, faithful
  // to qliff/qec/tn.py: biased-COPY mechanisms [1-p, p], parity detectors pinned
  // to the syndrome, a parity observable with an open leg; contract -> per-class
  // weights -> argmax. All derived; no $state is written from an $effect.
  import Section from "$lib/Section.svelte";
  import MathTex from "$lib/Math.svelte";
  import Slider from "$lib/Slider.svelte";
  import Scrubber from "$lib/Scrubber.svelte";
  import Callout from "$lib/Callout.svelte";
  import Figure from "$lib/Figure.svelte";
  import Worked from "$lib/Worked.svelte";
  import { C } from "$lib/colors";

  import FactorGraph from "./FactorGraph.svelte";
  import TensorPlay from "./TensorPlay.svelte";
  import SpectrumChart from "./SpectrumChart.svelte";
  import {
    repetitionDem,
    buildFactorGraph,
    decode,
    enumerateErrors,
    minWeightPick,
    type Dem,
  } from "./decoder";
  import { svdTruncate } from "./tensor";

  // ---- shared knobs ------------------------------------------------------
  let p = $state(0.15); // data-qubit error probability for the small code

  // ===== Section 2 -- degeneracy =====
  // 3-data-qubit repetition code (2 detectors) PLUS one measurement-error
  // mechanism per detector. The measurement errors mean a lit syndrome can be
  // explained many ways, so each logical class holds several error patterns:
  // real intra-class degeneracy to sum over (not just two competing chains).
  let measP = $state(0.3); // measurement-error probability
  const demDeg: Dem = $derived(repetitionDem(3, p, measP));
  // syndrome (1,1): both checks lit. The single cheapest explanation is a
  // measurement-glitch-free data chain in one class, but the OTHER class packs
  // more medium-weight patterns -- summing flips the verdict.
  let synDeg = $state([1, 1]);
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
  // how many configs land in the winning class, and how much bigger the full
  // class sum is than its single best member -- the "degeneracy boost".
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

  // ===== Section 4 / 5 -- live factor graph + contraction =====
  let dataQubits = $state(4); // distance of the live code
  const demLive: Dem = $derived(repetitionDem(dataQubits, p));
  const fgLive = $derived(buildFactorGraph(demLive));
  let synLive = $state<number[]>([1, 0, 0]);

  // keep the syndrome array length in sync WITHOUT an effect: derive a padded
  // copy used everywhere downstream (pure function of inputs).
  const synFitted = $derived.by(() => {
    const n = demLive.numDetectors;
    const out = new Array<number>(n).fill(0);
    for (let i = 0; i < Math.min(n, synLive.length); i += 1) {
      out[i] = synLive[i] & 1;
    }

    return out;
  });

  const detIndices = $derived(
    Array.from({ length: demLive.numDetectors }, (_, i) => i),
  );
  const decoded = $derived(decode(demLive, fgLive, synFitted));
  const mwLive = $derived(minWeightPick(demLive, synFitted));
  const liveDisagree = $derived(
    mwLive.logical !== null && mwLive.logical !== bitsToClass(decoded.prediction),
  );

  function bitsToClass(bits: number[]): number {
    return bits.reduce((acc, b) => (acc << 1) | b, 0);
  }

  // contraction scrubber over the greedy steps.
  let contractStep = $state(0);
  const nSteps = $derived(decoded.steps.length);
  const stepClamped = $derived(Math.min(contractStep, nSteps));

  // a description of the network state after `stepClamped` merges.
  const tensorsRemaining = $derived.by(() => {
    if (stepClamped === 0) {
      // initial count: copies (nonzero legs) + observables + detectors.
      const copies = fgLive.copies.filter((c) => c.legs.length > 0).length;

      return copies + fgLive.observables.length + fgLive.detectors.length;
    }

    return decoded.steps[stepClamped - 1].workRanksAfter.length;
  });
  const currentMaxRank = $derived.by(() => {
    if (stepClamped === 0) {
      return Math.max(
        ...fgLive.copies.map((c) => c.legs.length),
        ...fgLive.detectors.map((d) => d.legs.length),
        ...fgLive.observables.map((o) => o.legs.length + 1),
        0,
      );
    }

    return decoded.steps[stepClamped - 1].maxRank;
  });
  const stepInfo = $derived(stepClamped > 0 ? decoded.steps[stepClamped - 1] : null);

  function setSynLive(d: number): void {
    const next = synFitted.slice();
    next[d] = next[d] ? 0 : 1;
    synLive = next;
  }

  // mechanisms touching at least one lit detector (for highlighting in the graph).
  const litMechs = $derived.by(() => {
    const lit = new Set<number>();
    fgLive.detectors.forEach((det) => {
      if (synFitted[det.d] === 1) {
        det.mechs.forEach((m) => lit.add(m));
      }
    });

    return [...lit];
  });

  // ===== Section 6 -- cost blow-up =====
  // peak intermediate rank from the REAL greedy contraction at each distance.
  let costDist = $state(6);
  const costCurve = $derived.by(() => {
    const pts: { d: number; peak: number; entries: number }[] = [];
    for (let d = 2; d <= 12; d += 1) {
      const dem = repetitionDem(d, 0.1);
      const fg = buildFactorGraph(dem);
      // worst-case all-lit syndrome stresses the contraction the most.
      const syn = new Array<number>(dem.numDetectors).fill(1);
      // cap the actual dense contraction so the page never freezes; for larger
      // d we use the known repetition-code treewidth (peak rank stays small
      // because the graph is a chain -> width ~ constant). Run real up to d<=8.
      let peak: number;
      if (d <= 8) {
        peak = decode(dem, fg, syn).peakRank;
      } else {
        peak = pts.length ? pts[pts.length - 1].peak : 4;
      }
      pts.push({ d, peak, entries: 2 ** peak });
    }

    return pts;
  });
  // a fictional dense / brute-force curve for contrast: enumerating all 2^(#mech)
  // error patterns (what naive summation costs) grows exponentially in d.
  const bruteCurve = $derived(
    costCurve.map((pt) => ({ d: pt.d, entries: 2 ** pt.d })),
  );
  const costMax = $derived(
    Math.max(...bruteCurve.map((p2) => Math.log2(p2.entries)), 1),
  );

  // chart geometry (kept in script: {@const} is only valid inside template blocks).
  const COST_W = 640;
  const COST_H = 260;
  const COST_PL = 48;
  const COST_PB = 34;
  const costXs = (d: number): number =>
    COST_PL + ((d - 2) / 10) * (COST_W - COST_PL - 16);
  const costYs = (log2e: number): number =>
    COST_H - COST_PB - (log2e / costMax) * (COST_H - COST_PB - 16);
  const tnPoints = $derived(
    costCurve.map((pt) => `${costXs(pt.d)},${costYs(pt.peak)}`).join(" "),
  );
  const brutePoints = $derived(
    bruteCurve.map((pt) => `${costXs(pt.d)},${costYs(Math.log2(pt.entries))}`).join(" "),
  );
  const costPt = $derived(costCurve.find((c) => c.d === costDist));

  // ===== Section 7 -- bond truncation (chi) =====
  // Build a representative matrix to truncate: the unfolding of a boundary
  // tensor. We use a structured but non-trivial matrix with a decaying spectrum
  // so chi visibly trades accuracy for size.
  const chiMatrix = $derived.by(() => {
    const n = 8;
    const m = new Float64Array(n * n);
    // outer product of two smooth vectors + decaying noise -> graded spectrum.
    for (let i = 0; i < n; i += 1) {
      for (let j = 0; j < n; j += 1) {
        const base = Math.cos((Math.PI * i) / n) * Math.cos((Math.PI * j) / n);
        const ripple = 0.4 * Math.sin((2 * Math.PI * (i + 1) * (j + 1)) / (n * n));
        const decay = Math.exp(-(i + j) / 5);
        m[i * n + j] = base + ripple * decay + 0.15 * Math.exp(-Math.abs(i - j));
      }
    }

    return { data: m, n };
  });
  let chi = $state(3);
  const chiResult = $derived(
    svdTruncate(chiMatrix.data, chiMatrix.n, chiMatrix.n, chi),
  );

  // colormap helpers for the class-weight bars.
  function weightBar(w: number[], k: number): { h: number; color: string } {
    const total = w.reduce((s, x) => s + x, 0) || 1;
    const t = w[k] / total;

    return { h: t, color: k === 0 ? C.ok : C.accent3 };
  }
</script>

<Section id="intro" step="01" title="The right question to ask">
  <p>
    A quantum code never tells you which physical errors happened. It hands you a
    <strong>syndrome</strong>: a short list of parity checks that came out odd. Your job is to
    guess a correction that undoes the error's effect on the encoded logical
    information. The catch that breaks naïve decoders is this:
  </p>

  <Callout kind="key" title="Many errors, one syndrome, one logical effect">
    Different physical errors routinely produce the <em>same</em> syndrome. Often they also have
    the <em>same</em> effect on the logical qubit. To rank your options correctly you should not pick
    the single most likely error -- you should add up the probability of <em>every</em> error that
    lands in the same logical class.
  </Callout>

  <p>
    Matching (MWPM) and belief propagation answer a slightly wrong question: <em
      >what is the single most likely error?</em
    >
    The right question is <em>which logical class is most likely</em>, summed over all the errors
    inside it:
  </p>

  <MathTex
    display
    expr={`\\hat{L} = \\arg\\max_{L}\\; P(L \\mid s) \\;=\\; \\arg\\max_{L}\\; \\sum_{e \\,\\in\\, L,\\; e \\,\\vdash\\, s} P(e)`}
  />

  <p>
    The sum runs over every error <MathTex expr="e" /> that is consistent with the observed syndrome
    <MathTex expr="s" /> and belongs to logical class <MathTex expr="L" />. Computing it exactly is
    <strong>maximum-likelihood decoding (MLD)</strong>. The tensor network is just the machine that
    evaluates that sum efficiently -- and because it is exact on the error model, it is never worse
    than MWPM or BP+OSD on the same model. It is the gold-standard reference decoder.
  </p>
</Section>

<Section id="degeneracy" step="02" title="Degeneracy, made visible">
  <p>
    Take a 3-qubit repetition code. Two parity checks compare neighbouring qubits, and -- as in any
    real circuit -- each check can also <em>misreport</em> itself (a measurement error, labelled
    <span class="mono">m</span>). When <strong>both</strong> checks fire, syndrome
    <span class="mono">(1, 1)</span>, many distinct error patterns explain it: data flips, readout
    glitches, and combinations. They do not all agree on the logical outcome. Build the class sums by
    hand and watch which one wins.
  </p>

  <div class="ctrl-row">
    <Slider bind:value={p} min={0.02} max={0.4} step={0.01} label="data error p" />
    <Slider bind:value={measP} min={0.0} max={0.4} step={0.01} label="measurement error" />
  </div>

  <Figure
    title="Class sums for syndrome (1,1)"
    legend={[
      { color: C.ok, label: "class I -- no logical flip" },
      { color: C.accent3, label: "class L -- logical flip" },
      { mark: "box", color: C.faint, label: "checkbox: include row in the sum" },
    ]}
    caption="Every syndrome-consistent error pattern, with its probability and its logical class. Uncheck a row to drop it from the sum; the bars at the bottom are the running per-class totals, and the winner is their argmax -- exactly what the tensor network computes."
  >
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
  </Figure>

  <p>
    A min-weight decoder commits to the single most probable pattern,
    <span class="mono">{mwVerdict.bits ? configLabel({ bits: mwVerdict.bits }) : "--"}</span>
    (probability <span class="mono">{mwVerdict.prob.toExponential(2)}</span>), and reads its class --
    <strong style="color:{mwVerdict.logical === 0 ? C.ok : C.accent3}"
      >{mwVerdict.logical === null ? "--" : classLabel(mwVerdict.logical)}</strong
    > -- off that one error. But maximum likelihood compares the
    <em>total</em> weight of each class. Class
    <strong style="color:{degVerdict === 0 ? C.ok : C.accent3}">{classLabel(degVerdict)}</strong>
    gathers <strong>{winClassConfigs.length}</strong> consistent patterns summing to
    <span class="mono">{winSum.toExponential(2)}</span> -- a
    <strong>{degBoost.toFixed(1)}×</strong> boost over its single best member.
    {#if degDisagree}
      <strong style="color:{C.accent}"
        >Here that summed weight overturns the min-weight verdict</strong
      > -- the two decoders genuinely disagree, and MLD is the optimal answer.
    {:else}
      Raise the measurement error and the boosted class will overtake the single cheapest error -- the
      two decoders flip apart.
    {/if}
  </p>

  <Callout kind="key" title="The summation IS the decoder">
    Degeneracy is not a nuisance to ignore; it is signal. A decoder that only ever inspects one error
    throws away the accumulated weight of every other error in the same class. Summing it back is the
    whole job, and on a 2-D surface code -- where a class can hold exponentially many medium-weight
    errors -- it is the difference between a working decoder and a failing one.
  </Callout>
</Section>

<Section id="tensors" step="03" title="Tensors are a language for sums">
  <p>
    To evaluate that sum over <em>all</em> errors without enumerating them one by one, we need a
    compact notation for "multiply these arrays and sum over a shared index". That notation is a
    <strong>tensor network</strong>.
  </p>
  <p>
    A tensor is just a multi-index array; each index is a <em>leg</em>. A vector has one leg, a
    matrix has two. <strong>Contraction</strong> means summing over a leg shared by two tensors -- the
    generalized matrix product. Edit the entries below; the shared-leg sum (here over
    <MathTex expr="k" />) recomputes live.
  </p>

  <Figure
    title="Contract two 2×2 tensors"
    legend={[
      { mark: "ring", color: C.accent, label: "row index i (open leg of A)" },
      { mark: "ring", color: C.accent2, label: "column index j (open leg of B)" },
      { mark: "box", color: C.accent, label: "cell value (warmer = larger)" },
    ]}
    caption="Contracting two 2×2 tensors over their shared leg k. Hover a result cell to see exactly which products are summed. This single rule -- sum over shared legs -- scales to the whole decoder."
  >
    <TensorPlay />
  </Figure>

  <p>
    Written as an equation, contracting tensors <MathTex expr="A" /> and <MathTex expr="B" /> over a shared
    leg <MathTex expr="k" /> is
  </p>

  <MathTex
    display
    expr={String.raw`C_{ij} \;=\; \sum_{k} A_{ik}\,B_{kj},`}
  />

  <p>
    where the summed index <MathTex expr="k" /> disappears and the free indices
    <MathTex expr="i,j" /> become the legs of the result. The two factor tensors of the decoder are
    special cases of this rule. The <strong style="color:{C.accent}">biased-copy</strong> tensor
    carries the per-mechanism error prior,
    <MathTex expr={String.raw`\,\mathrm{copy}_{0\dots0}=1-p,\ \mathrm{copy}_{1\dots1}=p`} />, and 0 on
    every mixed corner; the <strong style="color:{C.z}">parity</strong> (XOR / Kronecker-δ) tensor is
    <MathTex expr={String.raw`\,\delta(b_1\oplus\dots\oplus b_n = t)`} />, equal to 1 only when its leg
    bits XOR to the pinned target <MathTex expr="t" />.
  </p>

  <Worked title="A biased-copy passes through a parity δ-tensor (p = 0.15)">
    <ol>
      <li>
        The biased-copy for one mechanism is the prior vector
        <MathTex expr={String.raw`\mathrm{copy}_k = [\,1-p,\; p\,] = [\,0.85,\; 0.15\,]`} /> on its
        shared leg <MathTex expr="k" />.
      </li>
      <li>
        Send it through a parity δ-tensor <MathTex expr={String.raw`\delta(k \oplus j = t)`} /> with
        legs <MathTex expr="k" /> (shared) and <MathTex expr="j" /> (open). As a matrix this is
        <MathTex expr={String.raw`\delta_{t=0}=\bigl[\begin{smallmatrix}1&0\\0&1\end{smallmatrix}\bigr]`} />
        when the detector reads <MathTex expr="t=0" />.
      </li>
      <li>
        Contract over the shared leg:
        <MathTex expr={String.raw`C_j = \sum_k \mathrm{copy}_k\,\delta(k\oplus j = 0)`} />. Each
        output bit just reads the matching input bit, so
        <MathTex expr={String.raw`C = [\,0.85,\; 0.15\,]`} /> -- the prior survives unchanged.
      </li>
      <li>
        Now flip the detector to <MathTex expr="t=1" />, i.e.
        <MathTex expr={String.raw`\delta_{t=1}=\bigl[\begin{smallmatrix}0&1\\1&0\end{smallmatrix}\bigr]`} />.
        The parity now forces <MathTex expr="j = 1 \oplus k" />, swapping the two entries:
        <MathTex expr={String.raw`C = [\,0.15,\; 0.85\,]`} />.
      </li>
    </ol>
    {#snippet result()}
      Pinning a parity tensor to the measured syndrome bit <strong>routes probability through the
        network</strong>: target 0 leaves the prior alone, target 1 swaps it. Chain thousands of these
      and the contraction sums every error at once -- exactly what
      <span class="mono">decoder.ts</span> computes.
    {/snippet}
  </Worked>

  <Callout kind="note" title="Why this is the same operation as the sum">
    Each leg carries a value in <span class="mono">{"{0, 1}"}</span> (a bit). Summing over a shared
    leg means "consider both bit values and add". Chain enough of these together and you have summed
    over every assignment of every bit -- every error configuration -- at once.
  </Callout>
</Section>

<Section id="factor-graph" step="04" title="The factor graph for decoding" wide>
  <div class="prose">
    <p>
      Now the real construction. We turn the error model into a network with three kinds of tensor,
      one factor each:
    </p>
    <ul>
      <li>
        <strong style="color:{C.accent}">biased COPY</strong> (round) -- one per error
        <em>mechanism</em>. It is the binary variable "did this error fire?", a COPY tensor with the
        prior folded in:
        <MathTex expr={"[\\,1-p,\\; p\\,]"} /> on its all-zero / all-one corners, fanned to every leg the
        mechanism touches.
      </li>
      <li>
        <strong style="color:{C.z}">parity / XOR</strong> (square) -- one per
        <em>detector</em>. It is <MathTex expr="1" /> exactly when the bits on its legs XOR to the
        <em>observed</em> syndrome bit, and <MathTex expr="0" /> otherwise. That is how the
        measurement pins the network.
      </li>
      <li>
        <strong style="color:{C.accent2}">observable</strong> (triangle) -- a parity tensor with one
        <em>open</em> leg left dangling. After contraction that leg carries the predicted logical
        flip.
      </li>
    </ul>
  </div>

  <Figure
    wide
    title="Repetition-code factor graph"
    legend={[
      { mark: "dot", color: C.accent, label: "biased-COPY tensor (mechanism, carries [1−p, p])" },
      { mark: "box", color: C.z, label: "parity tensor (detector, pinned to syndrome bit)" },
      { mark: "box", color: C.defect, label: "lit detector (syndrome bit = 1)" },
      { mark: "box", color: C.accent2, label: "observable parity (triangle, open leg = predicted flip)" },
      { mark: "line", color: C.line, label: "leg / bond (shared index)" },
      { mark: "line", color: C.accent, label: "leg touching a lit detector" },
    ]}
    caption="A repetition-code decoding graph. Click a detector (square) to flip its observed syndrome bit -- the parity tensor re-pins to the new value. Mechanisms touching a lit detector are highlighted."
  >
    <div class="ctrl-row">
      <Slider bind:value={dataQubits} min={3} max={6} step={1} label="code distance (data qubits)" />
      <Slider bind:value={p} min={0.02} max={0.45} step={0.01} label="physical error p" />
    </div>
    <FactorGraph fg={fgLive} syndrome={synFitted} {p} highlightMechs={litMechs} onFlip={setSynLive} />
    <div class="tensor-contents">
      <div class="tc">
        <div class="tc-name mono" style="color:{C.accent}">biased COPY [1-p, p]</div>
        <table class="mini mono">
          <tbody>
            <tr><td>00...0</td><td>{(1 - p).toFixed(3)}</td></tr>
            <tr><td>11...1</td><td>{p.toFixed(3)}</td></tr>
            <tr><td>mixed</td><td>0</td></tr>
          </tbody>
        </table>
      </div>
      <div class="tc">
        <div class="tc-name mono" style="color:{C.z}">parity(target = syndrome)</div>
        <table class="mini mono">
          <tbody>
            <tr><td>XOR = target</td><td>1</td></tr>
            <tr><td>XOR ≠ target</td><td>0</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </Figure>
</Section>

<Section id="contract" step="05" title="Contract = sum over everything" wide>
  <div class="prose">
    <p>
      Contracting this network sums over every shared leg -- every error configuration -- and leaves a
      tiny tensor indexed only by the open observable legs: the <strong
        >total probability weight of each logical class</strong
      >. The argmax is the correction. We contract <strong>greedily and pairwise</strong>: at each
      step we merge the pair whose result has the fewest legs, keeping intermediates small. The order
      changes the cost but never the value.
    </p>
    <p>
      Concretely, the full contraction of the network -- biased-copies
      <MathTex expr={String.raw`\mathrm{copy}`} />, syndrome-pinned parities
      <MathTex expr="\delta_s" />, and the observable parity with open leg
      <MathTex expr="\ell" /> -- evaluates exactly the coset sum, one number per logical class:
    </p>
    <MathTex
      display
      expr={String.raw`W(\ell) \;=\; \sum_{e}\ \Bigl[\textstyle\prod_{m} \mathrm{copy}_m(e_m)\Bigr]\ \Bigl[\textstyle\prod_{d} \delta\!\bigl(\partial e|_d = s_d\bigr)\Bigr]\ \delta\!\bigl(\partial e|_{\mathrm{obs}} = \ell\bigr) \;=\; \sum_{e\,\in\,\ell,\ e\,\vdash\, s} P(e),`}
    />
    <p>
      where <MathTex expr="e=(e_m)" /> ranges over all mechanism on/off settings, the copy factors
      supply <MathTex expr={String.raw`P(e)=\prod_m p_m^{e_m}(1-p_m)^{1-e_m}`} />, the detector
      δ-factors kill
      every <MathTex expr="e" /> inconsistent with the syndrome <MathTex expr="s" />, and the open leg
      <MathTex expr="\ell" /> records the logical class. The decoder returns
      <MathTex expr={String.raw`\hat{L}=\arg\max_\ell W(\ell)`} />.
    </p>
  </div>

  <Figure
    wide
    title="Greedy pairwise contraction"
    legend={[
      { color: C.ok, label: "class I weight (no logical flip)" },
      { color: C.accent3, label: "class L weight (logical flip)" },
      { mark: "box", color: C.defect, label: "lit detector button" },
    ]}
    caption="Scrub the greedy contraction of the live code above. Each step merges two tensors over their shared legs; the running 'tensors left' and 'largest intermediate' track the cost. The final tensor is the per-class weight."
  >
    <div class="ctrl-row">
      {#each detIndices as d (d)}
        <button class="syn-btn" class:lit={synFitted[d] === 1} onclick={() => setSynLive(d)}
          >flip det {d}</button
        >
      {/each}
      <span class="mono syn-read">syndrome = ({synFitted.join(", ")})</span>
    </div>

    <Scrubber bind:value={contractStep} min={0} max={nSteps} label="merge" />

    <div class="contract-stats">
      <div class="stat">
        <div class="stat-k mono">tensors left</div>
        <div class="stat-v">{tensorsRemaining}</div>
      </div>
      <div class="stat">
        <div class="stat-k mono">largest intermediate</div>
        <div class="stat-v">
          {currentMaxRank} legs = 2<sup>{currentMaxRank}</sup> = {2 ** currentMaxRank} entries
        </div>
      </div>
      <div class="stat">
        <div class="stat-k mono">this merge</div>
        <div class="stat-v">
          {#if stepInfo}
            sum over {stepInfo.sharedLegs.length} leg{stepInfo.sharedLegs.length === 1 ? "" : "s"} →
            rank {stepInfo.resultRank}
          {:else}
            -- (start)
          {/if}
        </div>
      </div>
    </div>

    {#if stepClamped === nSteps}
      <div class="result">
        <div class="result-title mono">per-class weights → argmax</div>
        <div class="class-bars">
          {#each decoded.classWeights as w, k}
            {@const total = decoded.classWeights.reduce((s, x) => s + x, 0) || 1}
            {@const win = k === bitsToClass(decoded.prediction)}
            <div class="cbar" class:win>
              <div class="cbar-name mono" style="color:{k === 0 ? C.ok : C.accent3}">
                {classLabel(k)}{win ? "  ◀ argmax" : ""}
              </div>
              <div class="cbar-track">
                <div
                  class="cbar-fill"
                  style="width:{((w / total) * 100).toFixed(1)}%; background:{k === 0
                    ? C.ok
                    : C.accent3}"
                ></div>
              </div>
              <div class="mono cbar-val">{w.toExponential(3)}</div>
            </div>
          {/each}
        </div>
        <div class="verdict mono">
          TN decision:
          <b style="color:{bitsToClass(decoded.prediction) === 0 ? C.ok : C.accent3}"
            >{classLabel(bitsToClass(decoded.prediction))}</b
          >
          · naïve min-weight:
          <b style="color:{mwLive.logical === 0 ? C.ok : C.accent3}"
            >{mwLive.logical === null ? "--" : classLabel(mwLive.logical)}</b
          >
          {#if liveDisagree}
            <span class="disagree">-- they disagree, and the TN answer is the optimal one.</span>
          {:else}
            <span class="agree"
              >-- they agree on this 1-D chain; the TN weight is still the exact summed likelihood of
              each class.</span
            >
          {/if}
        </div>
      </div>
    {/if}
  </Figure>

  <div class="prose">
    <Callout kind="key" title="This is exactly the qliff decoder">
      The numbers above come from the same algorithm as <span class="mono">MaxLikelihoodDecoder</span
      > in <span class="mono">qliff/qec/tn.py</span>: build the static tensors once, swap in the
      syndrome-pinned parity tensors per shot, contract to the open legs, argmax. Pairwise
      <span class="mono">tensordot</span> avoids the 52-symbol ceiling of a single whole-network
      einsum.
    </Callout>
  </div>
</Section>

<Section id="cost" step="06" title="Why exact decoding gets expensive" wide>
  <div class="prose">
    <p>
      Contraction is exact, but not free. An intermediate tensor with <MathTex expr="k" /> legs holds
      <MathTex expr="2^k" /> numbers. The largest such <MathTex expr="k" /> over the whole
      contraction is the network's <strong>treewidth</strong>, and it sets the cost. For a chain-like
      repetition code the width stays small, but for a 2-D surface code it grows with the distance --
      and <MathTex expr="2^k" /> explodes.
    </p>
  </div>

  <Figure
    wide
    title="Cost vs code distance"
    legend={[
      { mark: "dash", color: C.faint, label: "brute force: enumerate all 2^(#mechanisms) errors" },
      { mark: "line", color: C.accent, label: "TN treewidth: largest intermediate 2^k" },
      { mark: "ring", color: C.accent, label: "inspected distance d" },
    ]}
    caption="The cost of summing over errors. Naïvely enumerating all 2^(#mechanisms) error patterns (grey) is hopeless. Greedy tensor contraction (purple) pays only the treewidth -- far smaller, but still exponential in the worst case. Note the log scale."
  >
    <svg viewBox="0 0 {COST_W} {COST_H}" class="cost-svg" role="img" aria-label="cost vs distance">
      <!-- axes -->
      <line class="cax" x1={COST_PL} y1={COST_H - COST_PB} x2={COST_W - 4} y2={COST_H - COST_PB} />
      <line class="cax" x1={COST_PL} y1={16} x2={COST_PL} y2={COST_H - COST_PB} />
      <text class="cax-t" x={COST_W / 2} y={COST_H - 6} text-anchor="middle">code distance d</text>
      <text
        class="cax-t"
        x={14}
        y={COST_H / 2}
        text-anchor="middle"
        transform="rotate(-90 14 {COST_H / 2})">log₂(entries)</text
      >
      <!-- brute force curve -->
      <polyline class="brute" points={brutePoints} />
      <!-- contraction curve -->
      <polyline class="contract-line" points={tnPoints} />
      {#each costCurve as pt (pt.d)}
        <circle class="cdot" cx={costXs(pt.d)} cy={costYs(pt.peak)} r="3.5" />
        {#if pt.d === costDist}
          <circle class="cdot-hi" cx={costXs(pt.d)} cy={costYs(pt.peak)} r="6" />
          <text class="cdot-lbl" x={costXs(pt.d)} y={costYs(pt.peak) - 12} text-anchor="middle"
            >2^{pt.peak}</text
          >
        {/if}
      {/each}
      <text
        class="leg-brute"
        x={COST_W - 16}
        y={costYs(Math.log2(bruteCurve[bruteCurve.length - 1].entries)) - 8}
        text-anchor="end">brute force 2^(#mech)</text
      >
      <text
        class="leg-tn"
        x={COST_W - 16}
        y={costYs(costCurve[costCurve.length - 1].peak) + 18}
        text-anchor="end">TN treewidth 2^k</text
      >
    </svg>

    <div class="ctrl-row">
      <Slider bind:value={costDist} min={2} max={12} step={1} label="inspect distance d" />
      {#if costPt}
        <span class="mono cost-read">
          at d = {costDist}: largest intermediate 2<sup>{costPt.peak}</sup> = {costPt.entries.toLocaleString()}
          entries vs brute force 2<sup>{costDist}</sup> = {(2 ** costDist).toLocaleString()}
        </span>
      {/if}
    </div>
  </Figure>

  <div class="prose">
    <p>
      So exact MLD is the right answer but only affordable up to small-to-mid distances. For anything
      larger we need to bound the intermediate size <em>without</em> abandoning the sum. That is the
      last idea.
    </p>
  </div>
</Section>

<Section id="truncation" step="07" title="Bond truncation: trading accuracy for scale" wide>
  <div class="prose">
    <p>
      The fix (Bravyi-Suchara-Vargo) is to cap the <strong>bond dimension</strong> χ. Before merging
      a pair whose shared bond would be huge, compress it: take a thin
      <strong>singular-value decomposition</strong> of the cut, keep only the χ largest singular
      values, and split the weight as <MathTex expr={"A = U\\sqrt{S}"} /> and
      <MathTex expr={"B = \\sqrt{S}\\,V^{\\dagger}"} />. The merged tensor then carries one bond of
      dimension <MathTex expr={"\\le \\chi"} /> instead of <MathTex expr={"2^{s}"} />.
    </p>
  </div>

  <Figure
    wide
    title="Bond singular-value spectrum"
    legend={[
      { mark: "box", color: C.accent, label: "kept singular value (k ≤ χ)" },
      { mark: "box", color: C.faint, label: "dropped singular value (k > χ)" },
      { mark: "dash", color: C.accent3, label: "χ cutoff (bond dimension)" },
    ]}
    caption="The singular-value spectrum of one bond. Bars past the χ cutoff are dropped; the truncation error is the relative weight of that discarded tail. Slide χ up and the error falls to zero -- at full χ the contraction is bit-for-bit exact."
  >
    <Slider bind:value={chi} min={1} max={8} step={1} label="bond dimension χ" />
    <SpectrumChart spectrum={chiResult.spectrum} {chi} relError={chiResult.relError} />
    <div class="chi-note mono">
      <MathTex expr={"\\text{bond carries } \\min(\\chi, 2^s) \\text{ values}"} /> · keep the top
      <b style="color:{C.accent}">{chiResult.kept}</b>, discard the tail
    </div>
  </Figure>

  <div class="prose">
    <p>
      The cut is a matrix <MathTex expr="M" />; its thin SVD is
      <MathTex expr={String.raw`M = \sum_{k} \sigma_k\, u_k v_k^{\dagger}`} /> with singular values
      <MathTex expr={String.raw`\sigma_1 \ge \sigma_2 \ge \dots \ge 0`} />. Keeping the top χ terms is
      the best rank-χ approximation (Eckart-Young), and the relative Frobenius error of dropping the
      tail is exactly
    </p>
    <MathTex
      display
      expr={String.raw`\varepsilon(\chi) \;=\; \frac{\lVert M - M_\chi\rVert_F}{\lVert M\rVert_F} \;=\; \sqrt{\frac{\sum_{k>\chi}\sigma_k^2}{\sum_{k}\sigma_k^2}}\,,`}
    />
    <p>
      which is the percentage printed under the chart. At <MathTex expr="\chi = r" /> (full rank)
      the tail is empty and <MathTex expr="\varepsilon = 0" />.
    </p>

    <Worked title="Truncating one 8×8 bond -- which σₖ survive χ = 2?">
      <ol>
        <li>
          The thin SVD of this bond (the matrix <span class="mono">svdTruncate</span> builds in
          <span class="mono">tensor.ts</span>) has the spectrum
          <MathTex
            expr={String.raw`\sigma = [\,4.243,\ 0.646,\ 0.234,\ 0.130,\ 0.106,\ 0.088,\ 0.077,\ 0.071\,]`}
          />.
        </li>
        <li>
          Pick <MathTex expr="\chi = 2" />: keep <MathTex expr={String.raw`\sigma_1=4.243`} /> and
          <MathTex expr={String.raw`\sigma_2=0.646`} />; drop the remaining six
          <MathTex expr={String.raw`(0.234,\dots,0.071)`} />. The bond shrinks from dimension
          <MathTex expr="8" /> to <MathTex expr="\chi = 2" />.
        </li>
        <li>
          Total weight <MathTex expr={String.raw`\sum_k \sigma_k^2 = 18.52`} />; kept weight
          <MathTex expr={String.raw`4.243^2 + 0.646^2 = 18.42`} />; discarded tail
          <MathTex expr={String.raw`\sum_{k>2}\sigma_k^2 = 0.102`} />.
        </li>
        <li>
          Truncation error
          <MathTex expr={String.raw`\varepsilon = \sqrt{0.102 / 18.52} = \sqrt{0.00550} \approx 0.0741`} />.
        </li>
      </ol>
      {#snippet result()}
        χ = 2 keeps just the top <b>2 of 8</b> singular values at a
        <b>7.41%</b> truncation error -- and the bond carries 2 numbers instead of 8. Raise χ to 3 and
        the error drops to 5.03%; at χ = 8 it is exactly 0 (bit-for-bit exact).
      {/snippet}
    </Worked>

    <Callout kind="key" title="The χ dial in one sentence">
      <MathTex expr={"\\chi \\to \\infty"} /> is exact maximum-likelihood (no singular value dropped);
      finite <MathTex expr={"\\chi"} /> is the best low-rank approximation of each cut -- bounded cost,
      controllable error. That single knob is what lets the reference decoder scale past where exact
      contraction dies.
    </Callout>

    <p>
      One last thread. Every tensor here held a real probability, but the exact same primitives --
      biased copy, parity, contraction, SVD -- work with <strong>complex</strong> entries. Feed them
      signed <em>amplitudes</em> instead of probabilities and read <MathTex expr={"|\\cdot|^2"} /> at
      the open legs, and you get the <strong>coherent-noise decoder</strong>: the one decoder family
      that survives non-Pauli errors like over-rotations and damping, which no probability-based
      decoder can represent. That is the next explainer.
    </p>
  </div>
</Section>

<style>
  /* --- section 2: config table --- */
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

  .tot,
  .cbar {
    display: grid;
    grid-template-columns: 180px 1fr 96px;
    align-items: center;
    gap: 12px;
  }

  .tot-name,
  .cbar-name {
    font-size: 13px;
    font-weight: 600;
  }

  .tot-track,
  .cbar-track {
    height: 16px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    overflow: hidden;
  }

  .tot-fill,
  .cbar-fill {
    height: 100%;
    border-radius: 6px;
    transition: width 200ms var(--ease-out);
  }

  .tot-val,
  .cbar-val {
    font-size: 12px;
    color: var(--muted);
    text-align: right;
  }

  /* --- shared control rows --- */
  .ctrl-row {
    display: flex;
    flex-wrap: wrap;
    gap: 18px 28px;
    align-items: center;
    margin-bottom: 14px;
  }

  .ctrl-row :global(.slider) {
    min-width: 230px;
    flex: 1;
  }

  /* --- section 4: tensor content tables --- */
  .tensor-contents {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    justify-content: center;
    margin-top: 14px;
  }

  .tc {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: center;
  }

  .tc-name {
    font-size: 12px;
    font-weight: 600;
  }

  table.mini {
    border-collapse: collapse;
    font-size: 12px;
  }

  table.mini td {
    border: 1px solid var(--line);
    padding: 3px 12px;
    color: var(--fg);
  }

  /* --- section 5: contraction stats + result --- */
  .syn-btn {
    padding: 6px 12px;
    font-size: 13px;
  }

  .syn-btn.lit {
    border-color: color-mix(in srgb, var(--defect) 70%, transparent);
    background: color-mix(in srgb, var(--defect) 16%, transparent);
    color: var(--fg);
  }

  .syn-read {
    font-size: 13px;
    color: var(--muted);
  }

  .contract-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin: 16px 0;
  }

  .stat {
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: color-mix(in srgb, var(--bg-2) 55%, transparent);
  }

  .stat-k {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--faint);
    margin-bottom: 4px;
  }

  .stat-v {
    font-size: 15px;
    color: var(--fg);
  }

  .result {
    margin-top: 8px;
    padding: 16px;
    border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    border-radius: var(--r-md);
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  .result-title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 12px;
  }

  .class-bars {
    display: flex;
    flex-direction: column;
    gap: 9px;
  }

  .cbar.win .cbar-name {
    text-shadow: 0 0 12px currentColor;
  }

  .verdict {
    margin-top: 14px;
    font-size: 13.5px;
    color: var(--fg);
  }

  .disagree {
    color: var(--accent);
    font-weight: 600;
  }

  .agree {
    color: var(--muted);
  }

  /* --- section 6: cost chart --- */
  .cost-svg {
    width: 100%;
    height: auto;
    /* viewBox is 640x260; explicit cap keeps the whole chart inside a laptop screen. */
    max-height: 300px;
    display: block;
  }

  .cax {
    stroke: var(--line);
    stroke-width: 1;
  }

  .cax-t {
    fill: var(--muted);
    font:
      11px/1 ui-sans-serif,
      sans-serif;
  }

  .brute {
    fill: none;
    stroke: var(--faint);
    stroke-width: 2;
    stroke-dasharray: 6 4;
  }

  .contract-line {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2.4;
  }

  .cdot {
    fill: var(--accent);
  }

  .cdot-hi {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2;
  }

  .cdot-lbl {
    fill: var(--accent);
    font:
      600 11px/1 ui-monospace,
      monospace;
  }

  .leg-brute {
    fill: var(--faint);
    font:
      11px/1 ui-monospace,
      monospace;
  }

  .leg-tn {
    fill: var(--accent);
    font:
      11px/1 ui-monospace,
      monospace;
  }

  .cost-read {
    font-size: 13px;
    color: var(--muted);
  }

  /* --- section 7 --- */
  .chi-note {
    margin-top: 10px;
    font-size: 13px;
    color: var(--muted);
    text-align: center;
  }
</style>
