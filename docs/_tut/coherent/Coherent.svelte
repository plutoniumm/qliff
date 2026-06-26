<script lang="ts">
  // The Coherent-Noise Engine: how qliff represents NON-Pauli noise (coherent
  // rotations, amplitude damping) as SIGNED quasiprobability mixtures of Clifford
  // gates. The 3D showcase of the series -- a real Three.js Bloch sphere drives the
  // intuition, and every printed weight is the exact value from qliff's
  // noise/channel.py.
  import Section from "$lib/Section.svelte";
  import Math from "$lib/Math.svelte";
  import Slider from "$lib/Slider.svelte";
  import Callout from "$lib/Callout.svelte";
  import Figure from "$lib/Figure.svelte";
  import Worked from "$lib/Worked.svelte";
  import { C } from "$lib/colors";

  import Bloch from "./Bloch.svelte";
  import WeightBars from "./WeightBars.svelte";
  import Plot from "./Plot.svelte";
  import type { Series } from "./Plot.svelte";
  import {
    rotationBranches,
    dampingBranches,
    totalWeight,
    gamma,
    rotationGamma,
    dampingGamma,
  } from "./channel";
  import {
    applyGate,
    applyRz,
    applyDamping,
    norm,
    type Vec3,
    type GateName,
  } from "./bloch";

  const PI = window.Math.PI;
  const fmtAngle = (v: number) => `${v.toFixed(2)} rad`;

  // ---- Section 02: interactive Bloch playground ----------------------------
  // The user applies discrete Cliffords (mutating a base state) and then a live
  // continuous RZ(theta) on top. base = state after clicked gates; live = after RZ.
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

  // ---- Section 04: RZ(theta) decomposition ---------------------------------
  let thetaDec = $state(0.6);
  const rotBranches = $derived(rotationBranches(thetaDec));
  const rotSum = $derived(totalWeight(rotBranches));
  const rotGamma = $derived(gamma(rotBranches));
  const rotHasNeg = $derived(rotBranches.some((b) => b.weight < 0));

  // Bloch view for the decomposition: a |+> vector rotated by thetaDec.
  const decBase: Vec3 = [1, 0, 0];
  const decLive = $derived(applyRz(thetaDec, decBase));

  // ---- Section 03: coherent vs incoherent ----------------------------------
  // Coherent over-rotation: a small RZ(theta) per round, repeated R times. The net
  // unitary is RZ(R*theta); its "error amplitude" (how far it tilts |+>) grows ~
  // R*theta -- LINEAR. A depolarizing flip of "comparable strength" sin^2(theta/2)
  // accumulates as a probability and grows only ~ theta^2 per step.
  const coVsInc: Series[] = (() => {
    const coh: [number, number][] = [];
    const inc: [number, number][] = [];
    for (let i = 0; i <= 60; i++) {
      const th = (i / 60) * (PI / 2);
      // single-shot infidelity-like measures, normalised to [0,1] at theta=pi/2.
      const ampl = window.Math.sin(th); // coherent: error amplitude ~ theta (sin)
      const prob = window.Math.sin(th / 2) ** 2 * 2; // incoherent: ~ theta^2, scaled to meet at pi/2
      coh.push([th, ampl]);
      inc.push([th, window.Math.min(1, prob)]);
    }

    return [
      { pts: coh, color: C.accent2, label: "coherent (amplitude ∝ θ)" },
      { pts: inc, color: C.muted, label: "Pauli approx (prob ∝ θ²)", dash: true },
    ];
  })();
  let thetaCmp = $state(0.5);

  // ---- Section 05: gamma(theta) curve --------------------------------------
  const gammaCurve: Series[] = (() => {
    const pts: [number, number][] = [];
    for (let i = 0; i <= 80; i++) {
      const th = (i / 80) * 2 * PI;
      pts.push([th, rotationGamma(th)]);
    }

    return [{ pts, color: C.accent, label: "γ(θ)" }];
  })();

  // ---- Section 06: amplitude damping ---------------------------------------
  let pDamp = $state(0.3);
  const dampBranches = $derived(dampingBranches(pDamp));
  const dampSum = $derived(totalWeight(dampBranches));
  const dampGamma = $derived(gamma(dampBranches));

  // damping Bloch: pull a |+> state toward |0>.
  const dampBase: Vec3 = [1, 0, 0];
  const dampLive = $derived(applyDamping(pDamp, dampBase));

  const dampGammaCurve: Series[] = (() => {
    const exact: [number, number][] = [];
    const approx: [number, number][] = [];
    for (let i = 0; i <= 80; i++) {
      const p = i / 80;
      exact.push([p, dampingGamma(p)]);
      approx.push([p, 1 + p / 2]);
    }

    return [
      { pts: exact, color: C.accent, label: "γ exact" },
      { pts: approx, color: C.muted, label: "1 + p/2", dash: true },
    ];
  })();

  // small helper for printing a signed weight.
  const sgn = (v: number) => (v >= 0 ? "+" : "−") + window.Math.abs(v).toFixed(3);
</script>

<Section id="intro" step="01" title="Not all noise is a coin flip">
  <p>
    The textbook picture of quantum noise is a coin flip: with some probability a qubit suffers a
    random Pauli <Math expr="X" />, <Math expr="Y" />, or <Math expr="Z" />. That is the world a
    matching or belief-propagation decoder lives in -- independent, <em>stochastic</em>, Pauli errors.
  </p>
  <p>
    Real hardware is sneakier. Two failure modes refuse to be a coin flip:
  </p>
  <ul>
    <li>
      <strong style="color:{C.accent2}">A miscalibrated gate</strong> that <em>always</em> over- or
      under-rotates by a fixed angle -- a <strong>coherent</strong> error
      <Math expr={"e^{-i\\theta P/2}"} />. Nothing is random; the same small tilt happens every single
      shot, and the tilts <em>add up</em>.
    </li>
    <li>
      <strong style="color:{C.x}">Energy quietly leaking</strong> to the environment -- an excited
      <Math expr={"|1\\rangle"} /> decays toward <Math expr={"|0\\rangle"} /> with probability
      <Math expr="p" />. This is <strong>amplitude damping</strong>, and it is not symmetric: it has
      a preferred direction.
    </li>
  </ul>
  <p>
    Neither is a random Pauli flip. A Clifford simulator like <code>qliff</code> can only apply
    Clifford gates to stabilizer states, so at first glance it has no way to represent these channels
    at all. The trick -- the engine of this page -- is to write each one as a <strong>signed</strong>
    mixture of Cliffords. Let us build the intuition on the Bloch sphere first.
  </p>
</Section>

<Section id="bloch" step="02" title="A qubit on the Bloch sphere" wide>
  <div class="prose">
    <p>
      A single qubit's pure state is a point on the unit sphere: <Math expr={"|0\\rangle"} /> at the
      north pole, <Math expr={"|1\\rangle"} /> at the south, <Math expr={"|{+}\\rangle"} /> and friends
      around the equator. Clifford gates are <em>discrete</em> quarter- and half-turns of this
      sphere; a coherent rotation <Math expr={"R_Z(\\theta)"} /> is a <em>continuous</em> turn about the
      <span style="color:{C.fg}">z</span>-axis. Drag to orbit.
    </p>
  </div>

  <Figure
    wide
    title="Bloch playground"
    legend={[
      { color: C.x, label: "x axis (|+⟩)" },
      { color: C.z, label: "y axis (|+i⟩)" },
      { color: C.fg, label: "z axis (|0⟩ / |1⟩)" },
      { color: C.accent, mark: "line", label: "state vector |ψ⟩" },
      { color: C.muted, mark: "dash", label: "ghost (pre-rotation)" },
      { color: C.accent2, mark: "line", label: "RZ(θ) sweep arc" },
    ]}
    caption="Click Cliffords to apply discrete moves; drag the θ slider to apply a continuous RZ(θ) on top. The faint grey arrow + cyan arc show where the state was before the live rotation."
  >
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
        <Slider bind:value={thetaPlay} min={0} max={2 * PI} step={0.01} label="coherent RZ(θ)" format={fmtAngle} />
        <p class="hint">
          A <em>tiny</em> θ looks harmless. But the same miscalibration fires every round -- apply it
          repeatedly and the arrow sweeps all the way around. Coherent errors accumulate in the
          <strong style="color:{C.accent2}">amplitude</strong>, not the probability.
        </p>
      </div>
    </div>
  </Figure>

  <div class="prose">
    <Callout kind="note" title="Why the amplitude matters">
      <p>
        After <Math expr="R" /> identical small rotations the net tilt is <Math expr={"R\\theta"} /> --
        it grows <em>linearly</em>. If you instead modelled the same gate as a random Pauli flip, the
        errors would add in <em>probability</em> and grow far slower. That mismatch is the whole
        problem, and the next section makes it quantitative.
      </p>
    </Callout>
  </div>
</Section>

<Section id="coherent-vs-incoherent" step="03" title="Coherent vs. incoherent: amplitude beats probability">
  <p>
    Take an over-rotation by angle <Math expr={"\\theta"} /> and ask: how big is the error? There are
    two honest ways to measure "size", and they disagree.
  </p>
  <ul>
    <li>
      A <strong style="color:{C.accent2}">coherent</strong> rotation tilts the state by an
      <em>amplitude</em> that grows like <Math expr={"\\sin\\theta \\approx \\theta"} /> for small
      <Math expr={"\\theta"} />.
    </li>
    <li>
      The "equivalent" <strong style="color:{C.muted}">Pauli (depolarizing) approximation</strong>
      flips with a <em>probability</em> like <Math expr={"\\sin^2(\\theta/2) \\approx \\theta^2/4"} /> --
      quadratically smaller for small angles.
    </li>
  </ul>

  <Figure
    title="Amplitude vs. probability"
    legend={[
      { color: C.accent2, mark: "line", label: "coherent amplitude ∝ θ" },
      { color: C.muted, mark: "dash", label: "Pauli prob. ∝ θ²" },
      { color: C.muted, mark: "dash", label: "θ marker (slider)" },
    ]}
    caption="Coherent error amplitude (solid cyan) vs. the probability of the matched Pauli approximation (dashed grey), as a function of the rotation angle θ (radians). Near θ=0 the Pauli model under-counts the error by a whole power of θ."
  >
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
      <Slider bind:value={thetaCmp} min={0} max={PI / 2} step={0.01} label="θ" format={fmtAngle} />
    </div>
  </Figure>

  <Callout kind="warn" title="A Pauli approximation is dishonest">
    <p>
      Because coherent errors grow in amplitude (<Math expr={"\\propto\\theta"} />) while a same-strength
      Pauli error grows in probability (<Math expr={"\\propto\\theta^2"} />), replacing a coherent channel
      by "the nearest Pauli channel" systematically <em>under-counts</em> the damage -- and the gap is
      worst exactly where you care, at small per-gate angles that pile up over thousands of rounds.
      An honest simulator must keep the coherence. That is what the quasiprobability trick buys us.
    </p>
  </Callout>
</Section>

<Section id="decomposition" step="04" title="The Clifford trick: a signed mix for RZ(θ)" wide>
  <div class="prose">
    <p>
      Here is the key move. The non-Clifford rotation <Math expr={"R_Z(\\theta)=e^{-i\\theta Z/2}"} /> is
      written by <code>qliff</code> as a <strong>signed quasiprobability mixture</strong> over the four
      Cliffords <em>diagonal in Z</em> -- the identity <Math expr="I" />, the phase flip
      <Math expr="Z" />, and the <Math expr={"\\pm 90^\\circ"} /> phase gates <Math expr="S" /> and
      <Math expr={"S^\\dagger"} />:
    </p>
    <Math
      display
      expr={String.raw`R_Z(\theta)\;\approx\;\sum_k w_k\,C_k,\qquad C_k\in\{\,I,\;Z,\;S,\;S^\dagger\,\}.`}
    />
    <p>
      The <Math expr="w_k" /> are real but may be <em>negative</em>: this is a quasiprobability, not a
      probability. With <Math expr={"c=\\cos\\theta"} />, <Math expr={"s=\\sin\\theta"} /> and the shared
      offset <Math expr={"\\beta=\\tfrac{1-c-s}{4}"} />, the four branch weights are exactly
    </p>
    <Math
      display
      expr={"w_I=\\beta+c,\\quad w_Z=\\beta,\\quad w_S=\\beta+s,\\quad w_{S^\\dagger}=\\beta."}
    />
    <p>
      They always sum to <Math expr={"4\\beta + c + s = 1"} /> -- the channel is trace-preserving -- but
      <em>individual</em> weights go <span style="color:{C.bad}">negative</span> as soon as
      <Math expr={"\\theta"} /> is large enough. (The <Math expr="R_X" /> version is the same mixture
      wrapped in <Math expr="H" /> on each side, since <Math expr={"R_X = H\\,R_Z\\,H"} />.)
    </p>
  </div>

  <Figure
    wide
    title="RZ(θ) branch weights"
    legend={[
      { color: C.accent, mark: "box", label: "positive weight w_k > 0" },
      { color: C.bad, mark: "box", label: "negative weight w_k < 0" },
      { color: C.accent, mark: "line", label: "rotated |ψ⟩" },
      { color: C.muted, mark: "dash", label: "ghost |+⟩ (θ=0)" },
      { color: C.accent2, mark: "line", label: "sweep arc" },
    ]}
    caption={"Bars are the four signed weights w_k for the Cliffords {I, Z, S, S†}; bar SIGN = quasiprobability sign. Bars above the line are positive (sampled with prob ∝ |w|/γ); bars below are NEGATIVE -- the sign problem -- and carry a minus sign into the sampled trajectory's importance weight."}
  >
    <div class="panel">
      <div class="stage small">
        <Bloch vec={decLive} ghost={decBase} sweep={thetaDec} label="RZ rotation on the Bloch sphere" />
      </div>
      <div class="controls">
        <WeightBars branches={rotBranches} max={1.2} height={210} />
        <Slider bind:value={thetaDec} min={0} max={2 * PI} step={0.01} label="rotation angle θ" format={fmtAngle} />
        <div class="ledger mono">
          <span>w<sub>I</sub> = {sgn(rotBranches[0].weight)}</span>
          <span class:neg={rotBranches[1].weight < 0}>w<sub>Z</sub> = {sgn(rotBranches[1].weight)}</span>
          <span class:neg={rotBranches[2].weight < 0}>w<sub>S</sub> = {sgn(rotBranches[2].weight)}</span>
          <span class:neg={rotBranches[3].weight < 0}>w<sub>S†</sub> = {sgn(rotBranches[3].weight)}</span>
        </div>
        <div class="totals">
          <span>Σ w = <strong style="color:{C.ok}">{rotSum.toFixed(3)}</strong> (always 1)</span>
          <span>Σ |w| = γ = <strong style="color:{rotHasNeg ? C.bad : C.fg}">{rotGamma.toFixed(3)}</strong></span>
        </div>
      </div>
    </div>
  </Figure>

  <div class="prose">
    <Worked title="Decompose RZ(θ) at θ = π/8 = 22.5°">
      <ol>
        <li>
          Evaluate the trig at <Math expr={String.raw`\theta=\pi/8`} />:
          <Math expr={String.raw`c=\cos\theta\approx 0.9239`} />,
          <Math expr={String.raw`s=\sin\theta\approx 0.3827`} />.
        </li>
        <li>
          Shared offset
          <Math expr={String.raw`\beta=\tfrac{1-c-s}{4}=\tfrac{1-0.9239-0.3827}{4}\approx -0.0766`} />
          -- already negative.
        </li>
        <li>
          Branch weights from <Math expr={String.raw`w_I=\beta+c,\;w_Z=\beta,\;w_S=\beta+s,\;w_{S^\dagger}=\beta`} />:
          <Math expr={String.raw`w_I\approx +0.847`} />,
          <Math expr={String.raw`w_Z\approx -0.077`} />,
          <Math expr={String.raw`w_S\approx +0.306`} />,
          <Math expr={String.raw`w_{S^\dagger}\approx -0.077`} />.
        </li>
        <li>
          Trace check -- the signed sum is exactly one:
          <Math expr={String.raw`\textstyle\sum_k w_k = 0.847-0.077+0.306-0.077 = 1.000`} />.
        </li>
        <li>
          Negativity -- the absolute values sum to more:
          <Math expr={String.raw`\gamma=\textstyle\sum_k|w_k| = 0.847+0.077+0.306+0.077 \approx 1.307`} />.
        </li>
      </ol>
      {#snippet result()}
        Two of the four weights (<Math expr={String.raw`w_Z,w_{S^\dagger}`} />) are negative, so this
        is genuinely coherent. The sampler pays <Math expr={String.raw`\gamma\approx \mathbf{1.31}`} />
        per such location and a variance blow-up of
        <Math expr={String.raw`\gamma^2\approx \mathbf{1.71}`} /> -- already at a modest 22.5° tilt.
      {/snippet}
    </Worked>

    <Callout kind="key" title="Positive mixture impossible, signed mixture fine">
      <p>
        A genuine probability mixture of Cliffords can only ever produce another Clifford (or a
        stochastic Pauli) channel -- it can never reproduce a true rotation. Allowing
        <strong>negative</strong> weights breaks that barrier: the signed combination reconstructs
        <Math expr={"R_Z(\\theta)"} /> exactly. The price is the negativity, which we name next.
      </p>
    </Callout>
  </div>
</Section>

<Section id="negativity" step="05" title="Negativity γ -- the cost of non-Cliffordness">
  <p>
    The weights sum to <Math expr="1" />, but their <em>absolute</em> values sum to something
    larger. Define the <strong>negativity</strong>
  </p>
  <Math display expr={"\\gamma \\;=\\; \\sum_k |w_k| \\;\\ge\\; 1,"} />
  <p>
    with equality exactly when every weight is non-negative (a true probability mixture). At
    <Math expr={"\\theta=0"} /> the rotation is the identity, all weight sits on <Math expr="I" />, and
    <Math expr={"\\gamma=1"} /> -- free. As <Math expr={"\\theta"} /> grows, weights dip negative and
    <Math expr={"\\gamma"} /> climbs.
  </p>

  <Figure
    title="Negativity γ(θ)"
    legend={[
      { color: C.accent, mark: "line", label: "γ(θ) = Σ|w_k|" },
      { color: C.muted, mark: "dash", label: "θ marker (slider)" },
    ]}
    caption="Negativity γ (unitless) vs. rotation angle θ (radians) for the RZ decomposition. γ=1 at θ=0, and rises as branch weights go negative. The sampler later draws a branch with probability |w|/γ and carries a signed importance weight of magnitude γ -- so larger γ means more sampling variance downstream."
  >
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
      <Slider bind:value={thetaDec} min={0} max={2 * PI} step={0.01} label="rotation angle θ" format={fmtAngle} />
    </div>
  </Figure>

  <Callout kind="note" title="γ is the overhead, not the error">
    <p>
      Negativity does not make the simulation <em>wrong</em> -- the answer it converges to is exact.
      It makes it <em>expensive</em>: each non-Pauli location multiplies the variance of a sampled
      estimate by roughly <Math expr={"\\gamma^2"} />, so you need more shots for the same error bar.
      <Math expr={"\\gamma"} /> is the honest bookkeeping of "how non-Clifford is this channel". The
      <a href="./noise">noise-sampling</a> page shows how that importance weight is actually carried.
    </p>
  </Callout>
</Section>

<Section id="damping" step="06" title="Amplitude damping: a one-way pull to |0⟩" wide>
  <div class="prose">
    <p>
      Energy loss is different from a rotation: it is irreversible and it has a direction. Amplitude
      damping with loss probability <Math expr="p" /> is decomposed exactly over just three
      Cliffords -- the identity, a phase flip <Math expr="Z" />, and a <strong>reset</strong>
      <Math expr="R" /> to <Math expr={"|0\\rangle"} />:
    </p>
    <Math
      display
      expr={"q_I=\\tfrac{(1-p)+\\sqrt{1-p}}{2},\\quad q_Z=\\tfrac{(1-p)-\\sqrt{1-p}}{2},\\quad q_R=p."}
    />
    <p>
      The middle weight <Math expr="q_Z" /> is <span style="color:{C.bad}">negative</span> for every
      <Math expr="0<p<1" />, so damping is intrinsically non-Pauli, just like the rotation. The overhead
      is <Math expr={String.raw`\gamma = \sqrt{1-p} + p`} />: small at first
      (<Math expr={String.raw`\gamma \approx 1 + \tfrac{p}{2}`} /> for small <Math expr="p" />), it
      peaks at <Math expr={String.raw`\gamma = 1.25`} /> near <Math expr={String.raw`p = \tfrac34`} />,
      then eases back to <Math expr="1" /> as <Math expr={String.raw`p \to 1`} /> (a full reset is just
      the Clifford <Math expr="R" />, no negativity).
      On the sphere, damping does not rotate the state; it <em>shrinks</em> the equatorial component
      and <em>pulls</em> the vector toward the north pole <Math expr={"|0\\rangle"} />.
    </p>
  </div>

  <Figure
    wide
    title="Damping branch weights"
    legend={[
      { color: C.accent, mark: "box", label: "positive weight" },
      { color: C.bad, mark: "box", label: "negative q_Z" },
      { color: C.accent, mark: "line", label: "damped |ψ⟩ (shrinks toward |0⟩)" },
      { color: C.fg, label: "z axis (|0⟩ pole)" },
    ]}
    caption={"Bars are the three signed weights for the Cliffords {I, Z, R}; bar SIGN = quasiprobability sign. Amplitude damping pulls the Bloch vector toward |0> (the arrow shortens and tilts up, a mixed state). The weights q_I, q_Z, q_R include the negative q_Z; gamma = sum|q_k| is the (small) sampling overhead."}
  >
    <div class="panel">
      <div class="stage small">
        <Bloch vec={dampLive} label="amplitude damping on the Bloch sphere" />
      </div>
      <div class="controls">
        <WeightBars branches={dampBranches} max={1} height={200} />
        <Slider bind:value={pDamp} min={0} max={0.99} step={0.01} label="loss probability p" format={(v) => v.toFixed(2)} />
        <div class="ledger mono">
          <span>q<sub>I</sub> = {sgn(dampBranches[0].weight)}</span>
          <span class="neg">q<sub>Z</sub> = {sgn(dampBranches[1].weight)}</span>
          <span>q<sub>R</sub> = {sgn(dampBranches[2].weight)}</span>
        </div>
        <div class="totals">
          <span>Σ q = <strong style="color:{C.ok}">{dampSum.toFixed(3)}</strong></span>
          <span>γ = <strong style="color:{C.accent}">{dampGamma.toFixed(3)}</strong></span>
          <span>|r| = <strong>{norm(dampLive).toFixed(3)}</strong> (state purity)</span>
        </div>
      </div>
    </div>
  </Figure>

  <div class="prose">
    <Figure
      title="Damping negativity γ(p)"
      legend={[
        { color: C.accent, mark: "line", label: "γ exact = Σ|q_k|" },
        { color: C.muted, mark: "dash", label: "1 + p/2 estimate" },
        { color: C.muted, mark: "dash", label: "p marker (slider)" },
      ]}
      caption="Negativity gamma (unitless) vs. loss probability p (unitless). The exact gamma(p) = sqrt(1-p) + p (accent) matches the 1 + p/2 small-p estimate (dashed) near p = 0, then turns over: it peaks at gamma = 1.25 around p = 3/4 and falls back to 1 at p = 1."
    >
      <div class="plotwrap">
        <Plot
          series={dampGammaCurve}
          xmin={0}
          xmax={1}
          ymin={1}
          ymax={1.8}
          marker={pDamp}
          xlabel="loss probability p"
          ylabel="γ"
          height={150}
        />
      </div>
    </Figure>
  </div>
</Section>

<Section id="why-qec" step="07" title="Why QEC must take this seriously">
  <p>
    Coherent errors do not just sit there -- they <em>conspire</em>. Because each round adds the same
    tilt in amplitude, the contributions can align across many rounds and across many qubits,
    producing a logical failure rate well above what the matched depolarizing model predicts. A
    simulator that quietly Pauli-approximates its noise will report a threshold that is too
    optimistic.
  </p>
  <p>
    <code>qliff</code> refuses to cheat. It carries the real channels -- coherent
    <Math expr="R_Z/R_X" /> rotations and amplitude damping -- as the signed quasiprobability
    mixtures you just built, and pays the negativity <Math expr={"\\gamma"} /> honestly. Two pieces
    downstream make that practical:
  </p>
  <ul>
    <li>
      The <a href="./noise">trajectory sampler</a> draws one branch per location with probability
      <Math expr={"|w|/\\gamma"} /> and threads a <strong>signed importance weight</strong> of magnitude
      <Math expr={"\\gamma"} /> through the shot -- so a stochastic Clifford simulator reproduces a
      non-Pauli channel in expectation.
    </li>
    <li>
      A dedicated <a href="./tn"><code>coherent</code> tensor-network decoder</a> contracts the
      circuit's <em>signed</em> branch weights directly. A detector-error-model decoder (MWPM, BP+OSD)
      can only encode independent Pauli noise; it has no slot for a negative weight, so it literally
      cannot represent these channels. The coherent decoder can.
    </li>
  </ul>

  <Callout kind="key" title="Recap">
    <p>
      Non-Pauli noise -- coherent rotations and amplitude damping -- cannot be a <em>positive</em>
      mixture of Cliffords, but it <em>can</em> be a <strong>signed</strong> one. The weights still
      sum to 1, yet <Math expr={"\\sum|w|=\\gamma\\ge 1"} /> measures the non-Cliffordness. Coherent errors
      accumulate in amplitude (<Math expr={"\\propto\\theta"} />), beating a same-size Pauli flip
      (<Math expr={"\\propto\\theta^2"} />), so an honest QEC simulator models them exactly rather than
      flattening them into coin flips.
    </p>
  </Callout>
</Section>

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

  .stage.small {
    height: 320px;
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

  .plotwrap {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .ledger {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    font-size: 13px;
    color: var(--fg);
  }

  .ledger .neg {
    color: var(--bad);
  }

  .totals {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
    font-size: 13px;
    color: var(--muted);
    padding-top: 4px;
    border-top: 1px solid var(--line);
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
