---
title: The Coherent-Noise Engine
outline: 2
---

# The Coherent-Noise Engine <Badge type="info" text="Tutorial 05 of 7" />

> Rotations and damping aren't Pauli errors -- represent them as signed quasiprobabilities over Cliffords.

<script setup>
import BlochPlay from '../_tut/coherent/BlochPlay.svelte'
import AmpProb from '../_tut/coherent/AmpProb.svelte'
import RotWeights from '../_tut/coherent/RotWeights.svelte'
import GammaCurve from '../_tut/coherent/GammaCurve.svelte'
import Damping from '../_tut/coherent/Damping.svelte'
</script>

## Not all noise is a coin flip

The textbook picture of quantum noise is a coin flip: with some probability a qubit suffers a
random Pauli $X$, $Y$, or $Z$. That is the world a matching or belief-propagation decoder lives in
-- independent, *stochastic*, Pauli errors.

Real hardware is sneakier. Two failure modes refuse to be a coin flip:

- **A miscalibrated gate** that *always* over- or under-rotates by a fixed angle -- a **coherent**
  error $e^{-i\theta P/2}$. Nothing is random; the same small tilt happens every single shot, and
  the tilts *add up*.
- **Energy quietly leaking** to the environment -- an excited $\ket 1$ decays toward $\ket 0$ with
  probability $p$. This is **amplitude damping**, and it is not symmetric: it has a preferred
  direction.

Neither is a random Pauli flip. A Clifford simulator like `qliff` can only apply Clifford gates to
stabilizer states, so at first glance it has no way to represent these channels at all. The trick --
the engine of this page -- is to write each one as a **signed** mixture of Cliffords. Let us build
the intuition on the Bloch sphere first.

## A qubit on the Bloch sphere

A single qubit's pure state is a point on the unit sphere: $\ket 0$ at the north pole, $\ket 1$ at
the south, $\ket +$ and friends around the equator. Clifford gates are *discrete* quarter- and
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
After $R$ identical small rotations the net tilt is $R\theta$ -- it grows *linearly*. If you instead
modelled the same gate as a random Pauli flip, the errors would add in *probability* and grow far
slower. That mismatch is the whole problem, and the next section makes it quantitative.
:::

## Coherent vs. incoherent: amplitude beats probability

Take an over-rotation by angle $\theta$ and ask: how big is the error? There are two honest ways to
measure "size", and they disagree.

- A **coherent** rotation tilts the state by an *amplitude* that grows like
  $\sin\theta \approx \theta$ for small $\theta$.
- The "equivalent" **Pauli (depolarizing) approximation** flips with a *probability* like
  $\sin^2(\theta/2) \approx \theta^2/4$ -- quadratically smaller for small angles.

**Amplitude vs. probability**

<SvelteIsland :component="AmpProb" />

*Coherent error amplitude (solid cyan) vs. the probability of the matched Pauli approximation
(dashed grey), as a function of the rotation angle $\theta$ (radians). Near $\theta=0$ the Pauli
model under-counts the error by a whole power of $\theta$.*

*Legend: coherent amplitude $\propto \theta$; Pauli prob. $\propto \theta^2$; $\theta$ marker
(slider).*

::: warning A Pauli approximation is dishonest
Because coherent errors grow in amplitude ($\propto\theta$) while a same-strength Pauli error grows
in probability ($\propto\theta^2$), replacing a coherent channel by "the nearest Pauli channel"
systematically *under-counts* the damage -- and the gap is worst exactly where you care, at small
per-gate angles that pile up over thousands of rounds. An honest simulator must keep the coherence.
That is what the quasiprobability trick buys us.
:::

## The Clifford trick: a signed mix for RZ(θ)

Here is the key move. The non-Clifford rotation $R_Z(\theta)=e^{-i\theta Z/2}$ is written by `qliff`
as a **signed quasiprobability mixture** over the four Cliffords *diagonal in Z* -- the identity $I$,
the phase flip $Z$, and the $\pm 90^\circ$ phase gates $S$ and $S^\dagger$:

$$
R_Z(\theta)\;\approx\;\sum_k w_k\,C_k,\qquad C_k\in\{\,I,\;Z,\;S,\;S^\dagger\,\}.
$$

The $w_k$ are real but may be *negative*: this is a quasiprobability, not a probability. With
$c=\cos\theta$, $s=\sin\theta$ and the shared offset $\beta=\tfrac{1-c-s}{4}$, the four branch
weights are exactly

$$
w_I=\beta+c,\quad w_Z=\beta,\quad w_S=\beta+s,\quad w_{S^\dagger}=\beta.
$$

They always sum to $4\beta + c + s = 1$ -- the channel is trace-preserving -- but *individual*
weights go negative as soon as $\theta$ is large enough. (The $R_X$ version is the same mixture
wrapped in $H$ on each side, since $R_X = H\,R_Z\,H$.)

**RZ(θ) branch weights**

<SvelteIsland :component="RotWeights" />

*Bars are the four signed weights $w_k$ for the Cliffords $\{I, Z, S, S^\dagger\}$; bar SIGN =
quasiprobability sign. Bars above the line are positive (sampled with prob $\propto |w|/\gamma$);
bars below are NEGATIVE -- the sign problem -- and carry a minus sign into the sampled trajectory's
importance weight.*

*Legend: positive weight $w_k > 0$; negative weight $w_k < 0$; rotated $\ket\psi$; ghost $\ket +$
($\theta=0$); sweep arc.*

::: details Decompose RZ(theta) at theta = pi/8 = 22.5 deg
1. Evaluate the trig at $\theta=\pi/8$: $c=\cos\theta\approx 0.9239$, $s=\sin\theta\approx 0.3827$.
2. Shared offset $\beta=\tfrac{1-c-s}{4}=\tfrac{1-0.9239-0.3827}{4}\approx -0.0766$ -- already
   negative.
3. Branch weights from $w_I=\beta+c,\;w_Z=\beta,\;w_S=\beta+s,\;w_{S^\dagger}=\beta$:
   $w_I\approx +0.847$, $w_Z\approx -0.077$, $w_S\approx +0.306$, $w_{S^\dagger}\approx -0.077$.
4. Trace check -- the signed sum is exactly one:
   $\textstyle\sum_k w_k = 0.847-0.077+0.306-0.077 = 1.000$.
5. Negativity -- the absolute values sum to more:
   $\gamma=\textstyle\sum_k|w_k| = 0.847+0.077+0.306+0.077 \approx 1.307$.

**Result.** Two of the four weights ($w_Z,w_{S^\dagger}$) are negative, so this is genuinely
coherent. The sampler pays $\gamma\approx \mathbf{1.31}$ per such location and a variance blow-up of
$\gamma^2\approx \mathbf{1.71}$ -- already at a modest 22.5 deg tilt.
:::

::: tip Positive mixture impossible, signed mixture fine
A genuine probability mixture of Cliffords can only ever produce another Clifford (or a stochastic
Pauli) channel -- it can never reproduce a true rotation. Allowing **negative** weights breaks that
barrier: the signed combination reconstructs $R_Z(\theta)$ exactly. The price is the negativity,
which we name next.
:::

## Negativity γ -- the cost of non-Cliffordness

The weights sum to $1$, but their *absolute* values sum to something larger. Define the
**negativity**

$$
\gamma \;=\; \sum_k |w_k| \;\ge\; 1,
$$

with equality exactly when every weight is non-negative (a true probability mixture). At $\theta=0$
the rotation is the identity, all weight sits on $I$, and $\gamma=1$ -- free. As $\theta$ grows,
weights dip negative and $\gamma$ climbs.

**Negativity γ(θ)**

<SvelteIsland :component="GammaCurve" />

*Negativity $\gamma$ (unitless) vs. rotation angle $\theta$ (radians) for the RZ decomposition.
$\gamma=1$ at $\theta=0$, and rises as branch weights go negative. The sampler later draws a branch
with probability $|w|/\gamma$ and carries a signed importance weight of magnitude $\gamma$ -- so
larger $\gamma$ means more sampling variance downstream.*

*Legend: $\gamma(\theta) = \sum|w_k|$; $\theta$ marker (slider).*

::: info γ is the overhead, not the error
Negativity does not make the simulation *wrong* -- the answer it converges to is exact. It makes it
*expensive*: each non-Pauli location multiplies the variance of a sampled estimate by roughly
$\gamma^2$, so you need more shots for the same error bar. $\gamma$ is the honest bookkeeping of "how
non-Clifford is this channel". The [noise-sampling](./noise) page shows how that importance weight is
actually carried.
:::

## Amplitude damping: a one-way pull to |0⟩

Energy loss is different from a rotation: it is irreversible and it has a direction. Amplitude
damping with loss probability $p$ is decomposed exactly over just three Cliffords -- the identity, a
phase flip $Z$, and a **reset** $R$ to $\ket 0$:

$$
q_I=\tfrac{(1-p)+\sqrt{1-p}}{2},\quad q_Z=\tfrac{(1-p)-\sqrt{1-p}}{2},\quad q_R=p.
$$

The middle weight $q_Z$ is negative for every $0<p<1$, so damping is intrinsically non-Pauli, just
like the rotation. The overhead is $\gamma = \sqrt{1-p} + p$: small at first
($\gamma \approx 1 + \tfrac{p}{2}$ for small $p$), it peaks at $\gamma = 1.25$ near $p = \tfrac34$,
then eases back to $1$ as $p \to 1$ (a full reset is just the Clifford $R$, no negativity). On the
sphere, damping does not rotate the state; it *shrinks* the equatorial component and *pulls* the
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

Coherent errors do not just sit there -- they *conspire*. Because each round adds the same tilt in
amplitude, the contributions can align across many rounds and across many qubits, producing a logical
failure rate well above what the matched depolarizing model predicts. A simulator that quietly
Pauli-approximates its noise will report a threshold that is too optimistic.

`qliff` refuses to cheat. It carries the real channels -- coherent $R_Z/R_X$ rotations and amplitude
damping -- as the signed quasiprobability mixtures you just built, and pays the negativity $\gamma$
honestly. Two pieces downstream make that practical:

- The [trajectory sampler](./noise) draws one branch per location with probability $|w|/\gamma$ and
  threads a **signed importance weight** of magnitude $\gamma$ through the shot -- so a stochastic
  Clifford simulator reproduces a non-Pauli channel in expectation.
- A dedicated [`coherent` tensor-network decoder](./tn) contracts the circuit's *signed* branch
  weights directly. A detector-error-model decoder (MWPM, BP+OSD) can only encode independent Pauli
  noise; it has no slot for a negative weight, so it literally cannot represent these channels. The
  coherent decoder can.

::: tip Recap
Non-Pauli noise -- coherent rotations and amplitude damping -- cannot be a *positive* mixture of
Cliffords, but it *can* be a **signed** one. The weights still sum to 1, yet $\sum|w|=\gamma\ge 1$
measures the non-Cliffordness. Coherent errors accumulate in amplitude ($\propto\theta$), beating a
same-size Pauli flip ($\propto\theta^2$), so an honest QEC simulator models them exactly rather than
flattening them into coin flips.
:::
