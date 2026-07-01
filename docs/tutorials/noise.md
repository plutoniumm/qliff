---
title: Simulating Noise
outline: 2
---

# Simulating Noise <Badge type="info" text="Tutorial 06 of 7" />

> How one stabilizer trajectory is drawn, and why importance weights make non-Pauli noise honest.

<script setup>
import Trajectory from '../_tut/noise/Trajectory.svelte'
</script>

## Why you can't just store the state

A quantum computer with $n$ qubits lives in a space of $2^n$ complex amplitudes. To simulate it the brute-force way you write down all of them -- a *state vector*. That is fine for a toy, and catastrophic for a code: a few thousand qubits would need more numbers than there are atoms in the universe.

**Memory blow-up**

Legend:
- state vector -- $2^n$ amplitudes
- stabilizer tableau -- $\sim n^2$ bits

*State-vector amplitudes ($2^n$) versus a stabilizer tableau ($\sim n^2$ bits). Drag the qubit count.*

The escape hatch is the **Gottesman-Knill theorem**: a circuit built only from *Clifford* gates, acting on a *stabilizer* state, can be simulated in polynomial memory and time -- you track an $\sim n^2$ bit tableau instead of $2^n$ numbers. qliff's Rust core stores that tableau column-major so each shot is fast, and shots are embarrassingly parallel.

::: tip The constraint this puts on noise
Everything the simulator does -- including the noise -- must be expressible as **Clifford pieces**. The rest of this page is about how arbitrary physical noise gets squeezed into that mould, one Clifford branch at a time. That is exactly why qliff can run QEC at a scale a state-vector simulator simply cannot reach.
:::

## A channel is a menu of branches

A noise **channel** is just a menu. Each line on the menu is a **branch**: a weight and a little list of Clifford gates to apply. The first line is always the *no-fault* branch (do nothing). Per noise location, per shot, the simulator picks **exactly one** line and applies it. That single choice is what makes a trajectory.

Written out, a channel $\mathcal{E}$ applies branch $k$ -- a Clifford/Pauli operator $C_k$ -- to the state $\rho$ with weight $w_k$:

$$
\mathcal{E}(\rho)\;=\;\sum_k w_k\, C_k\,\rho\, C_k^{\dagger},\qquad \sum_k w_k = 1,\qquad C_0 = I\ (\text{no fault, first}).
$$

Here $w_k$ is the weight of branch $k$, $C_k$ its Clifford gate(s), and the total weight is always $1$ (the channel preserves probability). For a *Pauli* channel every $w_k \ge 0$, so the weights are a genuine probability distribution and you can sample straight from them.

The simplest example is single-qubit depolarizing noise, `DEPOLARIZE1(p)`: with probability $1-p$ nothing happens, and otherwise an $X$, $Y$, or $Z$ fires, each with probability $p/3$. So $w_0 = 1-p$ on $C_0 = I$ and $w_X = w_Y = w_Z = p/3$.

**DEPOLARIZE1 menu**

Legend:
- I -- no-fault branch ($w_0 = 1-p$)
- X branch ($p/3$)
- Y branch ($p/3$)
- Z branch ($p/3$)

*DEPOLARIZE1(p) as a labelled menu. Each bar's length is its weight $w_k$; they sum to 1.*

The weights are a genuine probability distribution: non-negative and summing to one. We'll see in a moment that *not all* physical noise is so polite -- but Pauli channels like this one are, and they cover the bulk of QEC benchmarking.

## One noisy shot

Now put several noise locations in a row -- one after each qubit of a tiny 4-qubit line -- and run a single shot. Pick a **seed** and step through the locations. At each one the simulator rolls a die and reads the menu: it draws a threshold uniformly on $[0,\gamma)$ and walks the branches, accumulating $|w|$, until it passes the threshold. For a Pauli channel $\gamma=1$, so this is just "spin the wheel".

::: info The exact rule (qliff's Channel.sample)

$$
\gamma=\textstyle\sum_k |w_k|,\qquad u\sim\mathcal{U}[0,1),\qquad t = u\,\gamma,\qquad \text{pick the first } k \text{ with } \sum_{j\le k}|w_j|\ge t.
$$

Here $u$ is the uniform draw `rng()`, $t$ the threshold on $[0,\gamma)$, and we walk the cumulative $\sum_{j\le k}|w_j|$ until it covers $t$. The location then carries the factor $\operatorname{sign}(w_k)\,\gamma$ (here always $1$, since $\gamma=1$ for a Pauli channel) and applies that branch's Clifford ops.
:::

**One seeded trajectory**

<SvelteIsland :component="Trajectory" />

Legend:
- location not yet revealed (?)
- fired I -- no fault
- fired X
- fired Y
- fired Z
- dice marker $t = u\cdot\gamma$
- current location

*A single seeded stabilizer trajectory. The bar shows the $\gamma$-scaled $|w_k|$ segments; the marker is the draw $t = u\cdot\gamma$. Same seed $\Rightarrow$ same shot, every time.*

Reset the seed and replay: you get the identical sequence of dice rolls and fired branches. That reproducibility is what lets a researcher pin down, rerun, and debug a single rare failure out of billions of shots.

## The menus, and the law of large numbers

Every Pauli instruction qliff understands is one of these menus:

| instruction | branches | weight each |
| --- | --- | --- |
| `DEPOLARIZE1(p)` | I, X, Y, Z | $1-p$ then $p/3$ |
| `DEPOLARIZE2(p)` | II + the 15 two-qubit pairs | $1-p$ then $p/15$ |
| `X_ERROR(p)` | I, X | $1-p,\; p$ |
| `Z_ERROR(p)` | I, Z | $1-p,\; p$ |

Sampling is honest only in aggregate: any single shot is random, but as you draw more shots the empirical fraction of times each branch fires converges to its weight. Crank $N$ and watch the bars settle.

**Law of large numbers**

Legend:
- theory weight $|w_k|$ (outline)
- empirical fraction (N shots)

*Per branch: theory weight $|w_k|$ (dashed outline) vs. empirical fraction of N seeded shots that fired it. x-axis = probability (fraction of shots, 0-1). More shots $\Rightarrow$ tighter match.*

::: info DEPOLARIZE2
Two-qubit depolarizing has **16** branches: identity plus the 15 non-identity Pauli pairs (XI, IX, XX, XY, ..., ZZ), each at $p/15$. They're grouped above for readability.
:::

## From trajectory to syndrome

A trajectory changes some qubits; the decoder never sees those errors directly. It sees **detection events**. The definition is blunt: run the circuit once with *no* noise to get a reference parity for every detector, then for a noisy shot,

$$
\text{detection event}_d \;=\; (\text{measured parity of detector } d)\;\oplus\;(\text{reference parity}_d).
$$

A detector fires precisely when noise flipped its deterministic value. That bit-string is the **syndrome** -- the only thing the decoder eats. Click data qubits to inject $X$ errors and watch the Z-checks between neighbours light up.

**Trajectory -> syndrome**

Legend:
- data qubit with X error
- clean data qubit
- Z-check lit (detection event = 1)
- Z-check quiet (0)

*A repetition-code round. Click a data qubit to flip it; a Z-check fires (lit) iff its two neighbours disagree.*

Notice an isolated error lights the *two* checks straddling it; a pair of adjacent errors only lights the checks at its ends. That structure is exactly what the matching, belief-propagation, and tensor-network decoders exploit. This panel is, quite literally, their input.

## The sign problem, and importance sampling

Real noise isn't always a tidy probability menu. A coherent **rotation** or **amplitude damping** is non-Pauli, and the only way to write it over Cliffords is with a **quasiprobability**: some weights go *negative*. You cannot sample from a probability that is below zero.

**Quasiprobability branches**

Legend:
- positive weight $w_k \ge 0$ (above axis)
- negative weight $w_k < 0$ (below axis)
- zero axis

*Quasiprobability branches. Bar height = $|w_k|$; negative weights (below the axis) are the hallmark of non-Pauli noise.*

The fix is **importance sampling**. Draw a branch with probability $|w_k|/\gamma$, and carry a signed **importance weight** $\operatorname{sign}(w_k)\,\gamma$ with the shot. Any statistic $f$ is then estimated by the *weighted* mean over $N$ shots:

$$
\hat{f} = \frac{1}{N}\sum_{s=1}^{N}\operatorname{sign}(w_{k_s})\,\gamma\; f(C_{k_s}),\qquad \mathbb{E}[\hat{f}] = \sum_k w_k\, f(C_k).
$$

Because we sample branch $k$ with probability $|w_k|/\gamma$ and multiply by $\operatorname{sign}(w_k)\,\gamma$, the $\gamma$ cancels and the $\operatorname{sign}$ restores the negative weights -- so $\mathbb{E}[\hat{f}]$ is exactly the true quasiprobability average $\sum_k w_k f(C_k)$. It is **unbiased**, the only honest way to put coherent or damping noise on a Clifford simulator.

Contrast the two regimes. **Naive Pauli sampling** has every $w_k \ge 0$, so $\gamma = \sum_k|w_k| = \sum_k w_k = 1$: each shot carries weight $1$ and you just count. **Weighted sampling** has $\gamma > 1$: each shot carries $\pm\gamma$, so the variance of $\hat f$ picks up a factor of order $\gamma^2$ per location (and the $\gamma$ multiply across locations). To match a target error bar you need on the order of $\gamma^2$ times as many shots -- that inflation is the entire cost of non-Cliffordness.

::: details Sampling RZ(theta = 0.6): one shot at u = 0.62

1. Build the menu. With $b_d=(1-\cos\theta-\sin\theta)/4$ at $\theta=0.6$ ($\cos=0.8253,\ \sin=0.5646,\ b_d=-0.0975$), the $\{I,Z,S,S^\dagger\}$ weights are $w_I=b_d+\cos=0.7278$, $w_Z=b_d=-0.0975$, $w_S=b_d+\sin=0.4671$, $w_{S^\dagger}=b_d=-0.0975$.
2. Negativity $\gamma=\sum_k|w_k|=0.7278+0.0975+0.4671+0.0975=1.3900$ ($>1$, so this is genuinely non-Pauli).
3. Roll the die: threshold $t=u\,\gamma=0.62\times 1.3900=0.8618$.
4. Walk the cumulative $|w_k|$: $I\!:0.7278$ ($<t$), ${+}Z\!:0.8253$ ($<t$), ${+}S\!:1.2925$ -- first sum $\ge t$, so branch $S$ fires.
5. Its weight $w_S=0.4671>0$, so the shot carries factor $\operatorname{sign}(w_S)\,\gamma=+1.3900$.

**Result:** This shot applies **S** and carries importance weight **+1.390**. Had the draw landed in $Z$'s slot (e.g. $u=0.58$, $t=0.806$, inside $(0.7278,\,0.8253]$), the same machinery would apply **Z** and carry **-1.390** -- the negative sign that keeps the estimate unbiased.

:::

**Weighted vs. naive estimate**

Legend:
- truth $\sum w_k \cdot \text{indicator}$
- weighted estimate ($\pm 2\sigma$ band)
- naive estimate (biased)

*Estimating P(a Z error fires) two ways, on a number line of the estimated value. The weighted estimate (with its $\pm 2\sigma$ band) hugs the truth; the naive one (ignoring $\operatorname{sign}\cdot\gamma$) is biased.*

::: warning The catch: variance grows with gamma^2
Importance sampling is unbiased but not free. Each shot's weight has magnitude $\gamma$, so the estimator's variance scales with $\gamma^2$ (and compounds multiplicatively across locations). The further your noise is from Clifford, the bigger $\gamma$, and the more shots you need. Push $\theta$ or $p$ up and the error bar visibly widens.
:::

## Why it all scales

Step back and count the cost of one shot. At every noise location the simulator picks **one** Clifford branch and applies it to the stabilizer tableau. No branch ever forks the simulation; no $2^n$ state-vector is ever formed. So a shot costs a polynomial number of tableau updates, and the millions of shots you need are independent -- perfectly parallel across cores and machines.

::: tip The whole engine in one breath
A channel is a menu of **(weight, Clifford ops)** branches; per location per shot you draw **one** via $\gamma$ and a uniform threshold; a trajectory is the running tableau plus a signed importance weight; a detector fires when the shot's parity disagrees with the noiseless reference. Pauli noise samples directly; non-Pauli noise rides the weighted mean. Stabilizer formalism + one branch per location = polynomial per shot, trivially parallel across shots. That is qliff's reason for existing.
:::

From here, those sampled-and-decoded shots become a number. Feed the detection events to a decoder (matching, BP, or tensor networks), compare its correction against the true observable flip, and the fraction it gets wrong -- weighted, if the noise was non-Pauli -- is the **logical error rate**. That's the next, and final, step.
