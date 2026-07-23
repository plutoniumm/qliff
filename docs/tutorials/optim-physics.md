---
title: "Optimisations: Physics"
outline: 2
---

# Optimisations: Physics <Badge type="info" text="Tutorial 09 of 10" />

<script setup>
import FrameProp from '../_tut/optim-physics/FrameProp.svelte'
import RareSkip from '../_tut/optim-physics/RareSkip.svelte'
import SignedWeights from '../_tut/optim-physics/SignedWeights.svelte'
</script>

The earlier pages built estimators that spend shots wisely: the [noise sampler](./noise) weights trajectories, the [stratified sampler](./stratified) cancels the weight magnitude before it forms a number. This page works one level below, on the cost of a single shot. Each of the four moves below is the simulator refusing to compute something it already knows. They all live in the Rust core (`src/tableau.rs`), reached through `qliff.noise` and `qliff.qec`.

## The Pauli frame sampler {#frame}

Sampling a noisy Clifford circuit the obvious way builds a fresh tableau for every shot, replays every gate, and rolls the coins. But the gates never change between shots, and in many circuits the measurements never roll a coin. Almost all of that work is redundant.

Split the run in two. First a single **noiseless reference** pass, replaying the gates once and recording each deterministic measurement bit. Then, over the shots, propagate only the **difference** the noise makes: a **Pauli frame**, a phase-free two-bit-per-qubit operator (an X-frame and a Z-frame) that says which Pauli each shot carries relative to the reference. The frame drops the Pauli's phase, the overall $\pm1$ or $\pm i$ in front of the operator, so propagating it becomes pure XOR with no i-phases and no row sums. And because 64 shots pack into one `u64`, a whole cohort moves through a gate in a handful of word operations.

Dropping the phase is safe because a measurement outcome depends only on whether the error commutes or anticommutes with the measured operator, which is set by its X and Z bits, not by its phase. This is the operator's phase, a different thing from the signed quasiprobability weight of the [noise decomposition](./noise). That weight's sign is kept, not dropped, and the [signed-weights section](#signed) below is where it earns its keep.

The frame rules are the [gate bit-algebra](./gates) with the phase term deleted:

<figure class="q-fig">
  <div class="q-fig-title">Every gate acting on a phase-free Pauli frame</div>
  <ul class="q-legend">
    <li style="--c:var(--x)">fx: the X-frame (which shots carry an X-part)</li>
    <li style="--c:var(--z)">fz: the Z-frame (which shots carry a Z-part)</li>
  </ul>
  <table>
    <thead>
      <tr><th>gate</th><th>action on the frame</th><th>why</th></tr>
    </thead>
    <tbody>
      <tr><td><code>H(a)</code></td><td>swap fx[a], fz[a]</td><td>X-frame and Z-frame trade places</td></tr>
      <tr><td><code>S / S&dagger;(a)</code></td><td>fz[a] ^= fx[a]</td><td>one map for both: the phase that split them is gone</td></tr>
      <tr><td><code>X / Y / Z(a)</code></td><td>(nothing)</td><td>a Pauli only changes the phase, which the frame dropped</td></tr>
      <tr><td><code>CX(a,b)</code></td><td><code>fx[b] ^= fx[a]</code><br><code>fz[a] ^= fz[b]</code></td><td>X copies forward, Z copies back</td></tr>
      <tr><td><code>CZ(a,b)</code></td><td><code>fz[a] ^= fx[b]</code><br><code>fz[b] ^= fx[a]</code></td><td>symmetric, one pass</td></tr>
      <tr><td><code>SWAP(a,b)</code></td><td>swap frames a, b</td><td>exchange the two columns</td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">Copied from frame_chunk in src/tableau.rs. Compare the CX and CZ rows against the signed versions on the gates page: identical bit moves, no phase term. S and S-dagger collapse to the same rule once the phase is dropped, so the frame cannot tell them apart and does not need to.</div>
</figure>

A **deterministic** measurement is then free. Its noiseless value is a known reference bit $b_{\text{ref}}$, and the noise only flips it when the frame carries an X-part on that qubit. So the recorded outcome for all 64 shots in the word is one XOR:

$$
\text{record} \;=\; b_{\text{ref}} \oplus \text{fx}[q],
$$

a single word operation for the whole cohort, no tableau consulted. The frame cannot handle a **random** measurement, because a coin flip is not reference-XOR-anything. So the reference pass returns `None` the moment it meets one, and the sampler falls back to the per-shot tableau path (`sample_batch`).

**Bit-packed frames through one syndrome check**

<SvelteIsland :component="FrameProp" />

Legend:
- coloured cell = shot carries an X-part on that qubit
- fx q0, fx q1 = X faults on the two data qubits
- record = ancilla word, reference XOR fx[a]
- toggle off = random final measurement (knocks out the frame path)

Take a circuit the frame path can handle, a deterministic memory experiment. There the speedup is a large constant factor over building a tableau per shot, because the per-shot cost falls from "replay every gate on a tableau" to "XOR a few words":

<figure class="q-fig">
  <div class="q-fig-title">Frame sampler vs per-shot tableau, same repetition-code memory</div>
  <ul class="q-legend">
    <li style="--c:var(--bad)">sample_batch: one full tableau per shot</li>
    <li style="--c:var(--ok)">frame_run: bit-packed frames, 64 shots per word</li>
  </ul>
  <table>
    <thead>
      <tr><th>distance</th><th>rounds</th><th>shots</th><th style="color:var(--bad)">sample_batch</th><th style="color:var(--ok)">frame_run</th><th>ratio</th></tr>
    </thead>
    <tbody>
      <tr><td>5</td><td>5</td><td>100k</td><td style="color:var(--bad)">0.18 s</td><td style="color:var(--ok)">0.001 s</td><td>~160x</td></tr>
      <tr><td>11</td><td>11</td><td>200k</td><td style="color:var(--bad)">1.11 s</td><td style="color:var(--ok)">0.010 s</td><td>~110x</td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">Measured on this machine, 2026-07-23, X_ERROR at p = 0.02, best of several runs. Both paths return statistically identical detector records, and the ratio is the stable quantity while the absolute wall-clock moves with machine load and core count. The reference pass is the frame method's one serial cost, and CompiledSampler computes it once and reuses it across a whole logical-error-rate sweep.</div>
</figure>

::: details Worked example: why the repetition memory is frame-eligible

A distance-5 bit-flip repetition memory over 5 rounds emits 20 ancilla parities plus a final 5-qubit data readout, 25 measurements. In the noiseless run every data qubit stays in $\ket0$ and every Z parity is even, so all 25 read 0: a fully deterministic reference.

```python
from qliff.noise import CompiledSampler
from qliff.qec.codes import repetition_code

code = repetition_code(distance=5, rounds=5, p=0.02, channel="X_ERROR")
sampler = CompiledSampler(code)
instrs, _tables = sampler._compiled
ref = sampler._core.frame_reference(instrs)
print("deterministic measurements:", len(ref))
print("all read 0 in the reference:", not any(ref))
# -> deterministic measurements: 25
# -> all read 0 in the reference: True
```

Now break it. A GHZ state measured in the Z basis is a fair coin on the first qubit, so the reference pass gives up and the sampler uses the per-shot tableau:

```python
from qliff import Circuit
from qliff.noise import CompiledSampler

ghz = Circuit(3)
ghz.append("H", 0)
ghz.append("CX", [0, 1])
ghz.append("CX", [1, 2])
ghz.append("M", [0, 1, 2])
gs = CompiledSampler(ghz)
print(gs._core.frame_reference(gs._compiled[0]))
# -> None
```

**Result:** the frame path is not a special case of a special code; it is precisely the circuits whose measurements are all deterministic in the noiseless run, which is most memory experiments and no logical-coin experiment.

:::

## Rare-error noise: skip to the faulty shots {#rare}

Inside the frame engine there is a second refusal to do redundant work. A single-qubit noise location fires with some per-shot probability $\varphi$, and at QEC error rates $\varphi \sim 10^{-3}$. Visiting all 64 shots in a word to draw a fault that almost never happens is wasteful: 999 of every 1000 draws come back "no fault".

The fix uses the fact that the faulty shots are Bernoulli($\varphi$), so the **gaps** between them are geometric. Instead of drawing a coin per shot, draw the gap directly and jump:

$$
\text{skip} \;=\; \left\lfloor \frac{\ln(1-U)}{\ln(1-\varphi)} \right\rfloor,
\qquad U \sim \text{Uniform}[0,1),
$$

which lands on the next faulty shot without touching the quiet ones in between. The loop does one skip and one branch draw per **faulty** shot, so it touches $\sim \varphi \cdot \text{shots}$ shots and the work drops by $\sim 1/\varphi$. The two edge cases fall out cleanly: a location with no fault mass ($\varphi = 0$) is skipped entirely, and $\varphi = 1$ makes $\ln(1-\varphi)$ non-finite, so every skip is zero and every shot faults.

**How few shots a rare location touches**

<SvelteIsland :component="RareSkip" />

Legend:
- lit cell = a shot the location faulted on (the only shots the loop visits)
- `uniform draws spent` = one geometric skip per faulty shot
- `work ratio` = shots / faults, tracking 1 / phi

Counting the faults confirms the touch rate: a lone `X_ERROR` location, measured, records a 1 on the shots it flipped.

```python
from qliff import Circuit
from qliff.noise import CompiledSampler

for phi in (0.001, 0.01, 0.1):
    c = Circuit(1)
    c.append("X_ERROR", [0], phi)
    c.append("M", [0])
    faulted = int(CompiledSampler(c).sample(100_000, seed=1).sum())
    print(f"phi={phi:<6} faulted {faulted:5d} of 100000")
# -> phi=0.001  faulted    97 of 100000
# -> phi=0.01   faulted   989 of 100000
# -> phi=0.1    faulted  9916 of 100000
```

At $\varphi = 10^{-3}$ the sampler wrote 97 faults into 100000 shots and did skip-arithmetic 97 times. The other 99903 shots cost nothing but the XOR that carries their (empty) frame forward.

## Signed weights for non-Pauli noise {#signed}

Pauli noise is a coin. Amplitude damping and coherent rotation are not. Both are still handled by **one** tableau per trajectory rather than a state vector, because qliff writes a non-Pauli channel as a signed quasiprobability mix of Clifford branches. The [noise page](./noise) builds that decomposition and the [stratified page](./stratified) drives its variance down. This section's optimisation is only the sampling loop, which lives in Rust (`ColTableau::estimate` / `estimate_chunk`), off the Python GIL.

Per trajectory: at each noise location, draw **one** branch with probability $|w_k|/\gamma$ (where $\gamma = \sum_k |w_k|$ is the location's negativity), apply that branch's Clifford ops, and multiply the running weight by $\operatorname{sign}(w_k)\,\gamma$. After the last gate, read the observable off the final tableau in one word-parallel pass. The estimate is the mean of $w\cdot\langle O\rangle$ over shots, unbiased for **any** channel:

$$
\langle O\rangle \;\approx\; \frac1N \sum_{\text{shots}} w\,\langle O\rangle_{\text{shot}},
\qquad
w \;=\; \prod_i \operatorname{sign}(w_{k_i})\,\gamma_i .
$$

Two details make it cheap. The branch ops are plain Clifford opcodes plus one extra, **opcode 9 = reset**, which is how amplitude damping's $R$ branch collapses a qubit to $\ket0$ without leaving the stabilizer formalism. And every weight has the **same magnitude** $\Gamma = \prod_i \gamma_i$, so only its sign varies from shot to shot. The whole trajectory payload is that one bit: the quasiprobability sign, the one the frame sampler could discard but this loop must keep.

**One branch per location, weight = sign x Gamma**

<SvelteIsland :component="SignedWeights" />

Legend:
- grey chip `I` = identity (no-fault) branch
- green chip `+` = positive-weight fault branch
- red chip `-` = negative-weight fault branch
- `+Gamma / -Gamma` = trajectory weight, sign set by the red-chip parity

Run it against a known state and the estimate lands where the density matrix says it should. Exciting a qubit and damping it at rate $p$ leaves $\rho = (1-p)\ket1\bra1 + p\ket0\bra0$, so $\langle Z\rangle = 2p-1$:

```python
from qliff import Circuit
from qliff.noise import Sampler

c = Circuit(1)
c.append("X", [0])                      # |1>, so damping has population to act on
c.append("AMPLITUDE_DAMP", [0], 0.3)
print(round(Sampler(c).expect("Z", shots=200_000, seed=3), 4))
# -> -0.3975       (true rho gives <Z> = 2p - 1 = -0.4)
```

The whole trajectory loop of draw, apply, weight, and evaluate ran in the Rust core. Python only handed it the compiled branch tables and read back one float.

## Word-parallel measurement {#measure}

The last optimisation is under the gate algebra, in the one place a stabilizer simulator cannot avoid a global operation: measuring a Pauli that anticommutes with the state needs a **rowsum**, combining two length-$2n$ Pauli rows and tracking the power of $i$ that accumulates. The [gates page](./gates) covers the per-gate sign bookkeeping and the one-pass CZ. What it does not cover is how that rowsum is done 64 lanes at a time.

The phase contribution of multiplying two Paulis, lane by lane, is a function $g \in \{-1,0,+1\}$ of the four bits $(x_i, z_i, x_h, z_h)$. Written per qubit it is a branch; written per **word** it is two masks and two popcounts. The six Pauli-pair cases that give $+1$ live on disjoint lanes, as do the six that give $-1$, so OR them together and count:

<figure class="q-fig">
  <div class="q-fig-title">word_g: the rowsum phase, 64 lanes at once</div>
  <ul class="q-legend">
    <li style="--c:var(--ok)">+1 lanes: (X,Y) (Z,X) (Y,Z)</li>
    <li style="--c:var(--bad)">-1 lanes: (X,Z) (Z,Y) (Y,X)</li>
  </ul>

```rust
fn word_g(xi: u64, zi: u64, xh: u64, zh: u64) -> i32 {
    let plus  = (xi & !zi & xh & zh) | (!xi & zi & xh & !zh) | (xi & zi & !xh & zh);
    let minus = (xi & !zi & !xh & zh) | (!xi & zi & xh & zh) | (xi & zi & xh & !zh);
    plus.count_ones() as i32 - minus.count_ones() as i32
}
```

  <div class="q-fig-note">One machine popcount per mask replaces 64 per-qubit branches. rowsum accumulates 2*r_h + 2*r_i + sum_k word_g(...) a word at a time, and the same trick drives the expectation used by the signed estimator above. Tail lanes past n are all-zero (identity), which contributes 0, so no masking is needed.</div>
</figure>

`word_g` on a full word equals the qubit-by-qubit sum of the scalar phase $g$. That is the property the core's test asserts, and it holds because the plus and minus Pauli-pair cases never share a lane.

Four refusals to do redundant work, and they compound. The frame sampler pays for the gates once and carries 64 shots per word. The rare-error skip stops it visiting shots that do nothing. The signed estimator keeps non-Pauli noise inside one tableau. And `word_g` measures a whole word in two popcounts. None of them change a single number the sampler returns. They change how little it has to compute to return it, which is the entire budget for a scalable noise simulation. The [logical error rate](./ler) is what all of this is spent on. The next page, [Optimisations: Memory](./optim-memory), is where the tableau itself gets smaller.
