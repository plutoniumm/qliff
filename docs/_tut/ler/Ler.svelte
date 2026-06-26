<script lang="ts">
  // Capstone explainer: how qliff turns a noisy, decoded run into a logical error
  // rate (LER) and fidelity, with honest error bars and the threshold crossing.
  // Faithful to qliff/qec/threshold.py (logical_error_rate, _weighted_error_rate,
  // sweep/isweep) and qliff/qec/codes.py (logical_fidelity). Every plot reacts to
  // sliders; all curves are $derived so no $effect ever writes the state it reads.
  import Section from "$lib/Section.svelte";
  import Math from "$lib/Math.svelte";
  import Slider from "$lib/Slider.svelte";
  import Callout from "$lib/Callout.svelte";
  import Figure from "$lib/Figure.svelte";
  import Worked from "$lib/Worked.svelte";
  import { C } from "$lib/colors";
  import { mulberry32 } from "$lib/rng";
  import ShotsGrid from "./ShotsGrid.svelte";
  import ConvergePlot from "./ConvergePlot.svelte";
  import SweepPlot from "./SweepPlot.svelte";
  import ThresholdPlot from "./ThresholdPlot.svelte";
  import {
    repCodeLER,
    repCodeMonteCarlo,
    repCodeTrace,
    repCodeCurve,
    weightedMonteCarlo,
    surfaceModelCurve,
  } from "./model";

  // The <Math> component shadows the global Math in this scope; alias the maths
  // we need so the script keeps using floor/min/max/ceil etc.
  const num = globalThis.Math;

  // ---- Section 1: shots grid --------------------------------------------------
  // Seeded initial grid: ~12% of shots are logical errors (predicted != observed).
  function makeShots(n: number, errFrac: number, seed: number) {
    const rng = mulberry32(seed);
    const out = [];
    for (let i = 0; i < n; i += 1) {
      const observed = rng() < 0.3;
      const wrong = rng() < errFrac;
      out.push({ observed, predicted: wrong ? !observed : observed });
    }

    return out;
  }
  let shots = $state(makeShots(48, 0.12, 7));
  function reshuffle(): void {
    shots = makeShots(48, 0.12, num.floor(num.random() * 1e9));
  }

  // ---- Section 2: truth-table (multi-observable np.any rule) ------------------
  let obsA = $state<[boolean, boolean]>([true, false]); // predicted (2 observables)
  let obsB = $state<[boolean, boolean]>([true, true]); // true
  const rowWrong = $derived(obsA.some((v, i) => v !== obsB[i]));

  // ---- Section 3: Monte-Carlo convergence + N slider --------------------------
  let mcP = $state(0.08);
  let mcD = $state(5);
  let mcN = $state(2000);
  let mcSeed = $state(1);
  const mcTruth = $derived(repCodeLER(mcP, mcD));
  const mcResult = $derived(repCodeMonteCarlo(mcP, mcD, mcN, mcSeed));
  const mcTrace = $derived(
    repCodeTrace(mcP, mcD, mcN, mcSeed, num.max(1, num.floor(mcN / 120))),
  );

  // ---- Section 4: weighted (coherent) estimator -------------------------------
  let wP = $state(0.05);
  let wGamma = $state(2.0);
  let wN = $state(4000);
  let wSeed = $state(3);
  const wTruth = $derived(repCodeLER(wP, 5));
  const wResult = $derived(weightedMonteCarlo(wTruth, wGamma, wN, wSeed));
  // shots needed to reach a target relative error, binomial vs weighted
  const targetRel = 0.1; // 10% relative error bar
  const binomShotsNeeded = $derived(
    wTruth > 0 ? num.ceil((1 - wTruth) / (wTruth * targetRel * targetRel)) : 0,
  );
  // weighted variance ~ gamma^2 * trueLER, so shots scale by ~gamma^2
  const weightedShotsNeeded = $derived(num.ceil(binomShotsNeeded * wGamma * wGamma));

  // ---- Section 5: single-distance sweep with error bars -----------------------
  let swD = $state(5);
  let swShots = $state(3000);
  let swSeed = $state(11);
  const swPMin = 0.01;
  const swPMax = 0.18;
  const swCurve = $derived(repCodeCurve(swD, swPMin, swPMax, 120, false));
  const swPoints = $derived(
    Array.from({ length: 9 }, (_, i) => {
      const p = swPMin + ((swPMax - swPMin) * i) / 8;
      const mc = repCodeMonteCarlo(p, swD, swShots, swSeed + i);

      return { p, ler: mc.ler, stderr: mc.stderr };
    }),
  );

  // ---- Section 6: threshold crossing (phenomenological surface model) ---------
  let pTh = $state(0.1);
  let modelA = $state(0.5);
  let dSet = $state<number[]>([3, 5, 7, 9]);
  const distanceColors = [C.accent2, C.accent, C.accent3, C.defect, C.ok];
  const thPMin = 1e-3;
  const thPMax = 0.5;
  const thCurves = $derived(
    dSet.map((d, i) => ({
      d,
      color: distanceColors[i % distanceColors.length],
      points: surfaceModelCurve(d, pTh, modelA, thPMin, thPMax, 160),
    })),
  );
  function toggleD(d: number): void {
    dSet = dSet.includes(d)
      ? dSet.filter((x) => x !== d).sort((a, b) => a - b)
      : [...dSet, d].sort((a, b) => a - b);
  }
  const allD = [3, 5, 7, 9, 11];

  function pct(v: number): string {
    return `${(v * 100).toFixed(2)}%`;
  }
</script>

<Section id="verdict" step="01" title="The verdict of one shot">
  <p>
    A round of error correction ends with a single yes/no question: <em>did the logical
    qubit survive?</em> We run the noisy circuit, read out the syndrome, hand it to a
    decoder, and the decoder announces which logical observables it thinks were flipped -- its
    <strong>prediction</strong>. We also know the <strong>truth</strong>, because in
    simulation we tracked the real errors. The shot is a <strong style="color:{C.bad}">logical
    error</strong> exactly when the prediction disagrees with the truth.
  </p>
  <p>
    That is the whole verdict, and it is exactly what qliff computes:
    <Math expr={String.raw`\text{shot is wrong} \iff \text{predicted} \neq \text{true}`} />.
    Below is a grid of shots. Each cell shows <span class="mono">predicted / true</span> for the
    logical observable. Click a cell to flip the decoder's guess and watch the running rate.
  </p>
</Section>

<Section id="verdict-grid" step="" title="" wide>
  <Figure
    wide
    title="Shot verdicts"
    legend={[
      { color: C.ok, mark: "box", label: "green: predicted = true (survived)" },
      { color: C.bad, mark: "box", label: "red: predicted ≠ true (logical error)" },
    ]}
    caption="48 decoded shots, each cell reading predicted / true for the logical observable. Green = decoder agreed with the truth (corrected); red = it disagreed (a logical error). The LER is just the red fraction."
  >
    <ShotsGrid bind:shots />
    <div class="ctl-row">
      <button onclick={reshuffle}>↻ new random batch</button>
    </div>
  </Figure>
</Section>

<Section id="fidelity" step="02" title="Fidelity and LER">
  <p>
    Stack up many shots and the rate of red cells is the <strong>logical error rate</strong>.
    Its complement is the <strong style="color:{C.ok}">logical fidelity</strong> -- the fraction
    of shots that came through clean. In qliff this is one line
    (<span class="mono">codes.py</span>):
  </p>
  <Math display expr={String.raw`P_L = \frac{1}{N}\sum_{i=1}^{N} \mathbf{1}\!\left[\text{pred}_i \neq \text{obs}_i\right] = \frac{\text{fails}}{N}, \qquad F = 1 - P_L.`} />
  <p>
    Here <Math expr={String.raw`P_L`} /> is the logical error rate, <Math expr={String.raw`F`} /> the fidelity,
    <Math expr={String.raw`N`} /> the number of shots, and <Math expr={String.raw`\mathbf{1}[\cdot]`} /> the
    indicator that is 1 when shot <Math expr={String.raw`i`} /> fails (predicted <Math expr={String.raw`\neq`} />
    observed) and 0 otherwise -- so the sum is just the failure count.
  </p>
  <p>
    A subtlety appears when a code protects more than one logical qubit (the toric code has
    two). Each shot then has a <em>row</em> of observables. qliff's rule is unforgiving: the
    shot fails if <strong>any</strong> column disagrees --
    <Math expr={String.raw`\texttt{np.any}(\text{pred} \neq \text{obs},\, \text{axis}=1)`} />. Getting most
    observables right is not partial credit.
  </p>

  <Callout kind="key" title="Try the np.any rule">
    <div class="tt">
      <div class="tt-col">
        <span class="tt-h">predicted</span>
        <div class="tt-cells">
          <button class="bit" class:on={obsA[0]} onclick={() => (obsA = [!obsA[0], obsA[1]])}>{obsA[0] ? "1" : "0"}</button>
          <button class="bit" class:on={obsA[1]} onclick={() => (obsA = [obsA[0], !obsA[1]])}>{obsA[1] ? "1" : "0"}</button>
        </div>
      </div>
      <div class="tt-col">
        <span class="tt-h">true</span>
        <div class="tt-cells">
          <button class="bit" class:on={obsB[0]} onclick={() => (obsB = [!obsB[0], obsB[1]])}>{obsB[0] ? "1" : "0"}</button>
          <button class="bit" class:on={obsB[1]} onclick={() => (obsB = [obsB[0], !obsB[1]])}>{obsB[1] ? "1" : "0"}</button>
        </div>
      </div>
      <div class="tt-col">
        <span class="tt-h">verdict</span>
        <div class="verdict" style="color:{rowWrong ? C.bad : C.ok}">
          {rowWrong ? "LOGICAL ERROR" : "survived"}
        </div>
      </div>
    </div>
    <p style="margin:10px 0 0; font-size:14px;">
      Two logical observables. Click any bit. The shot counts as wrong the moment a single
      column mismatches -- so <span class="mono">10</span> vs <span class="mono">11</span> already fails.
    </p>
  </Callout>
</Section>

<Section id="montecarlo" step="03" title="It's a Monte-Carlo estimate, so it has error bars">
  <p>
    We never see the true LER directly -- we <em>estimate</em> it by sampling a finite number of
    shots <Math expr={String.raw`N`} />. That makes the reported LER a sample mean, and sample means jitter.
    For ordinary (Pauli) noise the verdict per shot is a coin flip, so the spread of the
    estimate is the textbook <strong>binomial standard error</strong> -- exactly what qliff
    returns alongside the LER:
  </p>
  <Math display expr={String.raw`\mathrm{stderr} = \sqrt{\dfrac{\mathrm{LER}\,(1-\mathrm{LER})}{N}} \;\propto\; \dfrac{1}{\sqrt{N}}.`} />
  <p>
    To make this honest we run a <em>real</em> seeded Monte-Carlo in your browser: the
    distance-<Math expr={String.raw`d`} /> repetition code under bit-flip noise, decoded by majority vote.
    A logical error happens when more than <Math expr={String.raw`d/2`} /> of the <Math expr={String.raw`d`} /> bits
    flip -- whose exact probability is a binomial tail (the green line). Watch the estimate
    converge and the <Math expr={String.raw`\pm\,\mathrm{stderr}`} /> band taper as <Math expr={String.raw`N`} /> grows.
  </p>
</Section>

<Section id="montecarlo-plot" step="" title="" wide>
  <Figure
    wide
    title="Convergence with N"
    legend={[
      { color: C.accent, mark: "line", label: "running LER estimate" },
      { color: C.accent, mark: "box", label: "±1σ binomial band" },
      { color: C.ok, mark: "dash", label: "exact LER" },
    ]}
    caption="Seeded Monte-Carlo of the repetition code. x = shots N (log); y = running LER estimate (% of shots). The purple trace is the running estimate; the band is ±1σ = ±stderr; the green dashed line is the exact LER. The band shrinks like 1/√N."
  >
    <div class="prose-controls">
      <Slider bind:value={mcP} min={0.01} max={0.3} step={0.005} label="physical error p" format={(v) => v.toFixed(3)} />
      <Slider bind:value={mcD} min={3} max={11} step={2} label="code distance d" />
      <Slider bind:value={mcN} min={50} max={20000} step={50} label="shots N" />
      <Slider bind:value={mcSeed} min={1} max={40} step={1} label="seed" />
    </div>
    <ConvergePlot trace={mcTrace} truth={mcTruth} maxN={mcN} />
    <div class="stat-strip">
      <span>exact LER <b>{pct(mcTruth)}</b></span>
      <span>estimate <b style="color:{C.accent}">{pct(mcResult.ler)}</b></span>
      <span>± stderr <b>{pct(mcResult.stderr)}</b></span>
      <span>errors seen <b>{mcResult.errors}</b> / {mcResult.shots}</span>
    </div>
  </Figure>
  <div class="prose">
    <Worked title="An error bar from 37 failures in N = 4000 shots">
      <ol>
        <li>
          Count the verdicts: the decoder was wrong on <b>37</b> of <Math expr={String.raw`N = 4000`} />
          shots (qliff: a shot fails iff predicted <Math expr={String.raw`\neq`} /> observed).
        </li>
        <li>
          The Monte-Carlo estimate is the failure fraction:
          <Math expr={String.raw`P_L = \tfrac{\text{fails}}{N} = \tfrac{37}{4000} = 0.00925`} />.
        </li>
        <li>
          Fidelity is its complement:
          <Math expr={String.raw`F = 1 - P_L = 0.99075`} />.
        </li>
        <li>
          The binomial standard error:
          <Math expr={String.raw`\sigma = \sqrt{\tfrac{P_L(1-P_L)}{N}} = \sqrt{\tfrac{0.00925 \cdot 0.99075}{4000}} \approx 0.00151`} />.
        </li>
        <li>
          To <em>halve</em> the bar you need <Math expr={String.raw`4\times`} /> the shots
          (<Math expr={String.raw`\sigma \propto 1/\sqrt{N}`} />): <Math expr={String.raw`N = 16{,}000`} />
          drops <Math expr={String.raw`\sigma`} /> to <Math expr={String.raw`\approx 0.00076`} />.
        </li>
      </ol>
      {#snippet result()}
        Report <b><Math expr={String.raw`P_L = 0.0093 \pm 0.0015`} /></b>
        (fidelity <Math expr={String.raw`F \approx 0.9908`} />). Quartering the error bar costs
        <b>16×</b> the shots.
      {/snippet}
    </Worked>

    <Callout kind="note" title="Why rare errors are expensive">
      Push <span class="mono">p</span> down or <span class="mono">d</span> up and the true LER
      can fall below <span class="mono">{pct(mcTruth)}</span>. With few shots you may see
      <em>zero</em> errors and report LER = 0 with a deceptively tiny error bar. To resolve a
      LER of <Math expr={String.raw`\varepsilon`} /> you need roughly <Math expr={String.raw`N \gtrsim 1/\varepsilon`} />
      shots just to see a handful of errors -- the deeper the suppression, the more shots it costs.
    </Callout>
  </div>
</Section>

<Section id="weighted" step="04" title="The weighted case: coherent noise">
  <p>
    Coherent noise (a small over-rotation, amplitude damping) is <em>not</em> a random Pauli
    flip, so there is no honest detector-error model to sample from. qliff's escape hatch is
    <strong>importance sampling</strong>: it draws stabilizer trajectories from a
    quasiprobability and attaches a <strong>signed weight</strong> <Math expr={String.raw`w`} /> to each
    shot. The LER becomes a weighted mean
    (<span class="mono">threshold.py: _weighted_error_rate</span>):
  </p>
  <Math display expr={String.raw`\mathrm{LER} = \operatorname*{mean}_{\text{shots}}\big(w \cdot \text{error}\big), \qquad \mathrm{stderr} = \dfrac{\operatorname{std}(w \cdot \text{error})}{\sqrt{N}},`} />
  <p>
    with the result clamped to <Math expr={String.raw`[0,1]`} />. The weights average to one, so the
    estimate is unbiased -- but their spread inflates the variance. Each weight has magnitude
    <Math expr={String.raw`\gamma`} />, so <Math expr={String.raw`\operatorname{var}(w\cdot\text{error}) \approx \gamma^2 P_L`} />
    and the error bar grows by a factor of <Math expr={String.raw`\gamma`} /> over the Pauli case:
  </p>
  <Math display expr={String.raw`\sigma_{\text{w}} \approx \gamma\,\sqrt{\dfrac{P_L}{N}} = \gamma\,\sigma_{\text{binom}} \;\Longrightarrow\; N_{\text{w}} \approx \gamma^2\,N_{\text{binom}}\ \text{for the same bar.}`} />
  <p>
    The negativity <Math expr={String.raw`\gamma \ge 1`} /> from the coherent-noise engine measures that
    spread: bigger <Math expr={String.raw`\gamma`} /> means noisier weights, a fatter error bar, and many
    more shots for the same precision. (This ties straight back to the coherent-noise and
    noise-sampling pages.)
  </p>
</Section>

<Section id="weighted-plot" step="" title="" wide>
  <Figure
    wide
    title="Coherent shot cost"
    legend={[
      { color: C.ok, mark: "box", label: "Pauli: shots for 10% error bar" },
      { color: C.accent3, mark: "box", label: "coherent (γ): inflated shot budget" },
    ]}
    caption="Importance-weighted LER. Bars compare shots needed for a 10% relative error bar: Pauli (binomial) vs coherent (variance inflated by γ²). The estimate stays unbiased as γ grows, but the standard error balloons -- you pay for non-Pauli noise in shots."
  >
    <div class="prose-controls">
      <Slider bind:value={wP} min={0.01} max={0.2} step={0.005} label="underlying p" format={(v) => v.toFixed(3)} />
      <Slider bind:value={wGamma} min={1} max={6} step={0.1} label="negativity γ" format={(v) => v.toFixed(1)} />
      <Slider bind:value={wN} min={200} max={40000} step={200} label="shots N" />
      <Slider bind:value={wSeed} min={1} max={40} step={1} label="seed" />
    </div>
    <div class="stat-strip">
      <span>true LER <b>{pct(wTruth)}</b></span>
      <span>weighted estimate <b style="color:{C.accent}">{pct(wResult.ler)}</b></span>
      <span>± stderr <b style="color:{wGamma > 2.5 ? C.bad : C.fg}">{pct(wResult.stderr)}</b></span>
    </div>
    <div class="cost">
      <div class="cost-bar">
        <span class="cost-lbl">Pauli (binomial)</span>
        <div class="bar"><div class="fill" style="width:{num.min(100, (binomShotsNeeded / weightedShotsNeeded) * 100)}%; background:{C.ok}"></div></div>
        <span class="mono cost-n">{binomShotsNeeded.toLocaleString()} shots</span>
      </div>
      <div class="cost-bar">
        <span class="cost-lbl">coherent (γ={wGamma.toFixed(1)})</span>
        <div class="bar"><div class="fill" style="width:100%; background:{C.accent3}"></div></div>
        <span class="mono cost-n">{weightedShotsNeeded.toLocaleString()} shots</span>
      </div>
      <p class="cost-note">
        Shots to reach a 10% relative error bar. Weighted variance scales like
        <Math expr={String.raw`\gamma^2`} />, so the budget grows roughly <Math expr={String.raw`\gamma^2`} />-fold.
      </p>
    </div>
  </Figure>
  <div class="prose">
    <Worked title="The γ-tax: how many more shots at γ = 2?">
      <ol>
        <li>
          Take a true LER of <Math expr={String.raw`P_L \approx 0.00116`} /> (the repetition code at
          <Math expr={String.raw`p=0.05,\ d=5`} />).
        </li>
        <li>
          A Pauli (binomial) run needs
          <Math expr={String.raw`N_{\text{binom}} = \tfrac{1-P_L}{P_L\,(0.1)^2} \approx 86{,}247`} />
          shots for a 10% relative bar.
        </li>
        <li>
          Coherent noise carries weights of magnitude <Math expr={String.raw`\gamma = 2`} />, inflating the
          variance by <Math expr={String.raw`\gamma^2 = 4`} />.
        </li>
        <li>
          So the same bar now costs
          <Math expr={String.raw`N_{\text{w}} = \gamma^2 N_{\text{binom}} \approx 4 \times 86{,}247 \approx 344{,}988`} />
          shots.
        </li>
      </ol>
      {#snippet result()}
        A modest <Math expr={String.raw`\gamma = 2`} /> already <b>4×</b>'s the shot budget; at
        <Math expr={String.raw`\gamma = 3`} /> it is <b>9×</b>. Non-Pauli noise is expensive.
      {/snippet}
    </Worked>
  </div>
</Section>

<Section id="sweep" step="05" title="The sweep: LER versus p">
  <p>
    One LER is a single dot. The interesting object is the <strong>curve</strong>: how the
    logical error rate responds as we dial the physical rate <Math expr={String.raw`p`} /> up and down.
    qliff's <span class="mono">sweep(circuit_fn, p_values, ...)</span> does precisely this -- it
    rebuilds the circuit at each <Math expr={String.raw`p`} />, runs the sample → decode → compare loop,
    and yields a <Math expr={String.raw`(p,\ \mathrm{LER},\ \mathrm{stderr})`} /> triple per point, with the
    <strong>seed held fixed</strong> across points so the curve is reproducible.
  </p>
  <p>
    Below, the smooth line is the exact repetition-code LER and the points are seeded
    Monte-Carlo with binomial error bars. At small <Math expr={String.raw`p`} /> the code <em>helps</em>:
    the LER sits far below the break-even dashed line <Math expr={String.raw`\mathrm{LER} = p`} />. Push
    <Math expr={String.raw`p`} /> too high and majority vote starts losing -- the code <em>hurts</em>.
  </p>
</Section>

<Section id="sweep-plot" step="" title="" wide>
  <Figure
    wide
    title="LER vs p sweep"
    legend={[
      { color: C.accent2, mark: "line", label: "exact LER(p) curve" },
      { color: C.accent, mark: "dot", label: "Monte-Carlo point ±1σ" },
    ]}
    caption="A reproducible LER(p) sweep for one distance d: x = physical rate p, y = logical rate P_L (log). Exact curve plus seeded Monte-Carlo with binomial error bars -- exactly the (p, ler, stderr) triples qliff's sweep yields."
  >
    <div class="prose-controls">
      <Slider bind:value={swD} min={3} max={11} step={2} label="code distance d" />
      <Slider bind:value={swShots} min={200} max={20000} step={200} label="shots per point" />
      <Slider bind:value={swSeed} min={1} max={40} step={1} label="seed" />
    </div>
    <SweepPlot curve={swCurve} points={swPoints} pMin={swPMin} pMax={swPMax} />
  </Figure>
</Section>

<Section id="threshold" step="06" title="The threshold plot">
  <p>
    Now the headline result of the entire field. Draw LER-vs-<Math expr={String.raw`p`} /> on log-log axes
    for several code <strong>distances</strong> at once, and the curves <strong>cross</strong> at
    a single point -- the <strong style="color:{C.defect}">threshold</strong> <Math expr={String.raw`p_{th}`} />:
  </p>
  <ul>
    <li>
      <strong>Below <Math expr={String.raw`p_{th}`} />:</strong> bigger <Math expr={String.raw`d`} /> gives
      <strong style="color:{C.ok}">lower</strong> LER. Adding qubits crushes the error rate
      toward zero -- error correction <em>works</em>, and works better the more you scale.
    </li>
    <li>
      <strong>Above <Math expr={String.raw`p_{th}`} />:</strong> bigger <Math expr={String.raw`d`} /> gives
      <strong style="color:{C.bad}">higher</strong> LER. Your hardware is too noisy; adding
      qubits only adds places to fail.
    </li>
  </ul>
  <p>
    The plot below uses a clean, standard <strong>phenomenological model</strong> (it is a
    model, not a fit): <Math expr={String.raw`\mathrm{LER}(p,d) \approx A\,(p/p_{th})^{\lceil d/2 \rceil}`} />,
    softly saturating above threshold. The crossing isn't drawn in by hand -- it
    <em>emerges</em> from that exponent as you move the sliders.
  </p>
</Section>

<Section id="threshold-plot" step="" title="" wide>
  <Figure
    wide
    title="Threshold crossing"
    legend={[
      ...dSet.map((d, i) => ({
        color: distanceColors[i % distanceColors.length],
        mark: "line" as const,
        label: `d = ${d}`,
      })),
      { color: C.defect, mark: "dash" as const, label: "p_th (curves cross)" },
      { color: C.muted, mark: "dash" as const, label: "break-even LER = p" },
    ]}
    caption="The money shot: LER vs p (log-log) for several distances d. x = physical rate p, y = logical rate P_L. Curves cross at p_th (dashed gold) -- the threshold. Below it, more distance = less logical error; above it, more distance = more. Dotted grey is break-even LER = p."
  >
    <div class="prose-controls">
      <Slider bind:value={pTh} min={0.02} max={0.25} step={0.005} label="threshold p_th (model)" format={(v) => v.toFixed(3)} />
      <Slider bind:value={modelA} min={0.1} max={1.5} step={0.05} label="prefactor A (model)" format={(v) => v.toFixed(2)} />
    </div>
    <div class="dchips">
      <span class="dchips-lbl">distances:</span>
      {#each allD as d, i}
        <button
          class="chip"
          class:on={dSet.includes(d)}
          style="--cc:{distanceColors[num.max(0, dSet.indexOf(d)) % distanceColors.length]}"
          onclick={() => toggleD(d)}
        >d={d}</button>
      {/each}
    </div>
    <ThresholdPlot curves={thCurves} {pTh} pMin={thPMin} pMax={thPMax} lerMin={1e-6} lerMax={1} />
  </Figure>
  <div class="prose">
    <Callout kind="key" title="Read it off">
      Find the crossing. To its left, the steepest (highest-<Math expr={String.raw`d`} />) curve is on the
      bottom -- scaling helps. To its right, that same curve is on top -- scaling hurts. A real
      qliff threshold plot is this same picture, just with each point produced by a true
      sample → decode → compare run instead of a formula.
    </Callout>
  </div>
</Section>

<Section id="pipeline" step="07" title="The whole pipeline, and running it for real">
  <p>
    Every number on this page comes from the same five-stage loop, repeated <Math expr={String.raw`N`} />
    times and averaged:
  </p>
  <Math display expr={String.raw`\underbrace{\text{noise}}_{\text{1}} \rightarrow \underbrace{\text{syndrome}}_{\text{2}} \rightarrow \underbrace{\text{decode}}_{\text{3}} \rightarrow \underbrace{\text{compare}}_{\text{4}} \rightarrow \underbrace{\mathrm{LER} = 1 - \text{fidelity}}_{\text{5}}`} />
  <p>
    Stage 1 injects errors (Pauli channels sample directly; coherent channels need the weighted
    sampler from the previous page). Stage 2 reads the stabilizers into a syndrome. Stage 3 is
    the decoder -- MWPM, belief propagation, or a tensor network from the first three pages.
    Stage 4 is the one-bit verdict of section 1. Stage 5 averages the verdicts into the LER and
    its error bar.
  </p>
  <p>To run it yourself, you hand qliff a circuit factory and a list of physical rates:</p>
  <pre><code>{`from qliff.qec.threshold import sweep
from qliff.qec.codes import rotated_surface_code

# circuit_fn(p) rebuilds the code at each physical rate
def circuit_fn(p):
    return rotated_surface_code(distance=5, rounds=5, p=p)

curve = sweep(
    circuit_fn,
    p_values=[0.005, 0.01, 0.02, 0.04, 0.08],
    decoder_name="mwpm",   # the default matching decoder
    shots=20000,           # more shots -> tighter error bars
    seed=1234,             # fixed seed -> reproducible curve
)
# -> [(p, ler, stderr), ...]`}</code></pre>
  <p>
    Choosing well: pick several <strong>distances</strong> to expose the crossing; use enough
    <strong>shots</strong> that the rarest LER you care about is resolved (<Math expr={String.raw`N \gtrsim 1/\mathrm{LER}`} />,
    and <Math expr={String.raw`\times\,\gamma^2`} /> more for coherent noise); pick a <strong>decoder</strong>
    matched to your code; and <strong>fix the seed</strong> so the whole sweep is reproducible.
  </p>

  <Callout kind="note" title="The series in one breath">
    Three decoders turn a syndrome into a correction --
    <strong>matching</strong>, <strong>belief propagation</strong>, <strong>tensor networks</strong>.
    Two noise pages make the input honest -- <strong>coherent channels</strong> as signed
    quasiprobabilities, sampled into <strong>weighted trajectories</strong>. This final page is
    the scoreboard: feed decoder and noise into sample → decode → compare, average the verdicts,
    and read the <strong>logical error rate</strong>, its <strong>error bar</strong>, and the
    <strong>threshold</strong> that says whether scaling up will save you.
  </Callout>
</Section>

<style>
  .ctl-row {
    display: flex;
    gap: 10px;
    margin-top: 14px;
  }
  .prose-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px 26px;
    margin-bottom: 18px;
  }
  .stat-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin-top: 14px;
    font-size: 14px;
    color: var(--muted);
  }
  .stat-strip b {
    color: var(--fg);
    font-family: var(--font-mono);
    font-weight: 700;
  }

  /* truth-table */
  .tt {
    display: flex;
    gap: 26px;
    align-items: flex-start;
  }
  .tt-col {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }
  .tt-h {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .tt-cells {
    display: flex;
    gap: 6px;
  }
  .bit {
    width: 38px;
    height: 38px;
    font-family: var(--font-mono);
    font-size: 16px;
    font-weight: 700;
    color: var(--muted);
  }
  .bit.on {
    color: var(--fg);
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-soft);
  }
  .verdict {
    font-family: var(--font-mono);
    font-size: 14px;
    font-weight: 700;
    padding-top: 8px;
  }

  /* coherent cost bars */
  .cost {
    margin-top: 18px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .cost-bar {
    display: grid;
    grid-template-columns: 150px 1fr auto;
    align-items: center;
    gap: 12px;
  }
  .cost-lbl {
    font-size: 13px;
    color: var(--muted);
  }
  .bar {
    height: 12px;
    border-radius: 99px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    border-radius: 99px;
    transition: width var(--dur) var(--ease-out);
  }
  .cost-n {
    font-size: 12.5px;
    color: var(--fg);
    white-space: nowrap;
  }
  .cost-note {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--faint);
    line-height: 1.5;
  }

  /* distance chips */
  .dchips {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
  }
  .dchips-lbl {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .chip {
    font-family: var(--font-mono);
    font-size: 13px;
    padding: 5px 12px;
    opacity: 0.5;
  }
  .chip.on {
    opacity: 1;
    border-color: var(--cc);
    color: var(--cc);
    box-shadow: inset 0 0 0 1px var(--cc);
  }

  .mono {
    font-family: var(--font-mono);
  }
</style>
