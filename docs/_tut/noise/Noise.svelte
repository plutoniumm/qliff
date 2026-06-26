<script lang="ts">
  // How the simulator simulates noise: channels -> branches -> Monte-Carlo
  // stabilizer trajectories -> detection events, plus importance weighting for
  // non-Pauli noise. Faithful to qliff/noise/channel.py + qliff/qec/sampler.py.
  //
  // All sampling uses the seeded mulberry32 RNG so every panel is reproducible:
  // set a seed, get the exact same shot / histogram. No $effect writes to a
  // $state it reads -- sampled results are pure $derived of (params, seed).
  import Section from "$lib/Section.svelte";
  import Tex from "$lib/Math.svelte";
  import Slider from "$lib/Slider.svelte";
  import Scrubber from "$lib/Scrubber.svelte";
  import Callout from "$lib/Callout.svelte";
  import Figure from "$lib/Figure.svelte";
  import Worked from "$lib/Worked.svelte";
  import { C, withAlpha } from "$lib/colors";
  import { mulberry32 } from "$lib/rng";
  import Trajectory from "./Trajectory.svelte";
  import {
    makeChannel,
    sampleChannel,
    gamma,
    type Branch,
    type Circuit,
    type ChannelKind,
  } from "./channels";

  function pct(x: number): string {
    return (x * 100).toFixed(2) + "%";
  }
  function branchColor(pauli: string): string {
    const p = pauli.replace(/[^XYZ]/g, "");
    if (p.includes("X")) {
      return C.x;
    }
    if (p.includes("Y")) {
      return C.y;
    }
    if (p.includes("Z")) {
      return C.z;
    }
    return C.muted;
  }

  // ===== Section 01: scaling =====
  let nQubits = $state(40);
  // state-vector amplitudes = 2^n; stabilizer memory ~ n^2 (a tableau is 2n x 2n
  // bits). We show the magnitudes so the gap is visceral.
  const svBits = $derived(nQubits); // log2(2^n) = n -> 2^n amplitudes
  const svDigits = $derived(Math.floor(nQubits * Math.log10(2)));
  const stabCells = $derived(2 * nQubits * (2 * nQubits + 1));

  // ===== Section 02: the menu (DEPOLARIZE1) =====
  let menuP = $state(0.12);
  const menuBranches = $derived(makeChannel("DEPOLARIZE1", menuP, [0]).branches());

  // ===== Section 03: one noisy shot (trajectory) =====
  let trajP = $state(0.18);
  let trajSeed = $state(7);
  let trajLoc = $state(0);

  // A small rep-code-style round: 4 data qubits in a line, each gets a
  // DEPOLARIZE1 location after preparation; 3 Z-checks read parities of
  // neighbours. We only need the noise locations to show a trajectory.
  const trajCircuit = $derived<Circuit>(buildRepCircuit(4, trajP));

  function buildRepCircuit(nData: number, p: number): Circuit {
    const instructions = [];
    for (let q = 0; q < nData; q += 1) {
      instructions.push({
        type: "noise" as const,
        channel: makeChannel("DEPOLARIZE1", p, [q]),
        label: `DEPOLARIZE1 q${q}`,
      });
    }
    // Z-checks between neighbours -> detectors over (q, q+1).
    const detectors: number[][] = [];
    for (let q = 0; q < nData - 1; q += 1) {
      detectors.push([q, q + 1]);
    }
    // logical observable = parity of all data qubits.
    const observables = [Array.from({ length: nData }, (_, q) => q)];

    return { numQubits: nData, instructions, detectors, observables };
  }
  const trajLabels = ["q0", "q1", "q2", "q3"];

  // ===== Section 04: menus & law of large numbers =====
  let lawKind = $state<ChannelKind>("DEPOLARIZE1");
  let lawP = $state(0.15);
  let lawN = $state(400);
  let lawSeed = $state(3);

  const lawChannel = $derived(
    makeChannel(lawKind, lawP, lawKind === "DEPOLARIZE2" ? [0, 1] : [0]),
  );
  const lawBranches = $derived(lawChannel.branches());

  // Empirical histogram of which branch fires over lawN shots (seeded).
  const lawHist = $derived.by(() => {
    const branches = lawBranches;
    const counts = new Array(branches.length).fill(0);
    const rng = mulberry32(lawSeed >>> 0 || 1);
    for (let s = 0; s < lawN; s += 1) {
      const res = sampleChannel(branches, rng);
      counts[res.index] += 1;
    }
    return counts.map((c) => c / lawN);
  });

  // For DEPOLARIZE2 we group the 16 branches into I / single-Pauli / pair for a
  // readable histogram; otherwise show every branch.
  const lawGrouped = $derived.by(() => {
    if (lawKind !== "DEPOLARIZE2") {
      return lawBranches.map((b, i) => ({
        label: b.pauli,
        theory: Math.abs(b.weight),
        empirical: lawHist[i],
      }));
    }
    // group by "I", "single", "pair"
    const groups = { I: [0, 0], single: [0, 0], pair: [0, 0] };
    lawBranches.forEach((b, i) => {
      const nonI = b.pauli.replace(/I/g, "").length;
      const key = nonI === 0 ? "I" : nonI === 1 ? "single" : "pair";
      groups[key][0] += Math.abs(b.weight);
      groups[key][1] += lawHist[i];
    });
    return [
      { label: "II (no fault)", theory: groups.I[0], empirical: groups.I[1] },
      { label: "single Pauli ×6", theory: groups.single[0], empirical: groups.single[1] },
      { label: "Pauli pair ×9", theory: groups.pair[0], empirical: groups.pair[1] },
    ];
  });
  const lawMax = $derived(
    Math.max(0.001, ...lawGrouped.map((g) => Math.max(g.theory, g.empirical))),
  );

  // ===== Section 05: trajectory -> syndrome =====
  let synErrors = $state([false, false, true, false, false]); // 5 data qubits
  function toggleErr(q: number): void {
    synErrors = synErrors.map((e, i) => (i === q ? !e : e));
  }
  // Z-checks between neighbours fire iff the two neighbours' X-error parity is 1
  // (= a domain wall). Reference (noiseless) = all-0, so detection event = parity.
  const synDefects = $derived(
    Array.from({ length: synErrors.length - 1 }, (_, i) =>
      (synErrors[i] ? 1 : 0) ^ (synErrors[i + 1] ? 1 : 0),
    ),
  );

  // ===== Section 06: the sign problem (non-Pauli) =====
  let signKind = $state<"RZ" | "AMPLITUDE_DAMP">("RZ");
  let signParam = $state(0.6); // theta for RZ, p for damping
  let signN = $state(500);
  let signSeed = $state(11);

  const signChannel = $derived(makeChannel(signKind, signParam, [0]));
  const signBranches = $derived(signChannel.branches());
  const signGamma = $derived(gamma(signBranches));

  // The "quantity" we estimate: probability that the channel leaves a Z error on
  // the qubit (i.e. the branch's net effect anticommutes with X). For RZ/{I,Z,S,
  // S†} the Z-error indicator is 1 for the Z branch (and S/S† carry a phase but
  // we treat the demonstrable observable: did a Z fire). The TRUE value is the
  // signed sum over branches of w * indicator -- the quasiprobability mean.
  function zIndicator(b: Branch): number {
    return b.pauli === "Z" ? 1 : 0;
  }
  const signTrue = $derived(
    signBranches.reduce((s, b) => s + b.weight * zIndicator(b), 0),
  );

  // Importance estimate: draw branch w.p. |w|/gamma, carry factor sign(w)*gamma,
  // weighted mean of factor*indicator. Also a NAIVE estimate that ignores the
  // sign/gamma (treats |w|/gamma as a probability) to show the bias.
  const signRun = $derived.by(() => {
    const branches = signBranches;
    const rng = mulberry32(signSeed >>> 0 || 1);
    let wsum = 0; // sum of factor*indicator
    let naive = 0; // sum of indicator (ignores weight)
    let w2 = 0; // sum of (factor*indicator)^2 for variance
    for (let s = 0; s < signN; s += 1) {
      const res = sampleChannel(branches, rng);
      const ind = zIndicator(res.branch);
      const contrib = res.factor * ind;
      wsum += contrib;
      w2 += contrib * contrib;
      naive += ind;
    }
    const mean = wsum / signN;
    const naiveMean = naive / signN;
    const variance = Math.max(0, w2 / signN - mean * mean);
    const stderr = Math.sqrt(variance / signN);
    return { mean, naiveMean, stderr };
  });

  // axis range + projection for the variance number-line (kept in the script so
  // the markup has no @const directly under a plain element).
  const signLo = $derived(
    Math.min(signTrue, signRun.mean - 2 * signRun.stderr, signRun.naiveMean) - 0.05,
  );
  const signHi = $derived(
    Math.max(signTrue, signRun.mean + 2 * signRun.stderr, signRun.naiveMean) + 0.05,
  );
  const signSpan = $derived(Math.max(0.001, signHi - signLo));
  function signX(v: number): number {
    return ((v - signLo) / signSpan) * 100;
  }
</script>

<Section id="scaling" step="01" title="Why you can't just store the state">
  <p>
    A quantum computer with <Tex expr="n" /> qubits lives in a space of
    <Tex expr="2^n" /> complex amplitudes. To simulate it the brute-force way you
    write down all of them -- a <em>state vector</em>. That is fine for a toy, and
    catastrophic for a code: a few thousand qubits would need more numbers than
    there are atoms in the universe.
  </p>

  <Figure
    title="Memory blow-up"
    legend={[
      { color: C.bad, label: "state vector -- 2ⁿ amplitudes" },
      { color: C.ok, label: "stabilizer tableau -- ~n² bits" },
    ]}
    caption="State-vector amplitudes (2ⁿ) versus a stabilizer tableau (~n² bits). Drag the qubit count."
  >
    <div class="scale-demo">
      <Slider bind:value={nQubits} min={2} max={120} step={1} label="qubits n" />
      <div class="scale-rows">
        <div class="scale-row">
          <span class="scale-name">state vector</span>
          <span class="scale-val mono" style={`color:${C.bad}`}>
            2<sup>{svBits}</sup> ≈ 10<sup>{svDigits}</sup> amplitudes
          </span>
        </div>
        <div class="scale-row">
          <span class="scale-name">stabilizer tableau</span>
          <span class="scale-val mono" style={`color:${C.ok}`}>
            {stabCells.toLocaleString()} bits
          </span>
        </div>
      </div>
    </div>
  </Figure>

  <p>
    The escape hatch is the <strong>Gottesman-Knill theorem</strong>: a circuit
    built only from <em>Clifford</em> gates, acting on a <em>stabilizer</em>
    state, can be simulated in polynomial memory and time -- you track an
    <Tex expr="\sim n^2" /> bit tableau instead of <Tex expr="2^n" /> numbers.
    qliff's Rust core stores that tableau column-major so each shot is fast, and
    shots are embarrassingly parallel.
  </p>

  <Callout kind="key" title="The constraint this puts on noise">
    Everything the simulator does -- including the noise -- must be expressible as
    <strong>Clifford pieces</strong>. The rest of this page is about how arbitrary
    physical noise gets squeezed into that mould, one Clifford branch at a time.
    That is exactly why qliff can run QEC at a scale a state-vector simulator
    simply cannot reach.
  </Callout>
</Section>

<Section id="menu" step="02" title="A channel is a menu of branches">
  <p>
    A noise <strong>channel</strong> is just a menu. Each line on the menu is a
    <strong>branch</strong>: a weight and a little list of Clifford gates to
    apply. The first line is always the <em>no-fault</em> branch (do nothing).
    Per noise location, per shot, the simulator picks <strong>exactly one</strong>
    line and applies it. That single choice is what makes a trajectory.
  </p>
  <p>
    Written out, a channel <Tex expr={String.raw`\mathcal{E}`} /> applies branch
    <Tex expr="k" /> -- a Clifford/Pauli operator <Tex expr="C_k" /> -- to the state
    <Tex expr={String.raw`\rho`} /> with weight <Tex expr="w_k" />:
  </p>
  <Tex
    display
    expr={String.raw`\mathcal{E}(\rho)\;=\;\sum_k w_k\, C_k\,\rho\, C_k^{\dagger},\qquad \sum_k w_k = 1,\qquad C_0 = I\ (\text{no fault, first}).`}
  />
  <p>
    Here <Tex expr="w_k" /> is the weight of branch <Tex expr="k" />, <Tex expr="C_k" />
    its Clifford gate(s), and the total weight is always <Tex expr="1" /> (the
    channel preserves probability). For a <em>Pauli</em> channel every
    <Tex expr={String.raw`w_k \ge 0`} />, so the weights are a genuine probability
    distribution and you can sample straight from them.
  </p>
  <p>
    The simplest example is single-qubit depolarizing noise,
    <code>DEPOLARIZE1(p)</code>: with probability <Tex expr="1-p" /> nothing
    happens, and otherwise an <Tex expr="X" />, <Tex expr="Y" />, or
    <Tex expr="Z" /> fires, each with probability <Tex expr="p/3" />. So
    <Tex expr={String.raw`w_0 = 1-p`} /> on <Tex expr="C_0 = I" /> and
    <Tex expr={String.raw`w_X = w_Y = w_Z = p/3`} />.
  </p>

  <Figure
    title="DEPOLARIZE1 menu"
    legend={[
      { color: C.muted, label: "I -- no-fault branch (w₀ = 1−p)" },
      { color: C.x, label: "X branch (p/3)" },
      { color: C.y, label: "Y branch (p/3)" },
      { color: C.z, label: "Z branch (p/3)" },
    ]}
    caption="DEPOLARIZE1(p) as a labelled menu. Each bar's length is its weight wₖ; they sum to 1."
  >
    <div class="menu-demo">
      <Slider bind:value={menuP} min={0} max={0.6} step={0.005} label="error rate p" format={(v) => v.toFixed(3)} />
      <div class="menu-list">
        {#each menuBranches as b, i (i)}
          <div class="menu-item">
            <span class="menu-lbl mono" style={`color:${i === 0 ? C.muted : branchColor(b.pauli)}`}>
              {i === 0 ? "I (no fault)" : `${b.pauli} error`}
            </span>
            <div class="menu-track">
              <div
                class="menu-fill"
                style={`width:${b.weight * 100}%; background:${
                  i === 0 ? withAlpha(C.muted, 0.4) : withAlpha(branchColor(b.pauli), 0.7)
                }`}
              ></div>
            </div>
            <span class="menu-w mono">{b.weight.toFixed(3)}</span>
          </div>
        {/each}
      </div>
    </div>
  </Figure>

  <p>
    The weights are a genuine probability distribution: non-negative and summing
    to one. We'll see in a moment that <em>not all</em> physical noise is so
    polite -- but Pauli channels like this one are, and they cover the bulk of QEC
    benchmarking.
  </p>
</Section>

<Section id="trajectory" step="03" title="One noisy shot">
  <p>
    Now put several noise locations in a row -- one after each qubit of a tiny
    4-qubit line -- and run a single shot. Pick a <strong>seed</strong> and step
    through the locations. At each one the simulator rolls a die and reads the
    menu: it draws a threshold uniformly on <Tex expr="[0,\gamma)" /> and walks
    the branches, accumulating <Tex expr="|w|" />, until it passes the
    threshold. For a Pauli channel <Tex expr="\gamma=1" />, so this is just
    "spin the wheel".
  </p>

  <Callout kind="note" title="The exact rule (qliff's Channel.sample)">
    <Tex
      display
      expr={String.raw`\gamma=\textstyle\sum_k |w_k|,\qquad u\sim\mathcal{U}[0,1),\qquad t = u\,\gamma,\qquad \text{pick the first } k \text{ with } \sum_{j\le k}|w_j|\ge t.`}
    />
    Here <Tex expr="u" /> is the uniform draw <code>rng()</code>, <Tex expr="t" /> the
    threshold on <Tex expr="[0,\gamma)" />, and we walk the cumulative
    <Tex expr={String.raw`\sum_{j\le k}|w_j|`} /> until it covers <Tex expr="t" />. The
    location then carries the factor <Tex expr={String.raw`\operatorname{sign}(w_k)\,\gamma`} />
    (here always <Tex expr="1" />, since <Tex expr={String.raw`\gamma=1`} /> for a Pauli
    channel) and applies that branch's Clifford ops.
  </Callout>

  <Figure
    wide
    title="One seeded trajectory"
    legend={[
      { color: C.muted, mark: "box", label: "location not yet revealed (?)" },
      { color: C.ok, mark: "ring", label: "fired I -- no fault" },
      { color: C.x, mark: "box", label: "fired X" },
      { color: C.y, mark: "box", label: "fired Y" },
      { color: C.z, mark: "box", label: "fired Z" },
      { color: C.fg, mark: "line", label: "dice marker t = u·γ" },
      { color: C.accent, mark: "ring", label: "current location" },
    ]}
    caption="A single seeded stabilizer trajectory. The bar shows the γ-scaled |wₖ| segments; the marker is the draw t = u·γ. Same seed ⇒ same shot, every time."
  >
    <div class="traj-wrap">
      <div class="traj-controls">
        <Slider bind:value={trajSeed} min={0} max={9999} step={1} label="seed" />
        <Slider bind:value={trajP} min={0.02} max={0.4} step={0.005} label="error rate p" format={(v) => v.toFixed(3)} />
        <Scrubber bind:value={trajLoc} min={0} max={4} label="location" />
      </div>
      <Trajectory circuit={trajCircuit} seed={trajSeed} bind:loc={trajLoc} qubitLabels={trajLabels} />
    </div>
  </Figure>

  <p>
    Reset the seed and replay: you get the identical sequence of dice rolls and
    fired branches. That reproducibility is what lets a researcher pin down,
    rerun, and debug a single rare failure out of billions of shots.
  </p>
</Section>

<Section id="law" step="04" title="The menus, and the law of large numbers">
  <p>
    Every Pauli instruction qliff understands is one of these menus:
  </p>
  <table>
    <thead>
      <tr><th>instruction</th><th>branches</th><th>weight each</th></tr>
    </thead>
    <tbody>
      <tr><td><code>DEPOLARIZE1(p)</code></td><td>I, X, Y, Z</td><td><Tex expr="1-p" /> then <Tex expr="p/3" /></td></tr>
      <tr><td><code>DEPOLARIZE2(p)</code></td><td>II + the 15 two-qubit pairs</td><td><Tex expr="1-p" /> then <Tex expr="p/15" /></td></tr>
      <tr><td><code>X_ERROR(p)</code></td><td>I, X</td><td><Tex expr="1-p,\; p" /></td></tr>
      <tr><td><code>Z_ERROR(p)</code></td><td>I, Z</td><td><Tex expr="1-p,\; p" /></td></tr>
    </tbody>
  </table>

  <p>
    Sampling is honest only in aggregate: any single shot is random, but as you
    draw more shots the empirical fraction of times each branch fires converges
    to its weight. Crank <Tex expr="N" /> and watch the bars settle.
  </p>

  <Figure
    wide
    title="Law of large numbers"
    legend={[
      { color: C.lineStrong, mark: "dash", label: "theory weight |wₖ| (outline)" },
      { color: C.accent, mark: "box", label: "empirical fraction (N shots)" },
    ]}
    caption="Per branch: theory weight |wₖ| (dashed outline) vs. empirical fraction of N seeded shots that fired it. x-axis = probability (fraction of shots, 0-1). More shots ⇒ tighter match."
  >
    <div class="law-wrap">
      <div class="law-controls">
        <label class="seg-pick">
          {#each (["DEPOLARIZE1", "DEPOLARIZE2", "X_ERROR", "Z_ERROR"] as ChannelKind[]) as k (k)}
            <button class="chip" class:on={lawKind === k} onclick={() => (lawKind = k)}>{k}</button>
          {/each}
        </label>
        <Slider bind:value={lawP} min={0.0} max={0.6} step={0.005} label="error rate p" format={(v) => v.toFixed(3)} />
        <Slider bind:value={lawN} min={10} max={20000} step={10} label="shots N" format={(v) => v.toLocaleString()} />
        <Slider bind:value={lawSeed} min={0} max={9999} step={1} label="seed" />
      </div>
      <div class="hist">
        {#each lawGrouped as g (g.label)}
          <div class="hist-row">
            <span class="hist-lbl mono">{g.label}</span>
            <div class="hist-track">
              <div class="hist-theory" style={`width:${(g.theory / lawMax) * 100}%`}></div>
              <div
                class="hist-emp"
                style={`width:${(g.empirical / lawMax) * 100}%; background:${withAlpha(C.accent, 0.75)}`}
              ></div>
            </div>
            <span class="hist-num mono">
              <span class="muted">{pct(g.theory)}</span> → {pct(g.empirical)}
            </span>
          </div>
        {/each}
      </div>
    </div>
  </Figure>

  <Callout kind="note" title="DEPOLARIZE2">
    Two-qubit depolarizing has <strong>16</strong> branches: identity plus the 15
    non-identity Pauli pairs (XI, IX, XX, XY, ..., ZZ), each at <Tex expr="p/15" />.
    They're grouped above for readability.
  </Callout>
</Section>

<Section id="syndrome" step="05" title="From trajectory to syndrome">
  <p>
    A trajectory changes some qubits; the decoder never sees those errors
    directly. It sees <strong>detection events</strong>. The definition is
    blunt: run the circuit once with <em>no</em> noise to get a reference parity
    for every detector, then for a noisy shot,
  </p>
  <Tex display expr={String.raw`\text{detection event}_d \;=\; (\text{measured parity of detector } d)\;\oplus\;(\text{reference parity}_d).`} />
  <p>
    A detector fires precisely when noise flipped its deterministic value. That
    bit-string is the <strong>syndrome</strong> -- the only thing the decoder eats.
    Click data qubits to inject <Tex expr="X" /> errors and watch the Z-checks
    between neighbours light up.
  </p>

  <Figure
    title="Trajectory → syndrome"
    legend={[
      { color: C.x, mark: "dot", label: "data qubit with X error" },
      { color: C.data, mark: "ring", label: "clean data qubit" },
      { color: C.defect, mark: "dot", label: "Z-check lit (detection event = 1)" },
      { color: C.z, mark: "ring", label: "Z-check quiet (0)" },
    ]}
    caption="A repetition-code round. Click a data qubit to flip it; a Z-check fires (lit) iff its two neighbours disagree."
  >
    <div class="syn-demo">
      <svg viewBox="0 0 100 46" class="syn-svg" role="img" aria-label="repetition code round">
        <!-- data line -->
        <line x1="8" y1="30" x2="92" y2="30" stroke={C.line} stroke-width="0.6" />
        <!-- checks between neighbours -->
        {#each synDefects as d, i (i)}
          {@const cx = 8 + ((i + 1) / synErrors.length) * 84}
          {@const lit = d === 1}
          {#if lit}
            <circle {cx} cy="14" r="5.6" fill={withAlpha(C.defect, 0.25)} />
            <line x1={cx} y1="14" x2={cx} y2="30" stroke={withAlpha(C.defect, 0.5)} stroke-width="0.5" />
          {/if}
          <circle
            {cx}
            cy="14"
            r="3.1"
            fill={lit ? C.defect : C.bg2}
            stroke={lit ? C.defect : withAlpha(C.z, 0.55)}
            stroke-width="0.7"
          />
        {/each}
        <!-- data qubits -->
        {#each synErrors as err, q (q)}
          {@const cx = 8 + ((q + 0.5) / synErrors.length) * 84}
          <g
            class="syn-q"
            role="button"
            tabindex="0"
            onclick={() => toggleErr(q)}
            onkeydown={(e) => { if (e.key === "Enter") { toggleErr(q); } }}
          >
            <circle
              {cx}
              cy="30"
              r="4.2"
              fill={err ? withAlpha(C.x, 0.9) : C.data}
              stroke={err ? C.x : withAlpha(C.line, 0.9)}
              stroke-width="0.7"
            />
            {#if err}<text x={cx} y="31.6" class="syn-lbl" text-anchor="middle">X</text>{/if}
          </g>
        {/each}
      </svg>
      <div class="syn-readout mono">
        syndrome = [{synDefects.join(", ")}]
        {#if synDefects.every((d) => d === 0)}
          <span class="muted">-- clean (decoder does nothing)</span>
        {/if}
      </div>
    </div>
  </Figure>

  <p>
    Notice an isolated error lights the <em>two</em> checks straddling it; a pair
    of adjacent errors only lights the checks at its ends. That structure is
    exactly what the matching, belief-propagation, and tensor-network decoders
    exploit. This panel is, quite literally, their input.
  </p>
</Section>

<Section id="sign" step="06" title="The sign problem, and importance sampling">
  <p>
    Real noise isn't always a tidy probability menu. A coherent
    <strong>rotation</strong> or <strong>amplitude damping</strong> is non-Pauli,
    and the only way to write it over Cliffords is with a
    <strong>quasiprobability</strong>: some weights go <em>negative</em>. You
    cannot sample from a probability that is below zero.
  </p>

  <Figure
    title="Quasiprobability branches"
    legend={[
      { color: C.ok, mark: "box", label: "positive weight wₖ ≥ 0 (above axis)" },
      { color: C.bad, mark: "box", label: "negative weight wₖ < 0 (below axis)" },
      { color: C.lineStrong, mark: "dash", label: "zero axis" },
    ]}
    caption="Quasiprobability branches. Bar height = |wₖ|; negative weights (below the axis) are the hallmark of non-Pauli noise."
  >
    <div class="sign-demo">
      <div class="sign-controls">
        <label class="seg-pick">
          <button class="chip" class:on={signKind === "RZ"} onclick={() => (signKind = "RZ")}>RZ (rotation)</button>
          <button class="chip" class:on={signKind === "AMPLITUDE_DAMP"} onclick={() => (signKind = "AMPLITUDE_DAMP")}>AMPLITUDE_DAMP</button>
        </label>
        <Slider
          bind:value={signParam}
          min={0.02}
          max={signKind === "RZ" ? 1.5 : 0.9}
          step={0.01}
          label={signKind === "RZ" ? "angle θ" : "damping p"}
          format={(v) => v.toFixed(2)}
        />
      </div>
      <div class="qbars">
        {#each signBranches as b, i (i)}
          {@const h = Math.abs(b.weight) * 80}
          <div class="qbar-col">
            <div class="qbar-stack">
              <div
                class="qbar"
                class:neg={b.weight < 0}
                style={`height:${h}px; background:${
                  b.weight < 0 ? withAlpha(C.bad, 0.75) : withAlpha(C.ok, 0.6)
                }; align-self:${b.weight < 0 ? "flex-start" : "flex-end"}`}
              ></div>
            </div>
            <span class="qbar-lbl mono">{b.pauli}</span>
            <span class="qbar-w mono" class:neg={b.weight < 0}>{b.weight.toFixed(3)}</span>
          </div>
        {/each}
      </div>
      <div class="gamma-line">
        <Tex expr="\gamma=\sum_k|w_k|" /> = <strong class="mono">{signGamma.toFixed(3)}</strong>
        <span class="muted">(γ = 1 would mean a true probability; γ &gt; 1 is the price of non-Cliffordness)</span>
      </div>
    </div>
  </Figure>

  <p>
    The fix is <strong>importance sampling</strong>. Draw a branch with
    probability <Tex expr="|w_k|/\gamma" />, and carry a signed
    <strong>importance weight</strong> <Tex expr={String.raw`\operatorname{sign}(w_k)\,\gamma`} />
    with the shot. Any statistic <Tex expr="f" /> is then estimated by the
    <em>weighted</em> mean over <Tex expr="N" /> shots:
  </p>
  <Tex
    display
    expr={String.raw`\hat{f} = \frac{1}{N}\sum_{s=1}^{N}\operatorname{sign}(w_{k_s})\,\gamma\; f(C_{k_s}),\qquad \mathbb{E}[\hat{f}] = \sum_k w_k\, f(C_k).`}
  />
  <p>
    Because we sample branch <Tex expr="k" /> with probability
    <Tex expr={String.raw`|w_k|/\gamma`} /> and multiply by
    <Tex expr={String.raw`\operatorname{sign}(w_k)\,\gamma`} />, the
    <Tex expr={String.raw`\gamma`} /> cancels and the <Tex expr={String.raw`\operatorname{sign}`} />
    restores the negative weights -- so <Tex expr={String.raw`\mathbb{E}[\hat{f}]`} /> is exactly
    the true quasiprobability average <Tex expr={String.raw`\sum_k w_k f(C_k)`} />. It is
    <strong>unbiased</strong>, the only honest way to put coherent or damping noise on a
    Clifford simulator.
  </p>
  <p>
    Contrast the two regimes. <strong>Naive Pauli sampling</strong> has every
    <Tex expr={String.raw`w_k \ge 0`} />, so <Tex expr={String.raw`\gamma = \sum_k|w_k| = \sum_k w_k = 1`} />:
    each shot carries weight <Tex expr="1" /> and you just count. <strong>Weighted
    sampling</strong> has <Tex expr={String.raw`\gamma > 1`} />: each shot carries
    <Tex expr={String.raw`\pm\gamma`} />, so the variance of <Tex expr={String.raw`\hat f`} /> picks
    up a factor of order <Tex expr={String.raw`\gamma^2`} /> per location (and the
    <Tex expr={String.raw`\gamma`} /> multiply across locations). To match a target error
    bar you need on the order of <Tex expr={String.raw`\gamma^2`} /> times as many shots --
    that inflation is the entire cost of non-Cliffordness.
  </p>

  <Worked title="Sampling RZ(θ = 0.6): one shot at u = 0.62">
    <ol>
      <li>
        Build the menu. With <Tex expr={String.raw`b_d=(1-\cos\theta-\sin\theta)/4`} /> at
        <Tex expr={String.raw`\theta=0.6`} /> (<Tex expr={String.raw`\cos=0.8253,\ \sin=0.5646,\ b_d=-0.0975`} />),
        the <Tex expr={String.raw`\{I,Z,S,S^\dagger\}`} /> weights are
        <Tex expr={String.raw`w_I=b_d+\cos=0.7278`} />,
        <Tex expr={String.raw`w_Z=b_d=-0.0975`} />,
        <Tex expr={String.raw`w_S=b_d+\sin=0.4671`} />,
        <Tex expr={String.raw`w_{S^\dagger}=b_d=-0.0975`} />.
      </li>
      <li>
        Negativity <Tex expr={String.raw`\gamma=\sum_k|w_k|=0.7278+0.0975+0.4671+0.0975=1.3900`} />
        (<Tex expr={String.raw`>1`} />, so this is genuinely non-Pauli).
      </li>
      <li>
        Roll the die: threshold <Tex expr={String.raw`t=u\,\gamma=0.62\times 1.3900=0.8618`} />.
      </li>
      <li>
        Walk the cumulative <Tex expr={String.raw`|w_k|`} />:
        <Tex expr={String.raw`I\!:0.7278`} /> (<Tex expr={String.raw`<t`} />),
        <Tex expr={String.raw`{+}Z\!:0.8253`} /> (<Tex expr={String.raw`<t`} />),
        <Tex expr={String.raw`{+}S\!:1.2925`} /> -- first sum <Tex expr={String.raw`\ge t`} />, so branch
        <Tex expr="S" /> fires.
      </li>
      <li>
        Its weight <Tex expr={String.raw`w_S=0.4671>0`} />, so the shot carries factor
        <Tex expr={String.raw`\operatorname{sign}(w_S)\,\gamma=+1.3900`} />.
      </li>
    </ol>
    {#snippet result()}
      This shot applies <b>S</b> and carries importance weight <b>+1.390</b>. Had the
      draw landed in <Tex expr="Z" />'s slot (e.g. <Tex expr="u=0.58" />,
      <Tex expr="t=0.806" />, inside <Tex expr={String.raw`(0.7278,\,0.8253]`} />), the
      same machinery would apply <b>Z</b> and carry <b>−1.390</b> -- the negative sign
      that keeps the estimate unbiased.
    {/snippet}
  </Worked>

  <Figure
    wide
    title="Weighted vs. naive estimate"
    legend={[
      { color: C.fg, mark: "line", label: "truth Σ wₖ·indicator" },
      { color: C.accent, mark: "dot", label: "weighted estimate (±2σ band)" },
      { color: C.bad, mark: "dot", label: "naive estimate (biased)" },
    ]}
    caption="Estimating P(a Z error fires) two ways, on a number line of the estimated value. The weighted estimate (with its ±2σ band) hugs the truth; the naive one (ignoring sign·γ) is biased."
  >
    <div class="var-wrap">
      <div class="var-controls">
        <Slider bind:value={signN} min={20} max={20000} step={20} label="shots N" format={(v) => v.toLocaleString()} />
        <Slider bind:value={signSeed} min={0} max={9999} step={1} label="seed" />
      </div>
      <div class="var-axis">
        <!-- true value -->
        <div class="var-true" style={`left:${signX(signTrue)}%`}>
          <span class="var-tag" style={`color:${C.fg}`}>truth {signTrue.toFixed(3)}</span>
        </div>
        <!-- weighted estimate with ±2σ error bar -->
        <div
          class="var-band"
          style={`left:${signX(signRun.mean - 2 * signRun.stderr)}%; width:${((4 * signRun.stderr) / signSpan) * 100}%; background:${withAlpha(C.accent, 0.35)}`}
        ></div>
        <div class="var-point" style={`left:${signX(signRun.mean)}%; background:${C.accent}`}>
          <span class="var-tag" style={`color:${C.accent}`}>weighted {signRun.mean.toFixed(3)}</span>
        </div>
        <!-- naive (biased) estimate -->
        <div class="var-point naive" style={`left:${signX(signRun.naiveMean)}%; background:${C.bad}`}>
          <span class="var-tag down" style={`color:${C.bad}`}>naive {signRun.naiveMean.toFixed(3)}</span>
        </div>
      </div>
      <div class="var-note">
        weighted ±2σ error bar half-width ≈ <strong class="mono">{(2 * signRun.stderr).toFixed(4)}</strong>.
        Raising γ widens it -- non-Pauli noise needs more shots for the same precision.
      </div>
    </div>
  </Figure>

  <Callout kind="warn" title="The catch: variance grows with γ²">
    Importance sampling is unbiased but not free. Each shot's weight has magnitude
    <Tex expr={String.raw`\gamma`} />, so the estimator's variance scales with
    <Tex expr={String.raw`\gamma^2`} /> (and compounds multiplicatively across
    locations). The further your noise is from Clifford, the bigger
    <Tex expr={String.raw`\gamma`} />, and the more shots you need. Push
    <Tex expr={String.raw`\theta`} /> or <Tex expr="p" /> up and the error bar
    visibly widens.
  </Callout>
</Section>

<Section id="scales" step="07" title="Why it all scales">
  <p>
    Step back and count the cost of one shot. At every noise location the
    simulator picks <strong>one</strong> Clifford branch and applies it to the
    stabilizer tableau. No branch ever forks the simulation; no
    <Tex expr="2^n" /> state-vector is ever formed. So a shot costs a
    polynomial number of tableau updates, and the millions of shots you need are
    independent -- perfectly parallel across cores and machines.
  </p>

  <Callout kind="key" title="The whole engine in one breath">
    A channel is a menu of <strong>(weight, Clifford ops)</strong> branches; per
    location per shot you draw <strong>one</strong> via <Tex expr="\gamma" /> and a
    uniform threshold; a trajectory is the running tableau plus a signed
    importance weight; a detector fires when the shot's parity disagrees with the
    noiseless reference. Pauli noise samples directly; non-Pauli noise rides the
    weighted mean. Stabilizer formalism + one branch per location = polynomial per
    shot, trivially parallel across shots. That is qliff's reason for existing.
  </Callout>

  <p>
    From here, those sampled-and-decoded shots become a number. Feed the
    detection events to a decoder (matching, BP, or tensor networks), compare its
    correction against the true observable flip, and the fraction it gets wrong --
    weighted, if the noise was non-Pauli -- is the <strong>logical error rate</strong>.
    That's the next, and final, step.
  </p>
</Section>

<style>
  .scale-demo,
  .menu-demo,
  .law-wrap,
  .sign-demo,
  .var-wrap,
  .traj-wrap {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* section 01 */
  .scale-rows {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .scale-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    padding: 9px 12px;
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: color-mix(in srgb, var(--bg-2) 50%, transparent);
  }
  .scale-name {
    font-size: 13px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .scale-val {
    font-size: 15px;
    font-weight: 600;
  }
  .scale-val sup {
    font-size: 0.7em;
  }

  /* section 02 menu */
  .menu-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .menu-item {
    display: grid;
    grid-template-columns: 110px 1fr 56px;
    align-items: center;
    gap: 12px;
  }
  .menu-lbl {
    font-size: 13px;
    font-weight: 600;
  }
  .menu-track {
    height: 16px;
    border-radius: 5px;
    background: color-mix(in srgb, var(--bg-2) 70%, transparent);
    border: 1px solid var(--line);
    overflow: hidden;
  }
  .menu-fill {
    height: 100%;
    transition: width 0.12s ease-out;
  }
  .menu-w {
    font-size: 12.5px;
    color: var(--fg);
    text-align: right;
  }

  /* section 03 */
  .traj-controls,
  .law-controls,
  .sign-controls,
  .var-controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 14px;
    align-items: end;
  }

  /* section 04 histogram */
  .seg-pick {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    grid-column: 1 / -1;
  }
  .chip {
    padding: 5px 11px;
    font-size: 12.5px;
    font-family: var(--mono, ui-monospace, monospace);
  }
  .chip.on {
    border-color: color-mix(in srgb, var(--accent) 60%, transparent);
    background: var(--grad-soft);
    color: var(--fg);
  }
  .hist {
    display: flex;
    flex-direction: column;
    gap: 9px;
  }
  .hist-row {
    display: grid;
    grid-template-columns: 150px 1fr 150px;
    align-items: center;
    gap: 12px;
  }
  .hist-lbl {
    font-size: 12.5px;
    color: var(--fg);
  }
  .hist-track {
    position: relative;
    height: 22px;
  }
  .hist-theory {
    position: absolute;
    inset: 0 auto 0 0;
    height: 100%;
    border: 1px dashed var(--line-strong);
    border-radius: 5px;
    background: transparent;
  }
  .hist-emp {
    position: absolute;
    top: 4px;
    bottom: 4px;
    left: 0;
    border-radius: 4px;
    transition: width 0.1s ease-out;
  }
  .hist-num {
    font-size: 12px;
    color: var(--fg);
    text-align: right;
  }
  .muted {
    color: var(--muted);
  }

  /* section 05 syndrome */
  .syn-demo {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .syn-svg {
    width: 100%;
    height: auto;
    /* viewBox 100 x 46 renders ~300px tall; cap keeps it well under target on
       any panel width (default preserveAspectRatio letterboxes, no distortion). */
    max-height: 360px;
    display: block;
  }
  .syn-q {
    cursor: pointer;
  }
  .syn-q:hover circle {
    filter: brightness(1.2);
  }
  .syn-q:focus {
    outline: none;
  }
  .syn-q:focus-visible circle {
    stroke: var(--accent);
    stroke-width: 1.2;
  }
  .syn-lbl {
    font-size: 4px;
    font-weight: 700;
    fill: #1a0b14;
    pointer-events: none;
    font-family: var(--mono, ui-monospace, monospace);
  }
  .syn-readout {
    font-size: 13px;
    color: var(--fg);
    text-align: center;
  }

  /* section 06 quasiprob bars */
  .qbars {
    display: flex;
    gap: 14px;
    align-items: stretch;
    justify-content: center;
    min-height: 180px;
  }
  .qbar-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    flex: 1;
    max-width: 90px;
  }
  .qbar-stack {
    width: 100%;
    height: 160px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    border-bottom: 1px solid var(--line);
  }
  .qbar-stack::before {
    /* zero axis */
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    border-top: 1px dashed var(--line-strong);
  }
  .qbar {
    width: 70%;
    margin: 0 auto;
    border-radius: 3px 3px 0 0;
    transition: height 0.12s ease-out;
  }
  .qbar.neg {
    border-radius: 0 0 3px 3px;
  }
  .qbar-lbl {
    font-size: 13px;
    font-weight: 700;
    color: var(--fg);
  }
  .qbar-w {
    font-size: 11.5px;
    color: var(--ok);
  }
  .qbar-w.neg {
    color: var(--bad);
  }
  .gamma-line {
    font-size: 14px;
    color: var(--fg);
    text-align: center;
  }
  .gamma-line .muted {
    display: block;
    margin-top: 3px;
    font-size: 12.5px;
  }

  /* section 06 variance demo */
  .var-axis {
    position: relative;
    height: 70px;
    margin: 26px 8px 8px;
    border-bottom: 1px solid var(--line);
  }
  .var-band {
    position: absolute;
    top: 24px;
    height: 16px;
    border-radius: 4px;
  }
  .var-true {
    position: absolute;
    top: -22px;
    bottom: -6px;
    width: 2px;
    background: var(--fg);
    transform: translateX(-1px);
  }
  .var-point {
    position: absolute;
    top: 26px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    transform: translate(-6px, 0);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--bg-2) 90%, transparent);
  }
  .var-tag {
    position: absolute;
    top: -22px;
    left: 50%;
    transform: translateX(-50%);
    white-space: nowrap;
    font-size: 11.5px;
    font-weight: 600;
    font-family: var(--mono, ui-monospace, monospace);
  }
  .var-tag.down {
    top: 18px;
  }
  .var-note {
    font-size: 13px;
    color: var(--muted);
    text-align: center;
  }
  .var-note strong {
    color: var(--fg);
  }

  .mono {
    font-family: var(--mono, ui-monospace, monospace);
  }
</style>
