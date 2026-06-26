<script lang="ts">
  import Section from "$lib/Section.svelte";
  import TeX from "$lib/Math.svelte";
  import Scrubber from "$lib/Scrubber.svelte";
  import Callout from "$lib/Callout.svelte";
  import Figure from "$lib/Figure.svelte";
  import Worked from "$lib/Worked.svelte";
  import { C } from "$lib/colors";
  import PauliCells from "./PauliCells.svelte";
  import Circuit, { type Op } from "./Circuit.svelte";
  import {
    single,
    pauliString,
    stateLabel,
    apply1,
    withCX,
    withCZ,
    type Pauli,
    type Gate1Name,
  } from "./tableau";

  const G1: Gate1Name[] = ["H", "S", "S†", "X", "Y", "Z"];

  // ===== Section 1: Heisenberg flip (1-qubit conjugation) ==================
  let s1 = $state<Pauli>(single(1, 0, "Z")); // start at +Z = |0>
  const s1label = $derived(stateLabel(s1));

  function gate1(name: Gate1Name): void {
    s1 = apply1(name, s1, 0);
  }
  function reset1(): void {
    s1 = single(1, 0, "Z");
  }

  // ===== Section 2: Paulis as bits =========================================
  let bx = $state(false);
  let bz = $state(true); // default Z
  let bsign = $state<0 | 1>(0);
  const bitsPauli = $derived<Pauli>({ x: [bx], z: [bz], sign: bsign });

  const pauliTable = [
    { letter: "I", x: 0, z: 0, note: "does nothing" },
    { letter: "X", x: 1, z: 0, note: "bit flip" },
    { letter: "Z", x: 0, z: 1, note: "phase flip" },
    { letter: "Y", x: 1, z: 1, note: "both (Y = iXZ)" },
  ];

  // ===== Section 3: single-qubit gates as bit ops ==========================
  let s3 = $state<Pauli>(single(1, 0, "Z"));
  function gate3(name: Gate1Name): void {
    s3 = apply1(name, s3, 0);
  }
  function set3(letter: "I" | "X" | "Y" | "Z"): void {
    s3 = single(1, 0, letter);
  }

  // ===== Section 4: the CX gate ============================================
  // Two-qubit input Pauli the reader composes from generator buttons, then CX.
  const INPUTS: { key: string; letter: "X" | "Y" | "Z"; q: 0 | 1; label: string }[] = [
    { key: "Xc", letter: "X", q: 0, label: "X_c" },
    { key: "Zc", letter: "Z", q: 0, label: "Z_c" },
    { key: "Yc", letter: "Y", q: 0, label: "Y_c" },
    { key: "Xt", letter: "X", q: 1, label: "X_t" },
    { key: "Zt", letter: "Z", q: 1, label: "Z_t" },
    { key: "Yt", letter: "Y", q: 1, label: "Y_t" },
  ];
  let cxInput = $state<Pauli>(single(2, 1, "Z")); // default Z_t (the backward-propagating one)
  const cxOutput = $derived(withCX(cxInput, 0, 1));

  function setCXInput(letter: "X" | "Y" | "Z", q: 0 | 1): void {
    cxInput = single(2, q, letter);
  }

  // the four generator rules, each produced by withCX so the table is live.
  const cxRules = [
    { inp: single(2, 0, "X"), name: "X_c" },
    { inp: single(2, 1, "X"), name: "X_t" },
    { inp: single(2, 0, "Z"), name: "Z_c" },
    { inp: single(2, 1, "Z"), name: "Z_t" },
  ].map((r) => ({ ...r, out: withCX(r.inp, 0, 1) }));

  // CZ contrast (symmetric).
  const czRules = [
    { inp: single(2, 0, "X"), name: "X_0" },
    { inp: single(2, 1, "X"), name: "X_1" },
    { inp: single(2, 0, "Z"), name: "Z_0" },
  ].map((r) => ({ ...r, out: withCZ(r.inp, 0, 1) }));

  // ===== Section 5: error propagation through a GHZ encoder ================
  // Circuit: H q0; CX 0->1; CX 0->2; CX 0->3.  (GHZ / cat-state encoder; its
  // CX fan-out is the skeleton of a syndrome-extraction round.)
  const NQ5 = 4;
  const OPS5: Op[] = [
    { kind: "H", a: 0 },
    { kind: "CX", a: 0, b: 1 },
    { kind: "CX", a: 0, b: 2 },
    { kind: "CX", a: 0, b: 3 },
  ];

  let injType = $state<"X" | "Z">("X");
  let injQubit = $state(0);
  // inject the fault BEFORE this column index (0..OPS5.length).
  let injStep = $state(1);
  let frame5step = $state(OPS5.length); // scrub position (columns executed)

  // Pure: build the Pauli frame after `step` columns, given the injected fault.
  // The fault is inserted just before column `injStep`; columns at/after the
  // injection that have executed then conjugate it.
  function frameAt(step: number): Pauli {
    // start identity; the fault only exists from injStep onward.
    let p: Pauli = single(NQ5, injQubit, injType);
    if (step < injStep) {
      return single(NQ5, 0, "I"); // nothing on the wires yet (before injection)
    }
    // apply every gate from column injStep .. step-1.
    for (let col = injStep; col < step; col += 1) {
      const op = OPS5[col];
      if (op.kind === "H") {
        p = apply1("H", p, op.a);
      } else if (op.kind === "CX" && op.b !== undefined) {
        p = withCX(p, op.a, op.b);
      }
    }

    return p;
  }

  const frame5 = $derived(frameAt(frame5step));
  const finalFrame5 = $derived(frameAt(OPS5.length));
  // final support = qubits carrying a non-identity Pauli at the end.
  const finalSupport5 = $derived.by(() => {
    const s: number[] = [];
    for (let q = 0; q < NQ5; q += 1) {
      if (finalFrame5.x[q] || finalFrame5.z[q]) {
        s.push(q);
      }
    }

    return s;
  });

  function setInject(type: "X" | "Z", qubit: number, step: number): void {
    injType = type;
    injQubit = qubit;
    injStep = step;
    frame5step = OPS5.length;
  }

  // ===== Section 6: signs & measurement ====================================
  // A tiny ±Z demo: +Z stabilizes |0> (measures 0), -Z stabilizes |1> (measures 1).
  let measPauli = $state<Pauli>(single(1, 0, "Z"));
  const measOutcome = $derived(measPauli.sign === 0 ? 0 : 1);
  function flipMeas(): void {
    // X flips +Z <-> -Z (the bit), demonstrating the sign carries the outcome.
    measPauli = apply1("X", measPauli, 0);
  }
  function resetMeas(): void {
    measPauli = single(1, 0, "Z");
  }

  // ===== Section 7: recap table ============================================
  const recap = [
    { gate: "H(a)", sign: "x_a · z_a", upd: "swap x_a ↔ z_a", eff: "X↔Z, Y→−Y" },
    { gate: "S(a)", sign: "x_a · z_a", upd: "z_a ^= x_a", eff: "X→Y, Z→Z" },
    { gate: "S†(a)", sign: "x_a · ¬z_a", upd: "z_a ^= x_a", eff: "X→−Y" },
    { gate: "X(a)", sign: "z_a", upd: "--", eff: "phase on Z,Y" },
    { gate: "Z(a)", sign: "x_a", upd: "--", eff: "phase on X,Y" },
    { gate: "Y(a)", sign: "x_a ^ z_a", upd: "--", eff: "phase on X,Z" },
    { gate: "CX(a,b)", sign: "x_a·z_b·(x_b^z_a^1)", upd: "x_b ^= x_a;  z_a ^= z_b", eff: "X fwd, Z back" },
    { gate: "CZ(a,b)", sign: "x_a·x_b·(z_a^z_b)", upd: "z_a ^= x_b;  z_b ^= x_a", eff: "symmetric" },
  ];
</script>

<Section id="heisenberg" step="01" title="Cliffords conjugate operators, not amplitudes">
  <p>
    A general <TeX expr="n" />-qubit state needs <TeX expr="2^n" /> complex
    amplitudes -- hopeless past ~30 qubits. A <strong>stabilizer simulator</strong>
    sidesteps that entirely. Instead of the state vector it tracks the Pauli
    operators that <em>stabilize</em> the state: operators
    <TeX expr="S" /> with <TeX expr={String.raw`S\ket{\psi}=+\ket{\psi}`} />. The state is
    pinned down by its stabilizers, so we only ever store and update
    <em>operators</em>.
  </p>
  <p>
    When a gate <TeX expr="U" /> acts, every stabilizer is updated by
    <strong>conjugation</strong> in the Heisenberg picture,
    <TeX expr={String.raw`S \mapsto U S U^{\dagger}`} />. Why that is the right rule:
  </p>
  <TeX
    display
    expr={String.raw`(U S U^{\dagger})\,(U\ket{\psi}) = U S \ket{\psi} = U\ket{\psi},`}
  />
  <p>
    so if <TeX expr="S" /> stabilized the old state, <TeX expr={String.raw`USU^{\dagger}`} />
    stabilizes the new one <TeX expr={String.raw`U\ket{\psi}`} />. No amplitudes appear -- just
    a Pauli in, a Pauli out. Press a gate and watch the single stabilizer of a
    1-qubit state move, and the ket it pins down change with it.
  </p>

  <Figure
    title="1-qubit stabilizer under a gate"
    legend={[
      { color: C.x, mark: "box", label: "X part" },
      { color: C.z, mark: "box", label: "Z part" },
      { color: C.ok, mark: "box", label: "+ sign" },
      { color: C.bad, mark: "box", label: "− sign" },
    ]}
    caption="The operator IS the state here: +Z pins |0⟩, +X pins |+⟩, −Y pins |−i⟩, ..."
  >
    <div class="stage center">
      <div class="bigstate">
        <span class="ket mono">{s1label}</span>
        <span class="stab mono">stabilizer {pauliString(s1)}</span>
      </div>
      <div class="gaterow">
        {#each G1 as g (g)}
          <button class="gbtn mono" onclick={() => gate1(g)}>{g}</button>
        {/each}
        <button class="reset" onclick={reset1}>reset to |0⟩</button>
      </div>
    </div>
  </Figure>

  <Callout kind="key" title="Operators, never 2ⁿ numbers">
    <TeX expr="H" /> on <TeX expr="+Z" /> (which is <TeX expr={String.raw`\ket0`} />) gives
    <TeX expr="+X" /> (which is <TeX expr={String.raw`\ket+`} />) -- exactly the Hadamard basis
    change. The whole simulation is bookkeeping on a handful of bits per operator,
    which is why qliff scales to thousands of qubits where a state vector cannot.
  </Callout>
</Section>

<Section id="bits" step="02" title="A Pauli is two bits plus a sign">
  <p>
    To compute with Paulis we encode each single-qubit factor as two bits -- an
    <span style="color:var(--x)">x bit</span> and a
    <span style="color:var(--z)">z bit</span> -- plus one global
    <strong>sign</strong> bit for the whole operator
    (<TeX expr="0=+" />, <TeX expr="1=-" />):
  </p>

  <Figure
    title="Pauli ↔ bits"
    legend={[
      { color: C.x, mark: "box", label: "x bit (1 ⇒ has X-part)" },
      { color: C.z, mark: "box", label: "z bit (1 ⇒ has Z-part)" },
    ]}
    caption="Y is just x=z=1 in the tableau (the i in Y=iXZ lives in the bookkeeping, not these bits)."
  >
    <div class="splitgrid">
      <table class="tbl mono">
        <thead><tr><th>Pauli</th><th>x</th><th>z</th><th>meaning</th></tr></thead>
        <tbody>
          {#each pauliTable as r (r.letter)}
            <tr>
              <td class="lt" style="color:{r.letter === 'X' ? C.x : r.letter === 'Z' ? C.z : r.letter === 'Y' ? C.y : C.faint}">{r.letter}</td>
              <td>{r.x}</td>
              <td>{r.z}</td>
              <td class="muted">{r.note}</td>
            </tr>
          {/each}
        </tbody>
      </table>

      <div class="toggle-demo">
        <div class="tdrow">
          <button class="bitbtn" class:on={bx} style="--bc:{C.x}" onclick={() => (bx = !bx)}>x = {bx ? 1 : 0}</button>
          <button class="bitbtn" class:on={bz} style="--bc:{C.z}" onclick={() => (bz = !bz)}>z = {bz ? 1 : 0}</button>
          <button class="bitbtn" class:on={bsign === 1} style="--bc:{C.bad}" onclick={() => (bsign = (bsign ^ 1) as 0 | 1)}>sign = {bsign}</button>
        </div>
        <div class="tdout">
          <PauliCells p={bitsPauli} labels={["q"]} />
        </div>
        <p class="hint">Toggle the bits -- a whole tableau row is just many of these side by side.</p>
      </div>
    </div>
  </Figure>

  <Callout kind="note" title="The full tableau">
    A stabilizer state of <TeX expr="n" /> qubits is <TeX expr="n" /> such rows
    (qliff stores <TeX expr="2n" /> -- also <TeX expr="n" /> destabilizers -- but
    one conjugated row already tells the whole gate story). A gate edits these
    bits column by column; that is the entire engine.
  </Callout>
</Section>

<Section id="single" step="03" title="Single-qubit gates are tiny bit ops">
  <p>
    Each Clifford is a fixed recipe on the bits. Crucially we read the
    <em>original</em> <TeX expr="x,z" /> to update the sign, <em>then</em> permute
    the bits:
  </p>
  <TeX display expr={String.raw`\textsf{H}: \;\text{sign}\,{\oplus}{=}\,x z,\;\; x{\leftrightarrow}z \qquad \textsf{S}: \;\text{sign}\,{\oplus}{=}\,x z,\;\; z\,{\oplus}{=}\,x`} />
  <p>
    <TeX expr={String.raw`\textsf{X},\textsf{Z},\textsf{Y}`} /> never move bits at all -- they
    only flip the sign when they anticommute with what is already there
    (<TeX expr={String.raw`\textsf{X}{:}\,\text{sign}\,{\oplus}{=}\,z`} />,
    <TeX expr={String.raw`\textsf{Z}{:}\,\text{sign}\,{\oplus}{=}\,x`} />). Pick a starting
    Pauli, apply gates, and watch the bits and the sign rule fire.
  </p>

  <Figure
    title="Bit-level gate playground"
    legend={[
      { color: C.x, mark: "box", label: "x bit" },
      { color: C.z, mark: "box", label: "z bit" },
      { color: C.ok, mark: "box", label: "+ sign" },
      { color: C.bad, mark: "box", label: "− sign" },
    ]}
    caption="Set a Pauli, then apply gates. Y→−Y under H is the xz sign term firing."
  >
    <div class="stage">
      <div class="setrow">
        <span class="lbl">start:</span>
        {#each (["I", "X", "Y", "Z"] as const) as l (l)}
          <button class="gbtn small mono" onclick={() => set3(l)}>{l}</button>
        {/each}
      </div>
      <div class="bigout"><PauliCells p={s3} labels={["q"]} /></div>
      <div class="gaterow">
        {#each G1 as g (g)}
          <button class="gbtn mono" onclick={() => gate3(g)}>{g}</button>
        {/each}
        <span class="curr mono">= {pauliString(s3)}</span>
      </div>
    </div>
  </Figure>

  <Worked title="H on Z, then S on X (every number from the rules)">
    <ol>
      <li>
        Start at <TeX expr="Z" />: bits <TeX expr="(x,z)=(0,1)" />, sign
        <TeX expr="0" />.
      </li>
      <li>
        Apply <TeX expr={String.raw`\textsf{H}`} />. Sign term
        <TeX expr={String.raw`x\cdot z = 0\cdot 1 = 0`} />, so sign stays
        <TeX expr="0" />. Swap bits: <TeX expr={String.raw`(0,1)\to(1,0)`} />.
      </li>
      <li>
        <TeX expr="(1,0)" /> with sign <TeX expr="0" /> reads as <TeX expr="+X" />.
        So <TeX expr={String.raw`\textsf H Z\textsf H = X`} />. ✓
      </li>
      <li>
        Now start fresh at <TeX expr="X" />: <TeX expr="(1,0)" />, sign
        <TeX expr="0" />. Apply <TeX expr={String.raw`\textsf S`} />. Sign term
        <TeX expr={String.raw`x z = 1\cdot 0 = 0`} />; then
        <TeX expr={String.raw`z\,{\oplus}{=}\,x`} /> makes
        <TeX expr="(1,1)" />.
      </li>
    </ol>
    {#snippet result()}
      <TeX expr={String.raw`\textsf H Z \textsf H = +X`} /> and
      <TeX expr={String.raw`\textsf S X \textsf S^{\dagger} = +Y`} /> -- both with
      <strong>+ signs</strong>. Click <em>start: Z</em> then <em>H</em> above to
      reproduce the first; <em>start: X</em> then <em>S</em> for the second.
    {/snippet}
  </Worked>
</Section>

<Section id="cx" step="04" title="The CX gate -- where intuition breaks" wide>
  <div class="prose">
    <p>
      Here is the operation that confuses everyone. <TeX expr={String.raw`\textsf{CX}`} /> with
      control <TeX expr="a" /> and target <TeX expr="b" /> updates a Pauli with
      qliff's exact rule -- read originals, set the sign, then edit the bits:
    </p>
    <TeX
      display
      expr={String.raw`\text{sign}\,{\oplus}{=}\,x_a z_b (x_b{\oplus}z_a{\oplus}1), \qquad x_b\,{\oplus}{=}\,x_a, \qquad z_a\,{\oplus}{=}\,z_b.`}
    />
    <p>
      Two bit copies fall out, and they go in <em>opposite directions</em>:
      <TeX expr={String.raw`x_b\,{\oplus}{=}\,x_a`} /> copies the control's X-part
      <strong>forward</strong> onto the target, while
      <TeX expr={String.raw`z_a\,{\oplus}{=}\,z_b`} /> copies the target's Z-part
      <strong>backward</strong> onto the control.
    </p>
  </div>

  <Figure
    wide
    title="CX propagator"
    legend={[
      { color: C.x, mark: "box", label: "X part (copies forward)" },
      { color: C.z, mark: "box", label: "Z part (copies backward)" },
      { color: C.y, mark: "box", label: "Y part" },
      { color: C.accent, mark: "box", label: "control / target qubit" },
    ]}
    caption="Choose an input Pauli, then read off CX·input·CX†. Control = q0, target = q1."
  >
    <div class="cxgrid">
      <div class="cxcol">
        <span class="lbl">input on (control q0, target q1)</span>
        <div class="setrow wrap">
          {#each INPUTS as inp (inp.key)}
            <button class="gbtn small mono" onclick={() => setCXInput(inp.letter, inp.q)}>
              {inp.letter}<sub>{inp.q === 0 ? "c" : "t"}</sub>
            </button>
          {/each}
        </div>
        <div class="cxio"><PauliCells p={cxInput} labels={["q0 (c)", "q1 (t)"]} /></div>
      </div>

      <div class="cxarrow mono">-- CX 0→1 →</div>

      <div class="cxcol">
        <span class="lbl">output {pauliString(cxOutput)}</span>
        <div class="cxio"><PauliCells p={cxOutput} labels={["q0 (c)", "q1 (t)"]} /></div>
        <div class="bitnote mono">
          x₁ ^= x₀ = {cxInput.x[0] ? 1 : 0} → x₁ now {cxOutput.x[1] ? 1 : 0};
          z₀ ^= z₁ = {cxInput.z[1] ? 1 : 0} → z₀ now {cxOutput.z[0] ? 1 : 0}
        </div>
      </div>
    </div>

    <table class="rules mono">
      <thead><tr><th>generator</th><th>→ becomes</th><th>direction</th></tr></thead>
      <tbody>
        {#each cxRules as r (r.name)}
          <tr>
            <td class="lt">{r.name.replace("_c", "₍c₎").replace("_t", "₍t₎")}</td>
            <td class="lt" style="color:{C.accent}">{pauliString(r.out)}</td>
            <td class="muted">
              {r.name === "X_c" ? "X forward → target" : r.name === "Z_t" ? "Z backward → control" : "unchanged"}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </Figure>

  <div class="prose">
    <Callout kind="warn" title="Control and target are NOT symmetric">
      Almost everyone expects CX to "copy the control onto the target" for
      everything. True for <span style="color:var(--x)">X</span> -- but
      <span style="color:var(--z)">Z</span> propagates the
      <em>other way</em>, target → control. <TeX expr={String.raw`\textsf{X}`} /> goes forward,
      <TeX expr={String.raw`\textsf{Z}`} /> goes backward. This single fact is the source of
      almost every stabilizer-simulator bug.
    </Callout>

    <Worked title="The two propagations, in bits">
      <ol>
        <li>
          <strong>X on the control.</strong> <TeX expr="X_c" /> is
          <TeX expr={String.raw`x=(1,0),\,z=(0,0)`} />. Apply
          <TeX expr={String.raw`x_b\,{\oplus}{=}\,x_a:\;x_1\,{\oplus}{=}\,1`} /> →
          <TeX expr="x=(1,1)" />. Now both qubits carry an X.
        </li>
        <li>
          Sign term <TeX expr={String.raw`x_a z_b(\dots)=1\cdot 0\cdot(\dots)=0`} />.
          Result: <TeX expr={String.raw`X_c \to X_c X_t`} />, the
          <strong>+</strong> forward copy.
        </li>
        <li>
          <strong>Z on the target.</strong> <TeX expr="Z_t" /> is
          <TeX expr={String.raw`x=(0,0),\,z=(0,1)`} />. Apply
          <TeX expr={String.raw`z_a\,{\oplus}{=}\,z_b:\;z_0\,{\oplus}{=}\,1`} /> →
          <TeX expr="z=(1,1)" />. Now both qubits carry a Z.
        </li>
        <li>
          Sign term <TeX expr={String.raw`x_a z_b(\dots)=0\cdot 1\cdot(\dots)=0`} />.
          Result: <TeX expr={String.raw`Z_t \to Z_c Z_t`} />, the
          <strong>backward</strong> copy.
        </li>
      </ol>
      {#snippet result()}
        <TeX expr={String.raw`X_c \to X_c X_t`} /> (forward) and
        <TeX expr={String.raw`Z_t \to Z_c Z_t`} /> (backward), both <strong>+</strong>.
        Click <em>X<sub>c</sub></em> then <em>Z<sub>t</sub></em> above to watch the
        bits do exactly this.
      {/snippet}
    </Worked>

    <p>
      For contrast, <TeX expr={String.raw`\textsf{CZ}`} /> <em>is</em> symmetric
      (<TeX expr={String.raw`z_a\,{\oplus}{=}\,x_b,\; z_b\,{\oplus}{=}\,x_a`} />):
      it grows a Z on each qubit from the other's X, the same in both directions.
      And <TeX expr={String.raw`\textsf{SWAP}=\textsf{CX}(a,b)\,\textsf{CX}(b,a)\,\textsf{CX}(a,b)`} />.
    </p>
    <table class="rules mono inline-tbl">
      <thead><tr><th>CZ generator</th><th>→ becomes</th></tr></thead>
      <tbody>
        {#each czRules as r (r.name)}
          <tr>
            <td class="lt">{r.name.replace("_0", "₀").replace("_1", "₁")}</td>
            <td class="lt" style="color:{C.accent2}">{pauliString(r.out)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</Section>

<Section id="propagation" step="05" title="Faults spread through entangling gates" wide>
  <div class="prose">
    <p>
      Now the payoff for QEC. Because <TeX expr={String.raw`\textsf{X}`} /> copies forward
      through every <TeX expr={String.raw`\textsf{CX}`} />, a <em>single</em> fault before an
      entangling gate becomes a <em>multi-qubit</em> error after it. Below is a
      4-qubit GHZ / cat-state encoder
      (<TeX expr={String.raw`\textsf H\,q_0;\ \textsf{CX}\,0{\to}1;\ \textsf{CX}\,0{\to}2;\ \textsf{CX}\,0{\to}3`} />)
      -- the same fan-out of CX gates that a syndrome-extraction round uses. Inject
      a fault and scrub through the circuit to watch the Pauli "frame" spread.
    </p>
  </div>

  <Figure
    wide
    title="Error propagation through a GHZ encoder"
    legend={[
      { color: C.x, mark: "box", label: "X on a wire" },
      { color: C.z, mark: "box", label: "Z on a wire" },
      { color: C.accent3, mark: "ring", label: "injected fault" },
      { color: C.bad, mark: "dot", label: "final support" },
    ]}
    caption="The boxed letter on each wire is the Pauli currently riding it. Faded gates haven't executed yet at this scrub step."
  >
    <Circuit
      nq={NQ5}
      ops={OPS5}
      frame={frame5}
      step={frame5step}
      injectStep={injStep}
      injectQubit={injQubit}
      finalSupport={finalSupport5}
    />
    <Scrubber bind:value={frame5step} min={0} max={OPS5.length} label="after gate" />
    <div class="injrow">
      <span class="lbl">inject:</span>
      <button class="gbtn small mono" class:on={injType === "X"} onclick={() => setInject("X", injQubit, injStep)}>X</button>
      <button class="gbtn small mono" class:on={injType === "Z"} onclick={() => setInject("Z", injQubit, injStep)}>Z</button>
      <span class="lbl">on qubit:</span>
      {#each Array(NQ5) as _, q (q)}
        <button class="gbtn small mono" class:on={injQubit === q} onclick={() => setInject(injType, q, injStep)}>q{q}</button>
      {/each}
      <span class="lbl">before gate:</span>
      {#each Array(OPS5.length) as _, c (c)}
        <button class="gbtn small mono" class:on={injStep === c} onclick={() => setInject(injType, injQubit, c)}>#{c}</button>
      {/each}
    </div>
    <div class="finalbar mono">
      final error: <span style="color:{C.accent}">{pauliString(finalFrame5)}</span>
      &nbsp;·&nbsp; support = {finalSupport5.length} qubit{finalSupport5.length === 1 ? "" : "s"}
    </div>
  </Figure>

  <div class="prose">
    <Worked title="One X on the control lights two detectors">
      <ol>
        <li>
          Inject <TeX expr="X" /> on <TeX expr="q_0" /> just before
          <TeX expr={String.raw`\textsf{CX}\,0{\to}1`} /> (set inject = X, qubit q0,
          before gate #1).
        </li>
        <li>
          <TeX expr={String.raw`\textsf{CX}\,0{\to}1`} /> sends
          <TeX expr={String.raw`X_0 \to X_0 X_1`} /> -- the fault is now on <em>two</em> data
          qubits.
        </li>
        <li>
          If <TeX expr="q_0" /> also feeds <TeX expr={String.raw`\textsf{CX}\,0{\to}2`} /> the
          X keeps copying forward: a chain of X's across the support.
        </li>
        <li>
          On a 1-D code each flipped data qubit sits under a parity check, but
          only the <strong>two ends</strong> of the flipped chain break parity:
          every interior check sees two flips and stays quiet.
        </li>
      </ol>
      {#snippet result()}
        One physical <TeX expr="X" /> error → a chain of flipped qubits whose
        <strong>two endpoints light up</strong>. That is precisely the "defects
        come in pairs" you met on the <strong>matching</strong> page: the two ends
        of a propagated error are the endpoints MWPM tries to reconnect.
      {/snippet}
    </Worked>

    <Callout kind="key" title="Why decoders see correlated checks">
      Propagation is what makes one fault touch several checks. The pairs MWPM
      matches, the correlated checks belief propagation reasons over, and the
      detector-error-model edges all trace back to this: a Pauli fault, conjugated
      forward through the circuit's CX gates, ends up supported on several
      detectors.
    </Callout>
  </div>
</Section>

<Section id="signs" step="06" title="Signs, phases, and the only randomness">
  <p>
    The sign bit is small but load-bearing. <TeX expr="+Z" /> stabilizes
    <TeX expr={String.raw`\ket0`} />, so a <TeX expr="Z" /> measurement returns
    <strong>0</strong>; <TeX expr="-Z" /> stabilizes <TeX expr={String.raw`\ket1`} /> and
    returns <strong>1</strong>. The sign <em>is</em> the measurement outcome. The
    CX sign term <TeX expr={String.raw`x_a z_b(x_b{\oplus}z_a{\oplus}1)`} /> keeps these
    eigenvalues consistent as operators combine.
  </p>

  <Figure
    title="Sign carries the outcome"
    legend={[
      { color: C.ok, mark: "box", label: "+ sign → measures 0" },
      { color: C.bad, mark: "box", label: "− sign → measures 1" },
    ]}
    caption="An X flips +Z↔−Z, i.e. |0⟩↔|1⟩ -- the sign bit alone tracks the Z-measurement result."
  >
    <div class="stage center">
      <div class="bigstate">
        <span class="ket mono">{stateLabel(measPauli)}</span>
        <span class="stab mono">{pauliString(measPauli)} → measure Z = <b style="color:{measOutcome === 0 ? C.ok : C.bad}">{measOutcome}</b></span>
      </div>
      <div class="gaterow">
        <button class="gbtn mono" onclick={flipMeas}>apply X</button>
        <button class="reset" onclick={resetMeas}>reset to +Z</button>
      </div>
    </div>
  </Figure>

  <Callout kind="note" title="Gates are deterministic; only measurement rolls dice">
    Every gate on this page is a <em>deterministic</em> rewrite of operator bits --
    nothing random. In a Clifford simulator the <strong>only</strong> source of
    randomness is measuring a Pauli that anticommutes with a stabilizer, where the
    outcome is a fair coin and the tableau is updated to match. That clean split --
    deterministic operator updates, random only at measurement -- is what makes the
    whole scheme efficient and exactly samplable.
  </Callout>
</Section>

<Section id="scales" step="07" title="Why this scales -- and where it goes next">
  <p>
    Tally the cost. A single-qubit gate edits one column's bits; a
    <TeX expr={String.raw`\textsf{CX}`} /> touches just <strong>two</strong> columns. Each gate
    is <TeX expr="O(n)" /> bit operations across the rows, and the whole state is
    <TeX expr="O(n^2)" /> bits -- versus <TeX expr="2^n" /> complex amplitudes for a
    state vector. That gap is the entire reason qliff can simulate noisy circuits
    on thousands of qubits.
  </p>

  <Figure
    title="Every gate as a bit rule"
    legend={[{ color: C.accent, mark: "box", label: "sign update (from original bits)" }]}
    caption="The complete rule set used on this page -- copied from qliff's tableau core."
  >
    <table class="recap mono">
      <thead><tr><th>gate</th><th>sign ^=</th><th>bit update</th><th>effect</th></tr></thead>
      <tbody>
        {#each recap as r (r.gate)}
          <tr>
            <td class="lt">{r.gate}</td>
            <td style="color:{C.accent}">{r.sign}</td>
            <td>{r.upd}</td>
            <td class="muted">{r.eff}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </Figure>

  <Callout kind="key" title="Where these gates reappear">
    The Cliffords <TeX expr={String.raw`\{\,I, Z, S, S^{\dagger}\,\}`} /> you met
    here are exactly the basis the <strong>coherent-noise</strong> page expands a
    small rotation into. And the faults you watched propagate through CX gates are
    the very edges that <strong>MWPM</strong>, <strong>belief propagation</strong>,
    and the <strong>tensor-network</strong> decoder consume. Operators in,
    operators out -- all the way up the stack.
  </Callout>
</Section>

<style>
  .stage {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .stage.center {
    align-items: center;
  }

  .bigstate {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }

  .ket {
    font-size: 44px;
    font-weight: 700;
    color: var(--fg);
    line-height: 1;
  }

  .stab {
    font-size: 13px;
    color: var(--muted);
  }

  .gaterow,
  .setrow,
  .injrow {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .setrow.wrap {
    flex-wrap: wrap;
  }

  .gbtn {
    min-width: 40px;
    font-size: 15px;
    font-weight: 700;
    padding: 7px 12px;
  }

  .gbtn.small {
    min-width: 32px;
    font-size: 13px;
    padding: 5px 9px;
  }

  .gbtn.on {
    border-color: color-mix(in srgb, var(--accent) 65%, transparent);
    background: var(--grad-soft);
  }

  .reset {
    margin-left: 6px;
    font-size: 12px;
  }

  .curr {
    font-size: 15px;
    color: var(--accent);
    margin-left: 6px;
  }

  .lbl {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .hint {
    font-size: 12.5px;
    color: var(--faint);
    margin: 8px 0 0;
  }

  .bigout,
  .tdout {
    margin: 4px 0;
  }

  /* tables */
  .tbl,
  .rules,
  .recap {
    border-collapse: collapse;
    font-size: 13px;
  }

  .tbl th,
  .tbl td,
  .rules th,
  .rules td,
  .recap th,
  .recap td {
    padding: 5px 12px;
    text-align: left;
    border-bottom: 1px solid var(--line);
  }

  .tbl th,
  .rules th,
  .recap th {
    color: var(--muted);
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .lt {
    font-weight: 700;
  }

  .muted {
    color: var(--muted);
  }

  .splitgrid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 28px;
    align-items: start;
  }

  .toggle-demo {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .tdrow {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .bitbtn {
    font-size: 13px;
    font-weight: 700;
    padding: 6px 12px;
    border-color: color-mix(in srgb, var(--bc) 35%, var(--line));
  }

  .bitbtn.on {
    border-color: var(--bc);
    background: color-mix(in srgb, var(--bc) 14%, transparent);
    color: var(--fg);
  }

  /* CX section */
  .cxgrid {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 18px;
    align-items: center;
  }

  .cxcol {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .cxarrow {
    font-size: 13px;
    color: var(--accent);
    white-space: nowrap;
    text-align: center;
  }

  .cxio {
    margin-top: 2px;
  }

  .bitnote {
    font-size: 11.5px;
    color: var(--faint);
    line-height: 1.5;
  }

  .rules {
    margin-top: 16px;
    width: 100%;
  }

  .inline-tbl {
    width: auto;
    margin-top: 8px;
  }

  .injrow {
    margin-top: 12px;
  }

  .finalbar {
    margin-top: 12px;
    font-size: 13px;
    color: var(--muted);
  }

  @media (max-width: 760px) {
    .splitgrid,
    .cxgrid {
      grid-template-columns: 1fr;
    }

    .cxarrow {
      transform: rotate(90deg);
    }
  }
</style>
