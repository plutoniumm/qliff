---
title: The Coherent-Noise Engine
outline: 2
---

# The Coherent-Noise Engine <Badge type="info" text="Tutorial 05 of 7" />

> Rotations and damping are not Pauli errors: represent them as signed quasiprobabilities over Cliffords.

<script setup>
import BlochPlay from '../_tut/coherent/BlochPlay.svelte'
import AmpProb from '../_tut/coherent/AmpProb.svelte'
import RotWeights from '../_tut/coherent/RotWeights.svelte'
import GammaCurve from '../_tut/coherent/GammaCurve.svelte'
import Damping from '../_tut/coherent/Damping.svelte'
</script>

## Not all noise is a coin flip

The textbook picture of quantum noise is a coin flip: with some probability a qubit suffers a
random Pauli $X$, $Y$, or $Z$. That is the world a matching or belief-propagation decoder lives in:
independent, *stochastic*, Pauli errors.

Real hardware departs from this picture. Two failure modes do not fit it:

- **A miscalibrated gate** that *always* over- or under-rotates by a fixed angle: a **coherent**
  error $e^{-i\theta P/2}$. Nothing is random; the same small tilt happens every shot, and
  the tilts *add up*.
- **Energy leaking** to the environment: an excited $\ket 1$ decays toward $\ket 0$ with
  probability $p$. This is **amplitude damping**, and it is not symmetric: it has a preferred
  direction.

Neither is a random Pauli flip. A Clifford simulator like `qliff` can only apply Clifford gates to
stabilizer states, so at first glance it cannot represent these channels at all. The fix, and the
engine of this page, is to write each one as a **signed** mixture of Cliffords. Let us build
the intuition on the Bloch sphere first.

## A qubit on the Bloch sphere

A single qubit's pure state is a point on the unit sphere: $\ket 0$ at the north pole, $\ket 1$ at
the south, $\ket +$ and $\ket{+i}$ around the equator. Clifford gates are *discrete* quarter- and
half-turns of this sphere; a coherent rotation $R_Z(\theta)$ is a *continuous* turn about the
z-axis. Drag to orbit.

**Bloch playground**

<SvelteIsland :component="BlochPlay" />

*Click Cliffords to apply discrete moves; drag the $\theta$ slider to apply a continuous
$R_Z(\theta)$ on top. The faint grey arrow + cyan arc show where the state was before the live
rotation.*

*Legend: x axis ($\ket +$); y axis ($\ket{+i}$); z axis ($\ket 0 / \ket 1$); state vector
$\ket\psi$; ghost (pre-rotation); $R_Z(\theta)$ sweep arc.*

::: info Why the amplitude matters
After $R$ identical small rotations the net tilt is $R\theta$: it grows *linearly*. If you instead
modelled the same gate as a random Pauli flip, the errors would add in *probability* and grow far
slower. That mismatch is the central problem, and the next section makes it quantitative.
:::

## Coherent vs. incoherent: amplitude beats probability

Take an over-rotation by angle $\theta$ and ask: how big is the error? There are two natural ways to
measure "size", and they disagree.

- A **coherent** rotation tilts the state by an *amplitude* that grows like
  $\sin\theta \approx \theta$ for small $\theta$.
- The "equivalent" **Pauli (depolarizing) approximation** flips with a *probability* like
  $\sin^2(\theta/2) \approx \theta^2/4$, quadratically smaller for small angles.

**Amplitude vs. probability**

<SvelteIsland :component="AmpProb" />

*Coherent error amplitude (solid cyan) vs. the probability of the matched Pauli approximation
(dashed grey), as a function of the rotation angle $\theta$ (radians). Near $\theta=0$ the Pauli
model under-counts the error by a whole power of $\theta$.*

*Legend: coherent amplitude $\propto \theta$; Pauli prob. $\propto \theta^2$; $\theta$ marker
(slider).*

::: warning A Pauli approximation is systematically optimistic
Because coherent errors grow in amplitude ($\propto\theta$) while a same-strength Pauli error grows
in probability ($\propto\theta^2$), replacing a coherent channel by "the nearest Pauli channel"
systematically *under-counts* the damage, and the gap is worst where it matters: at small
per-gate angles that accumulate over thousands of rounds. A faithful simulator must keep the
coherence. That is what the quasiprobability construction provides.
:::

## The Clifford trick: a signed mix for RZ(θ)

The non-Clifford rotation $R_Z(\theta)=e^{-i\theta Z/2}$ is written by `qliff`
as a **signed quasiprobability mixture** over the four Cliffords *diagonal in Z*, namely the identity $I$,
the phase flip $Z$, and the $\pm 90^\circ$ phase gates $S$ and $S^\dagger$:

$$
R_Z(\theta)\;\approx\;\sum_k w_k\,C_k,\qquad C_k\in\{\,I,\;Z,\;S,\;S^\dagger\,\}.
$$

The $w_k$ are real but may be *negative*: this is a quasiprobability, not a probability. With
$c=\cos\theta$, $s=\sin\theta$ and the shared offset $\beta=\tfrac{1-c-s}{4}$, the four branch
weights are

$$
w_I=\beta+c,\quad w_Z=\beta,\quad w_S=\beta+s,\quad w_{S^\dagger}=\beta.
$$

They always sum to $4\beta + c + s = 1$ (the channel is trace-preserving), but *individual*
weights go negative as soon as $\theta$ is large enough. (The $R_X$ version is the same mixture
wrapped in $H$ on each side, since $R_X = H\,R_Z\,H$.)

**RZ(θ) branch weights**

<SvelteIsland :component="RotWeights" />

*Bars are the four signed weights $w_k$ for the Cliffords $\{I, Z, S, S^\dagger\}$; bar SIGN =
quasiprobability sign. Bars above the line are positive (sampled with prob $\propto |w|/\gamma$);
bars below are NEGATIVE (the sign problem) and carry a minus sign into the sampled trajectory's
importance weight.*

*Legend: positive weight $w_k > 0$; negative weight $w_k < 0$; rotated $\ket\psi$; ghost $\ket +$
($\theta=0$); sweep arc.*

::: details Decompose RZ(theta) at theta = pi/8 = 22.5 deg
1. Evaluate the trig at $\theta=\pi/8$: $c=\cos\theta\approx 0.9239$, $s=\sin\theta\approx 0.3827$.
2. Shared offset $\beta=\tfrac{1-c-s}{4}=\tfrac{1-0.9239-0.3827}{4}\approx -0.0766$, already
   negative.
3. Branch weights from $w_I=\beta+c,\;w_Z=\beta,\;w_S=\beta+s,\;w_{S^\dagger}=\beta$:
   $w_I\approx +0.847$, $w_Z\approx -0.077$, $w_S\approx +0.306$, $w_{S^\dagger}\approx -0.077$.
4. Trace check: the signed sum is one,
   $\textstyle\sum_k w_k = 0.847-0.077+0.306-0.077 = 1.000$.
5. Negativity: the absolute values sum to more,
   $\gamma=\textstyle\sum_k|w_k| = 0.847+0.077+0.306+0.077 \approx 1.307$.

**Result.** Two of the four weights ($w_Z,w_{S^\dagger}$) are negative, so no positive mixture
reproduces this rotation. The sampler pays $\gamma\approx \mathbf{1.31}$ per such location and a
variance factor of $\gamma^2\approx \mathbf{1.71}$, already at a modest 22.5 deg tilt.

`qliff`'s `Rotation` channel produces these branches:

```python
from math import pi

from qliff.noise import Rotation

for weight, ops in Rotation("Z", pi / 8).branches((0,)):
    label = ops[0][0] if len(ops) > 0 else "I"
    print(f"{label:>5s}  {weight:+.4f}")
# ->     I  +0.8472
# ->     Z  -0.0766
# ->     S  +0.3060
# -> S_DAG  -0.0766
```
:::

::: tip Positive mixture impossible, signed mixture exact
A probability mixture of Cliffords can only ever produce another Clifford (or a stochastic
Pauli) channel; it can never reproduce a rotation. Allowing **negative** weights breaks that
barrier: the signed combination reconstructs $R_Z(\theta)$ exactly. The price is the negativity,
which we name next.
:::

## Negativity γ: the cost of non-Cliffordness

The weights sum to $1$, but their *absolute* values sum to something larger. Define the
**negativity**

$$
\gamma \;=\; \sum_k |w_k| \;\ge\; 1,
$$

with equality exactly when every weight is non-negative (a true probability mixture). At $\theta=0$
the rotation is the identity, all weight sits on $I$, and $\gamma=1$: the location costs nothing.
As $\theta$ grows, weights dip negative and $\gamma$ climbs.

**Negativity γ(θ)**

<SvelteIsland :component="GammaCurve" />

*Negativity $\gamma$ (unitless) vs. rotation angle $\theta$ (radians) for the RZ decomposition.
$\gamma=1$ at $\theta=0$, and rises as branch weights go negative. The sampler later draws a branch
with probability $|w|/\gamma$ and carries a signed importance weight of magnitude $\gamma$, so
larger $\gamma$ means more sampling variance downstream.*

*Legend: $\gamma(\theta) = \sum|w_k|$; $\theta$ marker (slider).*

::: info γ is the overhead, not the error
Negativity does not make the simulation *wrong*: the answer it converges to is exact. It makes it
*expensive*: each non-Pauli location multiplies the variance of a sampled estimate by roughly
$\gamma^2$, so you need more shots for the same error bar. $\gamma$ is the bookkeeping of how
non-Clifford the channel is. The [noise-sampling](./noise) page shows how that importance weight is
carried.
:::

## Amplitude damping: a one-way pull to |0⟩

Energy loss is different from a rotation: it is irreversible and it has a direction. Amplitude
damping with loss probability $p$ is decomposed exactly over only three Cliffords (the identity, a
phase flip $Z$, and a **reset** $R$ to $\ket 0$):

$$
q_I=\tfrac{(1-p)+\sqrt{1-p}}{2},\quad q_Z=\tfrac{(1-p)-\sqrt{1-p}}{2},\quad q_R=p.
$$

The middle weight $q_Z$ is negative for every $0<p<1$, so damping is intrinsically non-Pauli, like
the rotation. The overhead is $\gamma = \sqrt{1-p} + p$: small at first
($\gamma \approx 1 + \tfrac{p}{2}$ for small $p$), it peaks at $\gamma = 1.25$ near $p = \tfrac34$,
then eases back to $1$ as $p \to 1$ (a full reset is the Clifford $R$ alone, with no negativity). On
the sphere, damping does not rotate the state; it *shrinks* the equatorial component and *pulls* the
vector toward the north pole $\ket 0$.

**Damping branch weights**

<SvelteIsland :component="Damping" />

*Bars are the three signed weights for the Cliffords {I, Z, R}; bar SIGN = quasiprobability sign.
Amplitude damping pulls the Bloch vector toward |0> (the arrow shortens and tilts up, a mixed state).
The weights q_I, q_Z, q_R include the negative q_Z; gamma = sum|q_k| is the (small) sampling
overhead.*

*Legend: positive weight; negative $q_Z$; damped $\ket\psi$ (shrinks toward $\ket 0$); z axis
($\ket 0$ pole).*

*Damping negativity gamma(p): negativity gamma (unitless) vs. loss probability p (unitless). The
exact gamma(p) = sqrt(1-p) + p (accent) matches the 1 + p/2 small-p estimate (dashed) near p = 0,
then turns over: it peaks at gamma = 1.25 around p = 3/4 and falls back to 1 at p = 1.*

## Why QEC must take this seriously

Coherent errors compound. Because each round adds the same tilt in amplitude, the contributions
can align across many rounds and across many qubits, producing a logical failure rate well above
what the matched depolarizing model predicts. A simulator that Pauli-approximates its noise will
report a threshold that is too optimistic.

`qliff` carries the exact channels, coherent $R_Z/R_X$ rotations and amplitude damping, as the
signed quasiprobability mixtures you just built, and pays the negativity $\gamma$ in full. Two
pieces downstream make that practical:

- The [trajectory sampler](./noise) draws one branch per location with probability $|w|/\gamma$ and
  threads a **signed importance weight** of magnitude $\gamma$ through the shot, so a stochastic
  Clifford simulator reproduces a non-Pauli channel in expectation.
- A dedicated [`coherent` tensor-network decoder](./tn) contracts the circuit's *signed* branch
  weights directly. A detector-error-model decoder (MWPM, BP+OSD) can only encode independent Pauli
  noise; it has no slot for a negative weight, so it cannot represent these channels. The
  coherent decoder can.

## Implementation {#implementation}

The tabs below make the pipeline concrete: the sampling recipe in pseudocode, an explicit
linear-algebra reconstruction in NumPy, and the same physics through `qliff`'s own channel,
estimator, and decoder.

**Pseudocode.** One noise location is handled in two phases: a one-time decomposition of
$R_Z(\theta)$ into signed weights over $\{I, Z, S, S^\dagger\}$, then a per-shot
sample-and-reweight loop. The signed average is unbiased; its variance grows with the negativity
$\gamma$.

**Std Python.** In the Pauli-transfer-matrix (PTM) basis a single-qubit channel is a real
$4\times 4$ matrix, so $\sum_k w_k\,C_k = R_Z(\theta)$ is a linear system for the weights. The four
Clifford PTMs only span three independent directions, so the symmetry constraint
$w_Z = w_{S^\dagger}$ (the choice the closed form makes) pins the unique solution; a seeded Monte
Carlo then shows the signed estimator converging to the exact $\langle X\rangle$ at a variance
cost.

**Qliff.** The same weights come out of `qliff.noise.Rotation`, and `Circuit.estimate` runs the
signed importance estimator end to end. The circuit-level `coherent` decoder then consumes those
signed branch weights directly, on a circuit no detector-error-model decoder can represent.

::: code-group

```text [Pseudocode]
decompose RZ(theta) over the Cliffords diagonal in Z:
    c = cos(theta);  s = sin(theta);  beta = (1 - c - s) / 4
    w[I] = beta + c;  w[Z] = beta;  w[S] = beta + s;  w[S_dag] = beta
    # signed weights, sum(w) = 1
gamma = sum over k of |w[k]|       # negativity >= 1; == 1 iff all w[k] >= 0

estimate <O> with N shots:
    total = 0
    repeat N times:
        draw branch k with probability |w[k]| / gamma
        apply Clifford C_k in the stabilizer simulator
        total += sign(w[k]) * gamma * <O after C_k>
    return total / N
    # unbiased for any theta; per-shot values reach +/- gamma,
    # so the variance grows like gamma^2 once weights go negative
```

```python [Std Python]
import numpy as np

# Pauli transfer matrix of a 1-qubit unitary U: R[i, j] = tr(P_i U P_j U^dag) / 2.
# A channel is a 4x4 real matrix in this basis, so "sum_k w_k C_k = RZ(theta)"
# becomes an ordinary linear system for the weights w_k.
PAULIS = [
    np.eye(2, dtype=complex),
    np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex),
    np.array([[0.0, -1.0j], [1.0j, 0.0]], dtype=complex),
    np.array([[1.0, 0.0], [0.0, -1.0]], dtype=complex),
]


def ptm(u):
    r = np.zeros((4, 4))
    for i in range(4):
        for j in range(4):
            val = np.trace(PAULIS[i] @ u @ PAULIS[j] @ u.conj().T)
            r[i, j] = np.real(val) / 2.0

    return r


theta = np.pi / 8
rz = np.diag([np.exp(-0.5j * theta), np.exp(0.5j * theta)])

# the four Cliffords diagonal in Z: {I, Z, S, S_dag}
basis = [
    ("I", PAULIS[0]),
    ("Z", PAULIS[3]),
    ("S", np.diag([1.0, 1.0j])),
    ("S_DAG", np.diag([1.0, -1.0j])),
]

# 16 stacked PTM equations in 4 unknowns. The four PTMs are linearly dependent
# (rank 3), so the decomposition has one free parameter; append the symmetric
# constraint w_Z = w_S_DAG that the closed form uses, which makes it unique.
a = np.stack([ptm(u).ravel() for _name, u in basis], axis=1)
b = ptm(rz).ravel()
a = np.vstack([a, [0.0, 1.0, 0.0, -1.0]])
b = np.append(b, 0.0)
weights, _res, _rank, _sv = np.linalg.lstsq(a, b, rcond=None)

for (name, _u), w in zip(basis, weights):
    print(f"w_{name:<5s} = {w:+.4f}")
# -> w_I     = +0.8472
# -> w_Z     = -0.0766
# -> w_S     = +0.3060
# -> w_S_DAG = -0.0766

# the solve lands on the closed form beta = (1 - cos - sin) / 4
c, s = np.cos(theta), np.sin(theta)
beta = (1.0 - c - s) / 4.0
closed = np.array([beta + c, beta, beta + s, beta])
print("matches closed form:", bool(np.allclose(weights, closed)))
# -> matches closed form: True
print(f"reconstruction error: {np.max(np.abs(a[:16] @ weights - b[:16])):.1e}")
# -> reconstruction error: 1.1e-16

gamma = float(np.sum(np.abs(weights)))
print(f"sum w = {weights.sum():+.4f}   gamma = {gamma:.4f}")
# -> sum w = +1.0000   gamma = 1.3066

# signed Monte Carlo: <X> on |+> after RZ(theta); the exact value is cos(theta).
# Draw branch k with probability |w_k| / gamma, evaluate <X> on C_k |+>, and
# average sign(w_k) * gamma * outcome.
rng = np.random.default_rng(7)
plus = np.array([1.0, 1.0], dtype=complex) / np.sqrt(2.0)
x_op = PAULIS[1]

outcomes = np.zeros(4)
for k, (_name, u) in enumerate(basis):
    psi = u @ plus
    outcomes[k] = np.real(psi.conj() @ x_op @ psi)

probs = np.abs(weights) / gamma
signs = np.sign(weights)
shots = 200000
draws = rng.choice(4, size=shots, p=probs)
values = signs[draws] * gamma * outcomes[draws]

print(f"exact <X>  = {np.cos(theta):.4f}")
print(f"signed MC  = {values.mean():.4f}")
# -> exact <X>  = 0.9239
# -> signed MC  = 0.9228
print(f"std/shot   = {values.std():.4f}  (direct measurement: {np.sin(theta):.4f})")
# -> std/shot   = 0.5951  (direct measurement: 0.3827)
print(f"E[v^2] = {np.mean(values ** 2):.4f} <= gamma^2 = {gamma ** 2:.4f}")
# -> E[v^2] = 1.2057 <= gamma^2 = 1.7071
```

```python [Qliff]
import numpy as np

from qliff import Circuit
from qliff.noise import Rotation
from qliff.qec.decoder import make_circuit_decoder

theta = np.pi / 8

# the engine's own branches: (weight, ops) pairs, identity branch first
branches = Rotation("Z", theta).branches((0,))
for weight, ops in branches:
    label = ops[0][0] if len(ops) > 0 else "I"
    print(f"{label:>5s}  w = {weight:+.4f}")
# ->     I  w = +0.8472
# ->     Z  w = -0.0766
# ->     S  w = +0.3060
# -> S_DAG  w = -0.0766

gamma = sum(abs(w) for w, _ops in branches)
print(f"gamma = {gamma:.4f}")
# -> gamma = 1.3066

# <X> on |+> after a coherent RZ(theta): the signed importance estimator
circuit = Circuit(1)
circuit.H(0)
circuit.RZ(0, theta)
print(f"estimate = {circuit.estimate('X', shots=20000, seed=1):.4f}")
print(f"exact    = {np.cos(theta):.4f}")
# -> estimate = 0.9247
# -> exact    = 0.9239


def rep_memory(distance: int, tilt: float) -> Circuit:
    # one-round bit-flip repetition memory whose data noise is a coherent RX
    # tilt: a non-Pauli circuit no detector-error-model decoder can represent
    c = Circuit()
    data = list(range(distance))
    anc = list(range(distance, 2 * distance - 1))
    checks = distance - 1

    for q in data:
        c.RX(q, tilt)
    for i in range(checks):
        c.append("CX", [data[i], anc[i]])
        c.append("CX", [data[i + 1], anc[i]])
    for i in range(checks):
        c.append("MR", [anc[i]])
        c.detector(-1)
    for q in data:
        c.append("M", [q])
    for i in range(checks):
        c.detector(-distance + i, -distance + i + 1, -distance - checks + i)
    c.observable(0, *[-distance + i for i in range(distance)])

    return c


# the coherent decoder consumes the circuit directly and contracts its SIGNED
# branch weights per logical class ("tn"/"mld" route here too on non-Pauli noise)
circuit = rep_memory(3, 0.45)
decoder = make_circuit_decoder("coherent", circuit)

syndromes = np.array(
    [
        [0, 0, 0, 0],  # quiet: no detector fired
        [1, 0, 0, 0],  # an X flip on the end data qubit
        [1, 1, 0, 0],  # an X flip on the middle data qubit
    ],
    dtype=np.uint8,
)
print("logical flips:", decoder.decode_batch(syndromes).ravel().tolist())
# -> logical flips: [0, 1, 1]
```

:::

::: tip Recap
Non-Pauli noise (coherent rotations and amplitude damping) cannot be a *positive* mixture of
Cliffords, but it *can* be a **signed** one. The weights still sum to 1, yet $\sum|w|=\gamma\ge 1$
measures the non-Cliffordness. Coherent errors accumulate in amplitude ($\propto\theta$), beating a
same-size Pauli flip ($\propto\theta^2$), so a QEC simulator must model them exactly rather than
flattening them into coin flips.
:::
