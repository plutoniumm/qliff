<script lang="ts">
  // Belief Propagation (BP) and BP+OSD, the second decoder in qliff. Intuition
  // first, then the real sum-product math, run live in the browser on small
  // parity-check matrices (see bp.ts). Faithful to qliff's BpOsdDecoder, which
  // hands the DEM check matrix H (detectors x mechanisms) to the `ldpc` library
  // with bp_method="product_sum", osd_method="osd_cs", osd_order=7.
  import Section from "$lib/Section.svelte";
  import MathTex from "$lib/Math.svelte";
  import Slider from "$lib/Slider.svelte";
  import Toggle from "$lib/Toggle.svelte";
  import Scrubber from "$lib/Scrubber.svelte";
  import Callout from "$lib/Callout.svelte";
  import Figure from "$lib/Figure.svelte";
  import Worked from "$lib/Worked.svelte";
  import { C, heat, withAlpha } from "$lib/colors";

  import TannerGraph from "./TannerGraph.svelte";
  import BeliefBars from "./BeliefBars.svelte";
  import {
    repetitionCode,
    degenerateCode,
    STUCK_SYNDROME,
    makeCode,
    runBp,
    runOsd,
    syndromeOf,
    llrFromP,
    type Code,
  } from "./bp";

  // KaTeX strings with braces live here as JS constants: inline in the template
  // Svelte would try to interpolate the {...} groups as expressions.
  const TEX = {
    Hcm: "H_{cm}=1",
    llrDef: "\\ell = \\log\\frac{1-p}{p} = \\log\\frac{P(\\text{no error})}{P(\\text{error})}.",
    posterior: "p = \\tfrac{1}{1+e^{\\ell}}",
    varToCheck: "m_{m\\to c} \\;=\\; \\ell_m \\;+\\!\\!\\sum_{c'\\neq c} m_{c'\\to m}.",
    tanhRule:
      "\\tanh\\frac{m_{c\\to m}}{2} \\;=\\; (-1)^{s_c}\\!\\!\\prod_{m'\\neq m}\\tanh\\frac{m_{m'\\to c}}{2},",
    cToV:
      "m_{c\\to m} \\;=\\; 2\\,\\mathrm{atanh}\\!\\Big[(-1)^{s_c}\\!\\!\\prod_{m'\\neq m}\\tanh\\tfrac{m_{m'\\to c}}{2}\\Big].",
    // Posterior LLR (sum of ALL incoming checks + prior) and the hard decision.
    post:
      "L_m \\;=\\; \\ell_m + \\sum_{c} m_{c\\to m}, \\qquad \\hat e_m = \\begin{cases}1 & L_m < 0\\\\ 0 & L_m \\ge 0\\end{cases}",
    // OSD fallback: solve the most-reliable full-rank core exactly over F2.
    osdSolve: "H_{\\mathcal{P}}\\,\\hat e_{\\mathcal{P}} \\;=\\; s \\pmod 2",
    obs: "\\text{obs} = O\\,\\hat{e} \\bmod 2",
    relAbs: "|L_m|",
    f2: "\\mathbb{F}_2",
  };

  // ----- Section 2: the Tanner graph, interactive syndrome -------------------
  const tannerCode: Code = makeCode(
    [
      [1, 1, 0, 0, 0],
      [0, 1, 1, 1, 0],
      [0, 0, 0, 1, 1],
    ],
    [0.06, 0.06, 0.06, 0.06, 0.06],
  );
  let litChecks = $state<boolean[]>([false, true, false]);
  const tannerSyndrome = $derived(litChecks.map((b) => (b ? 1 : 0)));
  let tannerHover = $state<{ kind: "var" | "check"; idx: number } | null>(null);

  function toggleCheck(c: number): void {
    litChecks = litChecks.map((b, i) => (i === c ? !b : b));
  }

  // ----- Section 3: prior p <-> LLR ------------------------------------------
  let pPrior = $state(0.05);
  const priorLlr = $derived(llrFromP(pPrior));

  // ----- Section 4 & 5: the message-passing dance on a repetition code -------
  const repP = 0.06;
  const repCode = $derived(repetitionCode(7, repP));
  let errBit = $state(3); // which single bit carries the true error
  const repTrueError = $derived(
    Array.from({ length: 7 }, (_, i) => (i === errBit ? 1 : 0)),
  );
  const repSyndrome = $derived(syndromeOf(repCode, repTrueError));
  const repBp = $derived(runBp(repCode, repSyndrome, 12));
  let repIter = $state(0);
  let showMsgs = $state(true);
  const repFrame = $derived(
    repBp.frames[Math.min(repIter, repBp.frames.length - 1)],
  );
  // Decoded vs. true, at the current frame.
  const repCorrect = $derived(
    repFrame.satisfied &&
      repFrame.hard.every((b, i) => b === repTrueError[i]),
  );

  // ----- Section 6: the stuck (degenerate) case ------------------------------
  const stuckCode: Code = degenerateCode(0.08);
  const stuckSyndrome = STUCK_SYNDROME;
  const stuckBp = runBp(stuckCode, stuckSyndrome, 16);
  let stuckIter = $state(0);
  const stuckFrame = $derived(
    stuckBp.frames[Math.min(stuckIter, stuckBp.frames.length - 1)],
  );

  // ----- Section 7: OSD to the rescue ----------------------------------------
  // Feed BP's final (oscillating) posterior into OSD.
  const osd = runOsd(
    stuckCode,
    stuckSyndrome,
    stuckBp.finalPosterior,
    7,
  );
  const osdSyndromeOk = $derived(
    syndromeOf(stuckCode, osd.solution).join("") === stuckSyndrome.join(""),
  );

  // ----- Legends: name every shape / colour each panel uses -------------------
  const tannerLegend = [
    { mark: "ring" as const, color: C.data, label: "variable node = error mechanism (circle)" },
    { mark: "box" as const, color: C.lineStrong, label: "check node = detector (square)" },
    { mark: "box" as const, color: C.defect, label: "lit check (syndrome bit = 1)" },
    { mark: "line" as const, color: C.line, label: "edge: mechanism flips detector" },
  ];
  const danceLegend = [
    { mark: "dot" as const, color: C.accent2, label: "live message (size/heat = |LLR|)" },
    { mark: "ring" as const, color: C.accent3, label: "belief ring = posterior P(error)" },
    { mark: "ring" as const, color: C.accent2, label: "true error mechanism" },
    { mark: "dot" as const, color: C.bad, label: "called an error (hard decision)" },
  ];
  const beliefLegend = [
    { mark: "box" as const, color: C.bad, label: "bar left = error (ℓ < 0)" },
    { mark: "box" as const, color: C.accent, label: "bar right = no error (ℓ > 0)" },
    { mark: "box" as const, color: C.accent2, label: "true mechanism (cyan label)" },
  ];
  const stuckLegend = [
    { mark: "box" as const, color: C.defect, label: "lit check" },
    { mark: "box" as const, color: C.bad, label: "unsatisfied check (residual = 1)" },
    { mark: "ring" as const, color: C.accent3, label: "oscillating belief ring" },
  ];
  const osdLegend = [
    { mark: "box" as const, color: C.accent, label: "pivot column (solved exactly)" },
    { mark: "box" as const, color: C.lineStrong, label: "free column" },
    { mark: "box" as const, color: C.ok, label: "syndrome-matching recovery" },
  ];
</script>

<!-- ===================================================================== -->
<Section id="why" step="01" title="Why another decoder?">
  <p>
    In the previous chapter, <strong>minimum-weight perfect matching</strong> turned a
    syndrome into a graph and paired up the lit detectors. That trick only works when
    every possible error touches <em>at most two</em> detectors -- then each error is an
    <em>edge</em> and decoding is graph matching.
  </p>
  <p>
    But most codes aren't so tidy. A single fault can flip three, four, or a dozen
    parity checks at once. Now an error is no longer an edge: it's a node wired to all
    the checks it disturbs. Matching has nothing to match. We need a decoder that lives
    on the <em>full bipartite graph</em> of errors and checks.
  </p>
  <Callout kind="key" title="The one-line intuition">
    <strong>Belief propagation is neighbours gossiping until they agree.</strong> Every
    possible error and every parity check holds an opinion -- "I probably did/didn't
    fire," "my parity is/ isn't satisfied" -- and they trade these opinions back and forth
    along the edges. After a few rounds, the opinions (hopefully) settle on the single
    most likely error.
  </Callout>
  <p>
    This is exactly what qliff's <code>BpOsdDecoder</code> does. It hands the code's
    check matrix to belief propagation, and -- when BP can't decide -- to a cleanup step
    called <strong>OSD</strong>. By the end of this page you'll have run both, live, on
    a real example where plain matching would be helpless.
  </p>
</Section>

<!-- ===================================================================== -->
<Section id="tanner" step="02" title="The Tanner graph" wide>
  <div class="prose">
    <p>
      Everything BP does happens on one picture: the <strong>Tanner graph</strong> (a
      "factor graph"). It has two kinds of node:
    </p>
    <ul>
      <li>
        <strong style="color:{C.data}">Variables</strong> (circles, top) -- one per
        <em>error mechanism</em>: a possible fault, like "qubit&nbsp;3 picked up an X."
      </li>
      <li>
        <strong style="color:{C.muted}">Checks</strong> (squares, bottom) -- one per
        <em>detector</em>: a parity measurement that lights up if an odd number of its
        neighbouring errors fired.
      </li>
    </ul>
    <p>
      We draw an edge from error <MathTex expr="e_m" /> to detector <MathTex expr="d_c" />
      exactly when <MathTex expr={TEX.Hcm} /> -- i.e. mechanism <MathTex expr="m" /> flips
      detector <MathTex expr="c" />. That matrix <MathTex expr="H" /> is the same one qliff
      builds from the circuit (<code>dem.check_matrix()</code> returns
      <MathTex expr="H" />, the priors, and the observable map).
    </p>
    <p>
      Click a detector to "light" it -- that's a <strong>syndrome</strong>, the only thing
      the decoder actually observes. Hover any node to see who it talks to.
    </p>
  </div>

  <Figure
    wide
    title="Tanner graph"
    legend={tannerLegend}
    caption="A small Tanner graph. Squares are detectors (parity checks); circles are error mechanisms. Click a detector to toggle the syndrome; hover a node to highlight its edges."
  >
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
  </Figure>

  <div class="prose">
    <Callout kind="note" title="Contrast with matching">
      Detector <MathTex expr="d_1" /> here touches <em>three</em> error mechanisms. Matching
      would choke on it. BP doesn't care how many edges a node has -- it just keeps
      gossiping along all of them.
    </Callout>
  </div>
</Section>

<!-- ===================================================================== -->
<Section id="beliefs" step="03" title="Beliefs as log-odds">
  <p>
    Before any gossip, each error mechanism has a <strong>prior</strong>: the channel
    probability <MathTex expr="p" /> that it fired. BP doesn't pass probabilities around
    directly -- it passes their <strong>log-likelihood ratio</strong> (LLR):
  </p>
  <MathTex display expr={TEX.llrDef} />
  <p>
    Why log-odds? Because along the way BP needs to <em>combine independent evidence</em>,
    and in log-space combining evidence is just <strong>addition</strong>. The sign and
    size carry all the meaning:
  </p>
  <ul>
    <li><MathTex expr="\ell \gg 0" /> -- confident there's <strong>no error</strong> (small <MathTex expr="p" />).</li>
    <li><MathTex expr="\ell \approx 0" /> -- a coin flip; the mechanism is undecided.</li>
    <li><MathTex expr="\ell < 0" /> -- the evidence now favours an <strong>error</strong>.</li>
  </ul>

  <Figure
    title="Prior p → LLR"
    legend={[
      { mark: "box", color: C.bad, label: "ℓ < 0: favours error" },
      { mark: "box", color: C.accent2, label: "ℓ > 0: favours no error" },
    ]}
    caption="Drag the prior p. The gauge shows the resulting prior LLR ℓ = log((1−p)/p) in nats -- exactly the number qliff seeds BP with per mechanism."
  >
    <div class="gauge-row">
      <Slider bind:value={pPrior} min={0.001} max={0.5} step={0.001} label="error prior p" />
      <div class="gauge">
        <div class="gauge-num mono" style="color:{priorLlr < 0 ? C.bad : C.fg}">
          ℓ = {priorLlr >= 0 ? "+" : ""}{priorLlr.toFixed(2)}
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
  </Figure>

  <Callout kind="key" title="Posterior, the other direction">
    After gossiping, BP has a <em>posterior</em> LLR per mechanism. Convert back with
    <MathTex expr={TEX.posterior} />. The hard decision is dead simple: declare
    an error whenever the posterior LLR goes <strong>negative</strong>.
  </Callout>
</Section>

<!-- ===================================================================== -->
<Section id="dance" step="04" title="The message-passing dance" wide>
  <div class="prose">
    <p>
      Now the gossip itself. Two kinds of message flow along every edge, and we alternate
      them each iteration. Below, a true error sits on one bit (cyan ring); only the
      lit detectors are observed. Step through and watch the beliefs flow.
    </p>
    <p><strong>Variable → check.</strong> A mechanism tells each neighbouring detector
      its log-odds, <em>using its prior plus what every</em> other <em>detector told it</em>
      (never echoing a check's own message back):</p>
    <MathTex display expr={TEX.varToCheck} />
    <p><strong>Check → variable</strong> is the clever part. A detector enforces a parity
      constraint, and the exact rule for combining log-odds through an XOR is the
      <strong>tanh rule</strong>:</p>
    <MathTex display expr={TEX.tanhRule} />
    <p>
      where <MathTex expr="s_c" /> is that detector's syndrome bit (a lit detector flips the
      sign, pushing its neighbours toward <em>disagreeing</em>). Solving for the outgoing
      message gives the rule <code>bp.ts</code> actually evaluates:
    </p>
    <MathTex display expr={TEX.cToV} />
    <p>
      This is precisely <code>bp_method="product_sum"</code> -- sum-product BP in the log
      domain.
    </p>
  </div>

  <Worked title="One check → variable message by hand">
    <p>
      Take an unlit detector <MathTex expr="s_c = 0" /> with three neighbours sending in
      messages <MathTex expr={String.raw`m_{1\to c}=1.2`} />,
      <MathTex expr={String.raw`m_{2\to c}=-0.8`} />,
      <MathTex expr={String.raw`m_{3\to c}=2.0`} />. What does it tell neighbour&nbsp;1?
    </p>
    <ol>
      <li>
        Drop the back-edge: combine only the <em>other</em> two,
        <MathTex expr={String.raw`m_{2\to c}`} /> and
        <MathTex expr={String.raw`m_{3\to c}`} />.
      </li>
      <li>
        Take <MathTex expr={String.raw`\tanh(m/2)`} /> of each:
        <MathTex expr={String.raw`\tanh(-0.4)=-0.3799`} />,
        <MathTex expr={String.raw`\tanh(1.0)=0.7616`} />.
      </li>
      <li>
        Multiply (the check is unlit, so the sign is <MathTex expr="+1" />):
        <MathTex expr="(-0.3799)(0.7616)=-0.2894" />.
      </li>
      <li>
        Invert:
        <MathTex expr={String.raw`m_{c\to 1}=2\,\mathrm{atanh}(-0.2894)=-0.5958`} />.
      </li>
    </ol>
    {#snippet result()}
      The outgoing message is <b>−0.60</b>: <em>negative</em>, so this detector nudges
      neighbour&nbsp;1 toward "you fired," but only weakly (small magnitude) because the
      −0.8 message was itself unsure. Had the detector been <em>lit</em>
      (<MathTex expr="s_c=1" />), the sign flips and it would instead send
      <b>+0.5958</b>.
    {/snippet}
  </Worked>

  <Figure
    wide
    title="Message passing"
    legend={danceLegend}
    caption="Real sum-product BP on a 7-bit repetition code. Dots are live messages, sized and coloured (heat) by magnitude. Belief rings on each mechanism track its posterior P(error); rings/labels turn red once a mechanism is called an error."
  >
    <TannerGraph
      code={repCode}
      syndrome={repSyndrome}
      trueError={repTrueError}
      frame={repFrame}
      showMessages={showMsgs}
      height={250}
    />
    <div class="dance-controls">
      <Scrubber bind:value={repIter} min={0} max={11} label="iteration" />
      <div class="dance-row">
        <Toggle bind:checked={showMsgs} label="show messages" />
        <div class="err-pick">
          <span class="mini-label">true error on bit</span>
          {#each Array(7) as _, i (i)}
            <button class="ebtn" class:on={errBit === i} onclick={() => (errBit = i)}>
              {i}
            </button>
          {/each}
        </div>
      </div>
    </div>
  </Figure>

  <div class="prose">
    <p>
      Iteration <strong>0</strong> is just the priors -- every belief is the same calm
      positive number. As messages flow, the detectors next to the true error start
      shouting "something flipped near me," and the beliefs of the mechanisms between
      two lit detectors collapse toward <span style="color:{C.bad}">error</span>.
    </p>
  </div>
</Section>

<!-- ===================================================================== -->
<Section id="answer" step="05" title="Reading the answer">
  <p>
    Once the messages stop changing, BP <em>converged</em>. Each mechanism's
    <strong>posterior LLR</strong> sums its prior and <em>all</em> incoming check
    messages (no back-edge dropped this time); thresholding at zero gives the hard
    decision <MathTex expr="\hat e" />:
  </p>
  <MathTex display expr={TEX.post} />
  <p>
    The proof that it's self-consistent: feed <MathTex expr="\hat e" /> back through
    <MathTex expr="H" /> and check it reproduces the very syndrome we started with.
  </p>

  <Worked title="One mechanism's posterior and hard decision">
    <p>
      A mechanism with prior <MathTex expr="p=0.06" /> (so
      <MathTex expr={String.raw`\ell = \log\frac{0.94}{0.06} = 2.752`} />) sits between two lit
      detectors that now send it strong "error" messages
      <MathTex expr="-2.0" /> and <MathTex expr="-1.6" />.
    </p>
    <ol>
      <li>
        Sum prior + all incoming:
        <MathTex expr="L = 2.752 + (-2.0) + (-1.6) = -0.848" />.
      </li>
      <li>
        Convert to a probability:
        <MathTex expr={String.raw`p = \tfrac{1}{1+e^{L}} = \tfrac{1}{1+e^{-0.848}} = 0.70`} />.
      </li>
      <li>
        Threshold: <MathTex expr="L < 0" />, so the hard decision is
        <MathTex expr="\hat e = 1" />.
      </li>
    </ol>
    {#snippet result()}
      The two detectors <em>outvoted</em> the prior: a mechanism that started 94% safe is
      now called an <b>error</b> (P ≈ 0.70). One lukewarm prior is no match for two
      confident neighbours -- that's evidence adding up in log-space.
    {/snippet}
  </Worked>

  <Figure
    title="Posterior beliefs"
    legend={beliefLegend}
    caption="Posterior beliefs at the current iteration. Bars grow left (red) toward 'error', right toward 'no error'; intensity tracks confidence. The 'true' mechanism is marked in cyan."
  >
    <BeliefBars
      posterior={repFrame.posterior}
      hard={repFrame.hard}
      trueError={repTrueError}
    />
    <div class="answer-status" class:ok={repCorrect}>
      {#if repFrame.satisfied}
        {#if repCorrect}
          ✓ converged at iteration {repFrame.iter}: decoded error reproduces the
          syndrome -- and it matches the true error.
        {:else}
          ✓ syndrome reproduced at iteration {repFrame.iter} (a valid, if degenerate,
          explanation).
        {/if}
      {:else}
        ... still settling -- the hard decision doesn't yet reproduce the syndrome.
      {/if}
    </div>
  </Figure>

  <p>
    The recovered mechanism vector then maps through the observable matrix
    (<MathTex expr={TEX.obs} />) to say which <em>logical</em>
    observables flipped -- the actual output qliff hands back. Try moving the true error
    around in the panel above; for the repetition code, BP nails it every time.
  </p>
  <Callout kind="note" title="So far, so easy">
    The repetition code is <em>graphlike</em> and loop-free near a single error, so BP
    glides to the answer. That's the happy path. Next we break it.
  </Callout>
</Section>

<!-- ===================================================================== -->
<Section id="stuck" step="06" title="When BP gets stuck" wide>
  <div class="prose">
    <p>
      Quantum codes are <strong>degenerate</strong>: genuinely different errors can have
      identical syndromes and identical likelihoods. When the graph also has short
      cycles, BP's "independent evidence" assumption breaks -- and the beliefs can
      <strong>oscillate forever</strong>, never committing to an answer.
    </p>
    <p>
      Here's a tiny hand-built code that traps it. Detector <MathTex expr="d_0" /> touches
      all four mechanisms; <MathTex expr="d_1" /> and <MathTex expr="d_2" /> each pair two of
      them. The syndrome lights <MathTex expr="d_0,d_1" />; the obvious fix is mechanism
      <MathTex expr="e_0" /> alone. But the symmetry makes mechanisms
      <MathTex expr="e_0" /> and <MathTex expr="e_1" /> perfectly tied. Watch:
    </p>
  </div>

  <Figure
    wide
    title="Degenerate trap"
    legend={stuckLegend}
    caption="A degenerate trap. Step the iteration: the hard decision flips between e0,e1 and nothing on every round, and the posteriors for e0 and e1 stay locked together -- BP never decides. (It is genuinely not converging; this is not an animation loop.)"
  >
    <TannerGraph
      code={stuckCode}
      syndrome={stuckSyndrome}
      frame={stuckFrame}
      showMessages={true}
      height={250}
    />
    <BeliefBars posterior={stuckFrame.posterior} hard={stuckFrame.hard} />
    <div class="dance-controls">
      <Scrubber bind:value={stuckIter} min={0} max={15} label="iteration" />
      <div class="answer-status warn">
        iteration {stuckFrame.iter}: hard decision =
        <span class="mono">{stuckFrame.hard.join("")}</span>
        {#if stuckFrame.satisfied}
          (reproduces syndrome)
        {:else}
          -- does <strong>not</strong> reproduce the syndrome
          <span class="mono">{stuckSyndrome.join("")}</span>
        {/if}
      </div>
    </div>
  </Figure>

  <div class="prose">
    <Callout kind="warn" title="The symmetric trap">
      Notice <MathTex expr="e_0" /> and <MathTex expr="e_1" /> always carry the
      <em>identical</em> posterior -- and it keeps flipping sign. BP has split its belief
      symmetrically between two indistinguishable stories and can't break the tie. No
      number of extra iterations helps. This is exactly the failure mode that sinks plain
      BP on real quantum codes (colour codes, surface codes with short cycles).
    </Callout>
  </div>
</Section>

<!-- ===================================================================== -->
<Section id="osd" step="07" title="OSD to the rescue" wide>
  <div class="prose">
    <p>
      <strong>BP proposes, OSD disposes.</strong> Ordered-statistics decoding doesn't
      throw away BP's work -- it uses BP's soft output to make a <em>decisive</em> guess.
      qliff runs <code>osd_method="osd_cs"</code> with <code>osd_order=7</code>. The
      recipe:
    </p>
    <ol>
      <li>
        <strong>Order by reliability.</strong> Sort the mechanisms by
        <MathTex expr={TEX.relAbs} /> -- most confident first. Even when BP can't
        decide <em>between</em> <MathTex expr="e_0" /> and <MathTex expr="e_1" />, it
        <em>is</em> sure that <MathTex expr="e_2,e_3" /> stayed quiet.
      </li>
      <li>
        <strong>Solve a full-rank core exactly.</strong> Walk that ordered list and
        Gaussian-eliminate over <MathTex expr={TEX.f2} /> to pull out a most-reliable
        set of independent pivot columns <MathTex expr={String.raw`\mathcal{P}`} />, then solve that
        square subsystem <MathTex expr={TEX.osdSolve} /> (free columns set to 0). This
        forces a recovery that <em>exactly</em> reproduces the syndrome -- no more
        oscillation.
      </li>
      <li>
        <strong>Search small corrections (order&nbsp;{7}).</strong> Flip up to
        <MathTex expr="7" /> of the least-reliable free columns, re-solve, and keep the
        <em>lowest-weight</em> consistent answer found.
      </li>
    </ol>
  </div>

  <Figure
    wide
    title="BP + OSD"
    legend={osdLegend}
    caption="OSD applied to BP's stuck output. Columns are listed most-reliable-first; the pivot core is solved exactly to force a syndrome-matching recovery."
  >
    <div class="osd-grid">
      <div class="osd-col">
        <div class="osd-h">1 · reliability order</div>
        <div class="rel-row">
          {#each osd.order as m, rank (m)}
            {@const isPivot = osd.pivots.includes(m)}
            <div class="rel-cell" class:pivot={isPivot}>
              <span class="mono">e{m}</span>
              <span class="rel-bar">
                <span
                  class="rel-fill"
                  style="height:{Math.min(100, (Math.abs(stuckBp.finalPosterior[m]) / 5) * 100).toFixed(0)}%;
                         background:{withAlpha(heat(Math.min(1, Math.abs(stuckBp.finalPosterior[m]) / 5)), 0.9)}"
                ></span>
              </span>
              <span class="rel-tag">{isPivot ? "pivot" : "free"}</span>
            </div>
          {/each}
        </div>
      </div>
      <div class="osd-col">
        <div class="osd-h">2 · solved recovery</div>
        <div class="osd-sol">
          <div class="sol-line">
            <span class="sol-label">order-0 (free = 0):</span>
            <span class="mono sol-vec">{osd.osd0.join("")}</span>
            <span class="sol-w">weight {osd.osd0Weight}</span>
          </div>
          <div class="sol-line best">
            <span class="sol-label">after order-{7} search:</span>
            <span class="mono sol-vec">{osd.solution.join("")}</span>
            <span class="sol-w">weight {osd.solutionWeight}</span>
          </div>
          <div class="sol-verdict" class:ok={osdSyndromeOk}>
            {#if osdSyndromeOk}
              ✓ reproduces syndrome <span class="mono">{stuckSyndrome.join("")}</span> --
              BP+OSD recovers <span class="mono">e0</span> where plain BP spun forever.
            {:else}
              residual <span class="mono">{osd.residual.join("")}</span>
            {/if}
          </div>
        </div>
      </div>
    </div>
  </Figure>

  <div class="prose">
    <Callout kind="key" title="Why qliff ships BP+OSD">
      OSD turns BP's <em>almost-an-answer</em> into a guaranteed syndrome-consistent,
      low-weight recovery. Crucially, BP+OSD works on the <strong>general bipartite
      graph</strong> -- including <em>non-graphlike</em> codes (colour codes, dense LDPC)
      where a detector touches more than two errors and MWPM has no graph to match. That
      generality is the whole reason it sits alongside matching in the decoder zoo.
    </Callout>
    <p>
      BP+OSD is fast and general, but it isn't <em>optimal</em>: OSD's combination search
      is a heuristic, not an exhaustive sum over every error. The next chapter contracts
      a tensor network to do exactly that -- <strong>exact maximum-likelihood
      decoding</strong> -- weighing every consistent error at once.
    </p>
  </div>
</Section>

<style>
  .check-toggles,
  .dance-controls {
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .check-toggles {
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

  .dance-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 14px;
  }

  .err-pick {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .mini-label {
    font-size: 11.5px;
    color: var(--muted);
    margin-right: 4px;
  }

  .ebtn {
    width: 26px;
    height: 26px;
    padding: 0;
    font-size: 12px;
    border-radius: 6px;
    border: 1px solid var(--line);
    background: color-mix(in srgb, var(--bg-2) 60%, transparent);
    color: var(--muted);
  }

  .ebtn.on {
    border-color: color-mix(in srgb, var(--accent-2) 60%, transparent);
    background: color-mix(in srgb, var(--accent-2) 16%, transparent);
    color: var(--fg);
  }

  /* prior gauge */
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

  .answer-status {
    margin-top: 14px;
    text-align: center;
    font-size: 13.5px;
    color: var(--muted);
    line-height: 1.5;
  }

  .answer-status.ok {
    color: var(--ok);
  }

  .answer-status.warn {
    color: var(--accent-3);
  }

  /* OSD panel */
  .osd-grid {
    display: grid;
    grid-template-columns: 1fr 1.3fr;
    gap: 24px;
  }

  .osd-h {
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--faint);
    margin-bottom: 12px;
  }

  .rel-row {
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }

  .rel-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    padding: 6px;
    border-radius: var(--r-sm, 8px);
    border: 1px solid transparent;
  }

  .rel-cell.pivot {
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
    background: var(--grad-soft);
  }

  .rel-bar {
    width: 14px;
    height: 60px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    display: flex;
    align-items: flex-end;
    overflow: hidden;
  }

  .rel-fill {
    width: 100%;
    transition: height 0.2s ease;
  }

  .rel-tag {
    font-size: 9.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--faint);
  }

  .rel-cell.pivot .rel-tag {
    color: var(--accent);
  }

  .osd-sol {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .sol-line {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 13.5px;
    color: var(--muted);
  }

  .sol-line.best {
    color: var(--fg);
  }

  .sol-label {
    min-width: 150px;
  }

  .sol-vec {
    font-size: 16px;
    letter-spacing: 0.18em;
    color: var(--fg);
  }

  .sol-w {
    font-size: 12px;
    color: var(--faint);
  }

  .sol-verdict {
    margin-top: 6px;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.5;
  }

  .sol-verdict.ok {
    color: var(--ok);
  }

  @media (max-width: 720px) {
    .gauge-row,
    .osd-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
