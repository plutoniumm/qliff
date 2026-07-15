---
title: Simulating Noise
outline: 2
---

# Simulating Noise <Badge type="info" text="Tutorial 06 of 7" />

> Amplitude damping is not a Pauli flip, yet a Clifford simulator can run it: three Clifford branches, signed weights, one branch drawn per shot.

<script setup>
import Trajectory from '../_tut/noise/Trajectory.svelte'
</script>

## The running example: amplitude damping

Every section of this page uses the same channel: **amplitude damping** (AD). A qubit stores energy. $\ket 1$ is the excited state, $\ket 0$ the ground state. Left alone, an excited qubit leaks its energy into the environment and relaxes toward $\ket 0$. One number $p$ sets the strength: over the time step being modelled, an excited qubit decays with probability $p$.

The standard description is a pair of **Kraus operators**:

$$
K_0=\begin{pmatrix}1&0\\0&\sqrt{1-p}\end{pmatrix},\qquad
K_1=\begin{pmatrix}0&\sqrt{p}\\0&0\end{pmatrix},\qquad
\mathcal E(\rho)=K_0\,\rho\,K_0^\dagger+K_1\,\rho\,K_1^\dagger .
$$

$K_1$ is the decay event: it maps $\ket 1$ to $\sqrt p\,\ket 0$. $K_0$ is the no-decay case: it keeps $\ket 0$ and shrinks the $\ket 1$ amplitude by $\sqrt{1-p}$ (seeing no decay is itself information, so the state still changes).

We fix $p = 0.1$ for the whole page. One target number to hold on to: start in $\ket 1$ and apply the channel once. The qubit decays with probability $0.1$ and stays with probability $0.9$, so

$$
\langle Z\rangle \;=\; (+1)\,p+(-1)(1-p) \;=\; 2p-1 \;=\; -0.8 .
$$

By the end of the page a stabilizer simulator computes this number, and every step it takes to get there will be on the table.

## Why the simulator cannot run it directly

A QEC experiment has hundreds of qubits and needs millions of shots. Storing the full quantum state, $2^n$ complex amplitudes, is off the table past a few dozen qubits:

<figure class="q-fig">
  <div class="q-fig-title">Memory: state vector vs stabilizer tableau</div>
  <ul class="q-legend">
    <li style="--c:var(--bad)">state vector: 2<sup>n</sup> amplitudes</li>
    <li style="--c:var(--ok)">stabilizer tableau: ~n<sup>2</sup> bits</li>
  </ul>
  <table>
    <thead>
      <tr><th>qubits n</th><th style="color:var(--bad)">state vector</th><th style="color:var(--ok)">tableau</th></tr>
    </thead>
    <tbody>
      <tr><td>10</td><td style="color:var(--bad)">~10<sup>3</sup></td><td style="color:var(--ok)">420</td></tr>
      <tr><td>40</td><td style="color:var(--bad)">~10<sup>12</sup></td><td style="color:var(--ok)">6,480</td></tr>
      <tr><td>100</td><td style="color:var(--bad)">~10<sup>30</sup></td><td style="color:var(--ok)">40,200</td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">The state vector needs 2<sup>n</sup> amplitudes; a stabilizer tableau needs about n<sup>2</sup> bits. At n = 100 that is ~10<sup>30</sup> numbers against 40,200 bits.</div>
</figure>

The way out is the **Gottesman-Knill theorem**: a circuit made only of **Clifford** operations (H, S, CX, Pauli gates, measurement, reset) acting on stabilizer states can be simulated with an $n^2$-bit tableau. qliff's core is such a simulator. This is what makes QEC-scale simulation possible at all, and it is also the constraint: the tableau can only be moved by Clifford operations.

$K_0$ is not one of them. It is not even unitary: it scales the two basis amplitudes by different factors, and no Clifford gate shrinks an amplitude. There is no gate to call.

A Pauli channel avoids the problem. `X_ERROR(p)` means: with probability $1-p$ do nothing, with probability $p$ apply $X$. Both options are Clifford gates and the two probabilities are non-negative, so the simulator can flip a coin per shot and apply one of them. AD does not split that way: expand each Kraus operator in the Pauli basis and you get $K_0 = 0.974\,I + 0.026\,Z$ and $K_1 = 0.158\,(X + iY)$ at $p=0.1$. Neither is a single Pauli times a number, so no assignment of flip probabilities reproduces the channel. [Tutorial 05](./coherent) makes the same point geometrically on the Bloch sphere.

## The fix: a menu of Clifford branches

The channel can still be written as a weighted sum of Clifford operations, if the weights are allowed to be negative:

$$
\mathcal E(\rho)\;=\;\sum_k q_k\, C_k\,\rho\,C_k^\dagger,\qquad \sum_k q_k = 1 .
$$

Think of it as a menu. Each line (a **branch**) is a weight $q_k$ plus a short list of Clifford gates $C_k$. For AD three lines are enough, using the identity, the phase flip $Z$, and the reset $R$ to $\ket 0$:

| branch | gates | weight $q_k$ | at $p=0.1$ |
| --- | --- | --- | --- |
| no fault | none | $\big((1-p)+\sqrt{1-p}\big)/2$ | $+0.9243$ |
| phase flip | $Z$ | $\big((1-p)-\sqrt{1-p}\big)/2$ | $-0.0243$ |
| reset | $R$ | $p$ | $+0.1000$ |

Why these numbers? The reset branch carries the population transfer: it moves weight from $\ket 1$ to $\ket 0$ at rate $p$, which is $K_1$'s job. The $I$ and $Z$ branches then have two conditions to meet: coherences (the off-diagonal entries of $\rho$) must shrink by $q_I - q_Z = \sqrt{1-p}$, and the surviving populations must scale by $q_I + q_Z = 1-p$. Solving those two equations gives the formulas in the table. And since $\sqrt{1-p} > 1-p$ for any $0 < p < 1$, the solution forces $q_Z < 0$. The negative weight is not a trick; it is the only way the sum can shrink an amplitude by $\sqrt{1-p}$ while every ingredient is Clifford. With it, the three-branch menu reproduces the Kraus form exactly.

<figure class="q-fig">
  <div class="q-fig-title">The AD menu at p = 0.1</div>
  <ul class="q-legend">
    <li style="--c:var(--ok)">positive weight</li>
    <li style="--c:var(--bad)">negative weight</li>
  </ul>
  <ul class="q-bars">
    <li style="--v:.9243;--c:var(--ok)"><b>I (no fault)</b><span class="q-track"></span><i>+0.9243</i></li>
    <li style="--v:.0243;--c:var(--bad)"><b>Z (phase flip)</b><span class="q-track"></span><i>-0.0243</i></li>
    <li style="--v:.1;--c:var(--ok)"><b>R (reset)</b><span class="q-track"></span><i>+0.1000</i></li>
  </ul>
  <div class="q-fig-note">Bar length is |q_k|, colour is the sign. The signed weights sum to 1; their absolute values sum to gamma = 1.0487.</div>
</figure>

qliff builds this menu for you, and you can read it directly:

```python
from qliff.noise import make_channel

for weight, ops in make_channel("AMPLITUDE_DAMP", 0.1).branches((0,)):
    label = ops[0][0] if len(ops) > 0 else "I"
    print(f"{label}  {weight:+.4f}")
# -> I  +0.9243
# -> Z  -0.0243
# -> R  +0.1000
```

The weights sum to $1$, but they are not probabilities: one of them is below zero, so you cannot draw a branch "with probability $q_k$". The quantity that measures how far the menu is from a probability distribution is

$$
\gamma \;=\; \sum_k |q_k| \;=\; \sqrt{1-p}+p \;=\; 1.0487 \quad (p=0.1),
$$

with $\gamma = 1$ if and only if all weights are non-negative. Everything that follows is about sampling from this menu anyway, and paying for it with $\gamma$.

## How the simulator picks a branch

Here is the sampling rule, in full. At **every noise location, in every shot**, the simulator does five things:

1. Compute $\gamma = \sum_k |q_k|$. For AD at $p=0.1$: $\gamma = 0.9243 + 0.0243 + 0.1 = 1.0487$.
2. Divide $[0, \gamma)$ into one slot per branch, of length $|q_k|$: the $I$ slot is $[0,\,0.9243]$, the $Z$ slot $(0.9243,\,0.9487]$, the $R$ slot $(0.9487,\,1.0487]$.
3. Draw a uniform random number $u \in [0,1)$ and scale it: $t = u\,\gamma$.
4. Apply the gates of the branch whose slot contains $t$. One branch, and only that branch: the simulation never forks.
5. Multiply the shot's running **weight** by $\operatorname{sign}(q_k)\,\gamma$. The weight starts at $1$ and one shot has one weight.

So each branch is picked with probability $|q_k|/\gamma$. For AD at $p=0.1$ the pick probabilities are $0.9243/1.0487 = 0.8814$ for $I$, $0.0232$ for $Z$, and $0.0954$ for $R$.

Walk one draw by hand. Say the generator returns $u = 0.90$:

- $t = 0.90 \times 1.0487 = 0.9438$.
- Walk the slots: $0.9438 > 0.9243$, so not $I$; $0.9438 \le 0.9487$, so the $Z$ slot contains it.
- Apply $Z$ to the qubit.
- $q_Z < 0$, so the weight multiplies by $\operatorname{sign}(q_Z)\,\gamma = -1.0487$. The shot's weight is now negative.

The three possible outcomes of a single location, side by side:

| draw $u$ | $t = u\gamma$ | slot | gates | weight factor |
| --- | --- | --- | --- | --- |
| 0.50 | 0.5243 | $I$ | none | $+1.0487$ |
| 0.90 | 0.9438 | $Z$ | $Z$ | $-1.0487$ |
| 0.97 | 1.0172 | $R$ | reset | $+1.0487$ |

Note the factor has magnitude $\gamma$ in every row, including the no-fault one. The sign is the only thing the branch controls. `Channel.sample` is this rule verbatim, and its long-run pick frequencies match the slot sizes:

```python
import random

from qliff.noise import make_channel

ch = make_channel("AMPLITUDE_DAMP", 0.1)
rng = random.Random(2026)

counts = {"I": 0, "Z": 0, "R": 0}
factor_of = {}
for _ in range(100_000):
    factor, ops = ch.sample((0,), rng)
    label = ops[0][0] if len(ops) > 0 else "I"
    counts[label] += 1
    factor_of[label] = factor

for label in ("I", "Z", "R"):
    frac = counts[label] / 100_000
    print(f"{label}  picked {frac:.4f} of shots, factor {factor_of[label]:+.4f}")
# -> I  picked 0.8827 of shots, factor +1.0487
# -> Z  picked 0.0232 of shots, factor -1.0487
# -> R  picked 0.0941 of shots, factor +1.0487
```

A circuit has many noise locations, and a **trajectory** is one pass through all of them: roll at the first location, apply its branch, roll at the second, and so on, multiplying the factors into a single per-shot weight. After $L$ locations the weight is $\pm\gamma^L$. The stepper below runs one seeded trajectory through four AD locations, one die roll at a time.

**One shot through four damping locations**

<SvelteIsland :component="Trajectory" />

*Four qubits, each with one `AMPLITUDE_DAMP(p)` location. Step the location control: each step rolls one die. The bar shows the three $|q_k|$ slots on $[0,\gamma)$; the marker is the draw $t = u\gamma$; the fired branch labels the square on the wire. At the default seed the second location draws the $Z$ branch, so the running weight flips sign, and after all four locations it is $-\gamma^4 = -1.209$. Same seed, same shot, every time.*

Legend:
- `?` location not yet rolled
- `I` no-fault branch fired (factor $+\gamma$)
- `Z` phase-flip branch fired (negative weight, factor $-\gamma$)
- `R` reset branch fired (factor $+\gamma$)
- vertical marker: the draw $t = u\gamma$ on the slot bar
- highlighted square: the location whose roll is displayed

## From weighted shots to answers

A single trajectory is not the channel; only the average over shots is. Say you want the expectation of some outcome function $f$ (for us: the measured $Z$ value of the qubit). The estimator is the **weighted mean**

$$
\hat f \;=\; \frac{1}{N}\sum_{s=1}^{N} w_s\, f_s ,
$$

where $w_s$ is shot $s$'s accumulated weight and $f_s$ its outcome. This is unbiased, and the proof is one line. A branch is picked with probability $|q_k|/\gamma$ and contributes $\operatorname{sign}(q_k)\,\gamma\,f_k$, so its average contribution is

$$
\frac{|q_k|}{\gamma}\cdot\operatorname{sign}(q_k)\,\gamma\, f_k \;=\; q_k\, f_k ,
$$

the term the channel definition asks for. The $\gamma$ cancels; the sign restores the negative weight.

Check it on the target from the top of the page: $\langle Z\rangle$ of a damped $\ket 1$. The branch outcomes are $f_I = -1$ (still $\ket 1$), $f_Z = -1$ ($Z\ket 1 = -\ket 1$, same measured value), $f_R = +1$ (reset to $\ket 0$). The weighted average is

$$
q_I(-1) + q_Z(-1) + q_R(+1) \;=\; -(1-p) + p \;=\; -0.8 .
$$

`Circuit.estimate` runs this estimator end to end:

```python
from qliff import Circuit

damped = Circuit(1)
damped.X(0)                    # prepare |1>
damped.AMPLITUDE_DAMP(0, 0.1)  # one damping location
print("estimate", round(damped.estimate("Z", shots=50_000, seed=3), 3))
print("truth   ", 2 * 0.1 - 1)
# -> estimate -0.8
# -> truth    -0.8
```

Two special cases are worth naming:

- **Pauli channels collapse to counting.** If every $q_k \ge 0$ then $\gamma = 1$ and every shot's weight is $+1$, so the weighted mean is a plain frequency count. That is why `compile_sampler` and `detector_sampler` hand you raw bitstrings for Pauli-noise circuits: no weights needed. For non-Pauli noise a bitstring cannot carry a signed weight, so those samplers refuse and `estimate` is the interface.
- **Dropping the signs gives the wrong answer.** If you sampled branches and averaged $f$ without the weights, you would be estimating the wrong channel: the one with weights $|q_k|/\gamma$. The Std Python tab below shows the miss.

## The price of the minus sign

The factor $\operatorname{sign}(q_k)\,\gamma$ has magnitude $\gamma$ at every location, so after $L$ noise locations every shot carries $|w| = \gamma^L$. The estimator averages numbers of size $\gamma^L$ to produce a result of size $1$, and cancellation between $+$ and $-$ shots does the work. Its variance therefore grows like $\gamma^{2L}$: to keep a fixed error bar you need on the order of $\gamma^{2L}$ times more shots.

For AD at $p=0.1$, $\gamma^2 = 1.10$: each location costs 10% more shots. Ten locations cost a factor of $2.6$. A hundred cost $1.0487^{200} \approx 1.3\times 10^4$. This exponential blow-up is the **sign problem**, and it is a property of the method, not a bug: the simulation stays polynomial per shot, and the bill is paid in shot count.

The flip side: Pauli channels have $\gamma = 1$ and cost nothing extra, no matter how many locations. That is why qliff keeps Pauli noise on its fast batched sampler and reserves weighted sampling for the locations whose physics demands it.

## From a trajectory to a syndrome

A decoder never sees which branches fired. It sees **detection events**, and they come from measurements. The recipe:

1. Run the circuit once with no noise. Every detector (a parity of measurement records, [Tutorial 02](./mwpm)) gets a deterministic reference value.
2. Run a noisy trajectory. The branches' gates ride along with the shot; for Pauli noise this is a **Pauli frame**, two bits per qubit saying "an $X$ flip is pending here" and "a $Z$ flip is pending here". An $X$ or $Y$ flip on a qubit inverts its Z-basis measurement record; a $Z$ flip does not.
3. XOR each measured parity against its reference:

$$
\text{detection event}_d \;=\; \text{parity}_d \,\oplus\, \text{reference}_d .
$$

A detector fires when noise changed its value. The resulting bit string is the **syndrome**, the decoder's only input.

<figure class="q-fig">
  <div class="q-fig-title">Trajectory to syndrome: repetition code, one X error on q2</div>
  <ul class="q-legend">
    <li style="--c:var(--x)">data qubit with X error</li>
    <li style="--c:var(--muted)">clean data qubit</li>
    <li style="--c:var(--bad)">Z-check lit (detection event = 1)</li>
    <li style="--c:var(--z)">Z-check quiet (0)</li>
  </ul>
  <div style="color:var(--muted);font-size:.8em;margin:.4rem 0 -.4rem">data qubits</div>
  <div class="q-cells">
    <div class="q-cell" style="--c:var(--muted)"><b>I</b><span class="q-bits">x=0 z=0</span><small>q0</small></div>
    <div class="q-cell" style="--c:var(--muted)"><b>I</b><span class="q-bits">x=0 z=0</span><small>q1</small></div>
    <div class="q-cell" style="--c:var(--x)"><b>X</b><span class="q-bits">x=1 z=0</span><small>q2</small></div>
    <div class="q-cell" style="--c:var(--muted)"><b>I</b><span class="q-bits">x=0 z=0</span><small>q3</small></div>
    <div class="q-cell" style="--c:var(--muted)"><b>I</b><span class="q-bits">x=0 z=0</span><small>q4</small></div>
  </div>
  <div style="color:var(--muted);font-size:.8em;margin:.2rem 0 -.4rem">Z-checks (parity of neighbouring data qubits)</div>
  <div class="q-cells">
    <div class="q-cell" style="--c:var(--z)"><b>0</b><span class="q-bits">q0,q1</span><small>quiet</small></div>
    <div class="q-cell" style="--c:var(--bad)"><b>1</b><span class="q-bits">q1,q2</span><small>lit</small></div>
    <div class="q-cell" style="--c:var(--bad)"><b>1</b><span class="q-bits">q2,q3</span><small>lit</small></div>
    <div class="q-cell" style="--c:var(--z)"><b>0</b><span class="q-bits">q3,q4</span><small>quiet</small></div>
  </div>
  <div style="font-family:var(--vp-font-family-mono,monospace);margin-top:.6rem">syndrome = [0, 1, 1, 0]</div>
  <div class="q-fig-note">One repetition-code round with an X error on q2. Each qubit's Pauli-frame bits (x, z) are shown; a Z-check fires when its two neighbours disagree, so the lone error lights the two checks that straddle it.</div>
</figure>

In code, with the error rate set to $0.2$ so both outcomes appear:

```python
from qliff import Circuit

rep = Circuit()
rep.X_ERROR([1], 0.2)     # noise on the middle of three data qubits 0,1,2
rep.append("CX", [0, 3])  # ancilla 3 reads the parity of q0, q1
rep.append("CX", [1, 3])
rep.append("CX", [1, 4])  # ancilla 4 reads the parity of q1, q2
rep.append("CX", [2, 4])
rep.append("MR", [3])
rep.append("MR", [4])
rep.detector(-2)
rep.detector(-1)

dets, _obs = rep.detector_sampler().sample(20_000, seed=5)
both = (dets[:, 0] == 1) & (dets[:, 1] == 1)
one = dets.sum(axis=1) == 1
print("both checks fire ", round(float(both.mean()), 4))
print("only one fires   ", round(float(one.mean()), 4))
# -> both checks fire  0.2009
# -> only one fires    0.0
```

The error on q1 fires both of its neighbouring checks together (at its rate, $0.2$) or neither; never one alone. That correlation structure is what the [matching](./mwpm), [BP](./bp), and [tensor-network](./tn) decoders exploit.

How does AD fit this picture? Branch by branch: the $Z$ branch never flips a Z-basis record ($Z$ commutes with measuring $Z$), the reset branch flips the record of a qubit that held $\ket 1$, and the no-fault branch flips nothing. Meanwhile all three multiply the shot's weight by $\pm\gamma$. Syndrome visibility and weight are separate ledgers: the syndrome is what the decoder reads, the weight is how much the shot counts when you average its outcome, logical failures included. That weighted failure average is the logical error rate, and it is the subject of [Tutorial 07](./ler).

## Implementation {#implementation}

The tabs rebuild the page in code, all on the same AD running example.

**Pseudocode.** The per-shot loop: one tableau, one running weight, one branch drawn per noise location, detection events from the XOR with a noiseless reference run.

**Std Python.** The AD algebra in NumPy: the Kraus pair, the Pauli expansion showing no flip model fits, the signed menu with its pick probabilities, and a weighted Monte Carlo for $\langle Z\rangle$ that lands on $2p-1$ while the sign-blind average misses.

**Qliff.** The same objects from the library: `branches` for the menu, `sample` for seeded draws with their $\pm\gamma$ factors, `estimate` for the weighted answer, and a Pauli channel collapsing to plain counting.

::: code-group

```text [Pseudocode]
reference = run the circuit once with no noise     # deterministic record bits

for shot in 1..N:
    state  = tableau with all qubits in |0>
    weight = 1
    for instruction in circuit:
        if instruction is a noise location:        # e.g. AMPLITUDE_DAMP(p)
            menu  = its branches [(q_k, Clifford ops)]
            gamma = sum_k |q_k|                    # 1.0487 for AD(0.1)
            draw one k with probability |q_k| / gamma
            apply that branch's ops to state       # nothing, Z, or reset
            weight = weight * sign(q_k) * gamma
        else:
            apply the Clifford gate / measurement to state
    for each detector d:
        event[d] = parity of d's records XOR reference parity of d
    emit (events, weight)                          # |weight| = gamma^L

estimate of E[f] = (1/N) * sum over shots of weight * f(shot)
# Pauli noise: every q_k >= 0, so gamma = 1 and every weight = 1,
# and the estimate is a plain frequency count
```

```python [Std Python]
import numpy as np

rng = np.random.default_rng(7)
p = 0.1

# 1. Amplitude damping as Kraus operators. K0 shrinks the |1> amplitude,
#    K1 moves it to |0> (a decay event).
K0 = np.array([[1.0, 0.0], [0.0, np.sqrt(1.0 - p)]])
K1 = np.array([[0.0, np.sqrt(p)], [0.0, 0.0]])
print("trace preserving:", np.allclose(K0.T @ K0 + K1.T @ K1, np.eye(2)))
# -> trace preserving: True

# 2. Neither operator is a number times one Pauli, so no set of flip
#    probabilities reproduces the channel. Expand K = sum_P c_P P:
paulis = {
    "I": np.eye(2, dtype=complex),
    "X": np.array([[0, 1], [1, 0]], dtype=complex),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "Z": np.array([[1, 0], [0, -1]], dtype=complex),
}
for name, K in [("K0", K0), ("K1", K1)]:
    coeff = [np.trace(P @ K) / 2.0 for P in paulis.values()]
    print(name, np.round(coeff, 3))
# -> K0 [0.974+0.j 0.   +0.j 0.   +0.j 0.026+0.j]
# -> K1 [0.   +0.j    0.158+0.j    0.   +0.158j 0.   +0.j   ]

# 3. The signed Clifford menu {I, Z, Reset} and its sampling table.
root = np.sqrt(1.0 - p)
q = np.array([(1.0 - p + root) / 2.0, (1.0 - p - root) / 2.0, p])
gamma = np.abs(q).sum()
print("weights", np.round(q, 4), " sum", round(q.sum(), 4), " gamma", round(gamma, 4))
# -> weights [ 0.9243 -0.0243  0.1   ]  sum 1.0  gamma 1.0487
print("pick probabilities", np.round(np.abs(q) / gamma, 4))
# -> pick probabilities [0.8814 0.0232 0.0954]

# 4. Monte Carlo for <Z> on a damped |1>. Branch outcomes: I keeps |1>
#    (Z reads -1), Z keeps |1> (-1), Reset gives |0> (+1). Truth: 2p - 1.
f = np.array([-1.0, -1.0, +1.0])
shots = 400_000
k = rng.choice(3, size=shots, p=np.abs(q) / gamma)
weighted = (np.sign(q)[k] * gamma * f[k]).mean()
naive = f[k].mean()
print("truth   ", 2 * p - 1)
print("weighted", round(float(weighted), 4))
print("naive   ", round(float(naive), 4), " (its limit:", round(float(np.abs(q) @ f / gamma), 4), ")")
# -> truth    -0.8
# -> weighted -0.8017
# -> naive    -0.811  (its limit: -0.8093 )

# 5. The sign-blind miss is small here because gamma is near 1. At p = 0.5
#    the truth is 0 and dropping the signs misses by 0.17.
p2 = 0.5
root2 = np.sqrt(1.0 - p2)
q2 = np.array([(1.0 - p2 + root2) / 2.0, (1.0 - p2 - root2) / 2.0, p2])
print("truth", 2 * p2 - 1, " naive limit", round(float(np.abs(q2) @ f / np.abs(q2).sum()), 4))
# -> truth 0.0  naive limit -0.1716
```

```python [Qliff]
import random

from qliff import Circuit
from qliff.noise import make_channel

# 1. The AD menu, straight from the library: (weight, ops) branches.
ch = make_channel("AMPLITUDE_DAMP", 0.1)
for weight, ops in ch.branches((0,)):
    label = ops[0][0] if len(ops) > 0 else "I"
    print(label, f"{weight:+.4f}")
# -> I +0.9243
# -> Z -0.0243
# -> R +0.1000

# 2. Four seeded draws, one per noise location of a 4-location shot.
#    sample() picks a branch with probability |q|/gamma and returns
#    (sign(q) * gamma, ops) for the branch it picked.
rng = random.Random(106)
weight = 1.0
for _ in range(4):
    factor, ops = ch.sample((0,), rng)
    weight *= factor
    print(round(factor, 4), ops)
print("shot weight", round(weight, 4))
# -> 1.0487 []
# -> -1.0487 [('Z', (0,))]
# -> 1.0487 []
# -> 1.0487 [('R', (0,))]
# -> shot weight -1.2094

# 3. The weighted estimator end to end: <Z> after damping |1>.
damped = Circuit(1)
damped.X(0)
damped.AMPLITUDE_DAMP(0, 0.1)
print(round(damped.estimate("Z", shots=50_000, seed=3), 3))
# -> -0.8

# 4. A Pauli channel has gamma = 1, so sampling is plain counting:
#    the flip rate comes back as a frequency.
flip = Circuit(1)
flip.X_ERROR([0], 0.2)
flip.M(0)
recs = flip.compile_sampler().sample(50_000, seed=7)
print(round(float(recs.mean()), 4))
# -> 0.1987
```

:::

One channel, one path through the machine: AD's Kraus pair cannot run on a tableau, its signed three-branch menu can, the sampler draws one branch per location at $|q|/\gamma$ and books $\operatorname{sign}(q)\,\gamma$ into the shot's weight, and the weighted mean returns the channel's true expectations at a shot-count cost of $\gamma^{2L}$. Next, those weighted, decoded shots become the one number a code is judged by: the [logical error rate](./ler).
