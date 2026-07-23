---
title: Stratified Self-Normalised Sampling
outline: 2
---

# Stratified Self-Normalised Sampling <Badge type="info" text="Tutorial 07 of 10" />

<script setup>
import GammaWall from '../_tut/stratified/GammaWall.svelte'
import MassBars from '../_tut/stratified/MassBars.svelte'
import SignTally from '../_tut/stratified/SignTally.svelte'
</script>

## The running example: a 3x3 damping patch

[Tutorial 06](./noise) built a sampler for non-Pauli noise. It runs a channel a stabilizer simulator cannot represent, like amplitude damping, by rewriting it as a signed sum of branches the simulator can run. For `AMPLITUDE_DAMP(0.05)` those branches are $I, Z$, and $R$, with weights

$$
q_I = 0.962340, \qquad q_Z = -0.012340, \qquad q_R = 0.050000 .
$$

To take one shot, the location draws a branch with probability $|q_k|/\gamma$ and multiplies the shot's running weight by $\operatorname{sign}(q_k)\,\gamma$, where

$$
\gamma \;=\; \sum_k |q_k| \;=\; \sqrt{1-p}+p \;=\; 1.024679 .
$$

This $\gamma$ is what the page is about. A Pauli channel has every $q_k \ge 0$ and $\gamma = 1$. A channel the simulator cannot represent needs a negative weight, and $\gamma$ measures how far above 1 that pushes it. It is the price of running one location.

Now put nine of them in a circuit: a distance-3 rotated surface-code patch, one round, one `AMPLITUDE_DAMP(0.05)` on each of the nine data qubits.

```python
from qliff.qec.codes import rotated_surface_code

circuit = rotated_surface_code(rows=3, cols=3, rounds=1, p=0.05, channel="AMPLITUDE_DAMP")
```

Each of the nine locations multiplies the weight by its $\gamma$, so a shot that runs the whole circuit comes back with magnitude

$$
\Gamma \;=\; \prod_{i=1}^{9}\gamma_i \;=\; \gamma^{9} \;=\; 1.245352 .
$$

$\Gamma$ is the price of one shot, and the whole page is about paying less of it. The reason it is so expensive comes first, then the fix: sort the shots by how many locations actually faulted, and $\Gamma$ divides out before any number is formed.

## Every trajectory carries the same magnitude

Draw three thousand weighted trajectories and look at the weights themselves, not their average:

```python
import numpy as np

from qliff.qec.sampler import WeightedDetectorSampler

_dets, _obs, weights = WeightedDetectorSampler(circuit).sample(3000, seed=7)
print("distinct |w|:", np.unique(np.round(np.abs(weights), 9)))
print("signs:", int((weights > 0).sum()), "plus /", int((weights < 0).sum()), "minus")
# -> distinct |w|: [1.24535216]
# -> signs: 2710 plus / 290 minus
```

Three thousand shots, **one** distinct magnitude. Every trajectory came back carrying $\Gamma = 1.245352$, and the only thing that differed between them was the sign.

<figure class="q-fig">
  <div class="q-fig-title">3000 weighted trajectories, one magnitude</div>
  <ul class="q-legend">
    <li style="--c:var(--ok)">weight = +&Gamma;</li>
    <li style="--c:var(--bad)">weight = -&Gamma;</li>
  </ul>
  <ul class="q-bars">
    <li style="--v:.9033;--c:var(--ok)"><b>+1.245352</b><span class="q-track"></span><i>2710</i></li>
    <li style="--v:.0967;--c:var(--bad)"><b>-1.245352</b><span class="q-track"></span><i>290</i></li>
  </ul>
  <div class="q-fig-note">Bar length is the shot count, colour is the sign of the weight. There is no third bar and no spread: the sampler's weight histogram for this circuit is two spikes at &plusmn;&Gamma;, seed 7.</div>
</figure>

That is not a coincidence, it is the sampling rule. At every noise location the shot's weight multiplies by $\operatorname{sign}(q_k)\,\gamma$, and $|{\operatorname{sign}(q_k)\,\gamma}| = \gamma$ whether the location fired the identity branch or a fault branch. After $A$ locations,

$$
|w| \;=\; \prod_{i=1}^{A} \gamma_i \;=\; \Gamma \qquad\text{for every shot, always.}
$$

So the logical error rate comes out of `_weighted_error_rate` as the mean of $N$ numbers, each of which is $+\Gamma$, $-\Gamma$ or $0$, and the answer is a probability of order $10^{-2}$ or smaller. The estimator is asking cancellation to do all the work. Its standard error inflates by $\Gamma$ over the Pauli case, so the shot budget inflates by $\Gamma^2$ (the same rule the [LER page](./ler) uses for coherent noise):

$$
N_{\text{flat}} \;=\; \Gamma^2\,N_{\text{binom}},
\qquad
N_{\text{binom}} \;=\; \frac{1-\mathrm{LER}}{\mathrm{LER}\cdot \varepsilon^2}
\ \ \text{for a relative bar } \varepsilon .
$$

And $\Gamma$ is a product over **every** noise location, so it grows exponentially with the size of the experiment. Keeping $p = 0.05$ and running $d$ rounds of a distance-$d$ patch:

<figure class="q-fig">
  <div class="q-fig-title">Gamma across surface-code sizes (amplitude damping, p = 0.05, d rounds)</div>
  <ul class="q-legend">
    <li style="--c:var(--muted)">noise locations A = d<sup>2</sup> &times; d</li>
    <li style="--c:var(--bad)">flat shot-budget factor &Gamma;<sup>2</sup></li>
  </ul>
  <table>
    <thead>
      <tr><th>distance d</th><th>locations A</th><th>&Gamma;</th><th style="color:var(--bad)">&Gamma;<sup>2</sup></th></tr>
    </thead>
    <tbody>
      <tr><td>3</td><td>27</td><td>1.93</td><td style="color:var(--bad)">3.7</td></tr>
      <tr><td>5</td><td>125</td><td>21.06</td><td style="color:var(--bad)">4.4 x 10<sup>2</sup></td></tr>
      <tr><td>7</td><td>343</td><td>4282</td><td style="color:var(--bad)">1.8 x 10<sup>7</sup></td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">Computed with qliff's own build_strata, not modelled: A is the number of noise instructions the circuit emits and &Gamma; the product of their per-location gammas. Each step in d multiplies the shot budget by orders of magnitude while the physics stays the same.</div>
</figure>

A full circuit-level model puts a noise location after every gate rather than once per data qubit per round, which pushes the same numbers much harder: the paper this estimator comes from ([arXiv:2512.07304](https://arxiv.org/abs/2512.07304), Myers, Teo, Mishra, Chai and Hui Khoon Ng at CQT/NUS) reports $\Gamma = 2.83$, $141$ and $8.6\times 10^{5}$ at $d = 3, 5, 7$ for amplitude damping, and $\Gamma = 6.6\times 10^{17}$ at $d = 3$ for coherent $R_Z$ noise. At $6.6\times 10^{17}$ there is no shot budget. That is the wall.

**The Gamma wall**

<SvelteIsland :component="GammaWall" />

Legend:
- purple curve = $\Gamma = \gamma^A$ vs noise locations $A$ (log y)
- red dot = selected $A$
- `Pauli shots` = binomial budget at a 10% bar
- `flat shots` = `Pauli shots` times $\Gamma^2$

## Sort the shots by how many locations faulted

The move is to split the trajectories into **strata** by their **fault count** $k$: how many of the $A$ locations took a branch other than identity. Every trajectory lands in one stratum, so the answer splits with them:

$$
\mathrm{LER} \;=\; \sum_{k=0}^{A} m_k\,F_k ,
$$

where $m_k$ is the stratum's total **signed quasiprobability mass** and $F_k$ the **conditional error rate given $k$ faults**. Nothing has been approximated: this is the law of total probability, written for a signed measure.

The point is that $m_k$ does not have to be sampled. Summarise location $i$ by two numbers: $a_i$, the weight of its identity branch, and $b_i$, the summed weight of all its fault branches. Trace preservation says every location's weights sum to one, so

$$
a_i + b_i = 1 \qquad\text{for every location.}
$$

Choosing a branch at each location is then choosing one term of the product $\prod_i (a_i + b_i)$, and collecting the terms with $k$ fault factors is reading off a polynomial coefficient:

$$
\sum_k m_k\,x^k \;=\; \prod_{i=1}^{A}\big(a_i + b_i\,x\big) ,
\qquad
m_k = [x^k]\prod_i (a_i + b_i x).
$$

That is `stratum_masses` in `qliff/noise/sampler.py`, one convolution per location. For the running example, $a = q_I = 0.962340$ and $b = q_Z + q_R = 0.037660$ at every location, giving

| stratum k | mass m_k | sampled P(k) | mean sign |
| --- | --- | --- | --- |
| 0 | +0.707874 | 0.568412 | 1.000000 |
| 1 | +0.249318 | 0.331392 | 0.604114 |
| 2 | +0.039027 | 0.085869 | 0.364953 |
| 3 | +0.003564 | 0.012979 | 0.220473 |

Two distributions, not one, and they differ. $m_k$ is the **truth**: the signed mass the channel puts on $k$ faults, summing to 1. $P(k)$ is what the **sampler** draws: the Poisson-binomial of the per-location fault probabilities $\varphi_i = \text{gfault}_i/\gamma_i$, where $\text{gfault}_i = \sum_{k \ne I}|q_k|$ is the location's summed **absolute** fault weight. The split between the two columns is the crux: the mass is built from the **signed** fault weight $b_i$, while the sampler draws from the absolute $\text{gfault}_i$. The last column, $m_k/(\Gamma P(k))$, measures the gap that opens up between them, and the next section is what it costs.

::: info The masses are signed in general
For amplitude damping both $a$ and $b$ come out positive, so every $m_k$ here is positive and the masses read like an ordinary probability distribution. That is a property of this channel, not of the method: nothing forces $a_i$ or $b_i$ to be non-negative, and where they are not, some $m_k$ are negative and the "conditional error rate" $F_k$ is a ratio of signed masses that can fall outside $[0,1]$. Only the total $\sum_k m_k F_k$ has to be a probability.
:::

**Where the answer lives**

<SvelteIsland :component="MassBars" />

Legend:
- purple bar = $m_k$, the signed mass of stratum $k$ (red if negative)
- grey bar = $P(k)$, what the sampler draws from
- `mean sign` = $m_k / (\Gamma\,P(k))$

## Self-normalising one stratum

Now sample **inside** a stratum. Fix $k$, draw $k$ faulty locations from the Poisson-binomial (`fault_set`), and at each of them draw a fault branch with probability $|w|/\text{gfault}_i$ (`pick_branch`). Write $S$ for the chosen fault set. The trajectory's true weight and the probability of having drawn it are

$$
w_{\text{true}} = \prod_{i\notin S} a_i \prod_{i\in S} w_{j_i},
\qquad
\Pr[\text{traj}] = \frac{1}{P(k)}\prod_{i\notin S}\frac{a_i}{\gamma_i}\prod_{i\in S}\frac{|w_{j_i}|}{\gamma_i},
$$

using $1-\varphi_i = a_i/\gamma_i$ and $\varphi_i = \text{gfault}_i/\gamma_i$. Divide, and every $a_i$ and every $|w_{j_i}|$ cancels:

$$
\frac{w_{\text{true}}}{\Pr[\text{traj}]} \;=\; \Gamma\,P(k)\;\prod_{i\in S}\operatorname{sign}(w_{j_i}) \;=\; \Gamma\,P(k)\cdot \sigma ,
$$

with $\sigma = \pm 1$ the product of the chosen branches' signs. **Every trajectory in stratum $k$ carries the same importance weight up to that sign.** The natural first move is to estimate $F_k$ as a **ratio**, dividing that common weight out:

$$
\widehat F_k^{\;\text{ratio}} \;=\; \frac{\sum_{\text{shots in }k} \sigma\cdot\mathbf 1[\text{decoder wrong}]}{\sum_{\text{shots in }k} \sigma} .
$$

The common factor $\Gamma\,P(k)$ divides out of numerator and denominator, so $\Gamma$ never touches the arithmetic. This is the self-normalisation, and it is why `StratifiedDetectorSampler.sample` hands back signs and stratum labels instead of weights:

```python
from qliff.qec.sampler import StratifiedDetectorSampler

_dets, _obs, signs, strata = StratifiedDetectorSampler(circuit).sample(3000, seed=7)
print(sorted(set(signs.tolist())))
# -> [-1.0, 1.0]
```

That denominator is a **sampled** sum of $\pm 1$ signs, and the next section shows it decays like $r^k$. Once it is small, dividing by it is dividing by noise. So qliff does not take the ratio. Its expectation is already known: $\mathbb E[\sigma] = r_k = m_k/(\Gamma P(k))$, the mean-sign column of the mass table. Rather than divide by a noisy estimate of $r_k$, subtract the known $r_k$ as a **control variate**:

$$
y \;=\; \sigma\,\mathbf 1[\text{wrong}] \;-\; \beta\,(\sigma - r_k),
\qquad
\widehat{\mathrm{LER}} \;=\; \sum_k \Gamma\,P(k)\;\overline{y_k} .
$$

Because $\mathbb E[\sigma] = r_k$ holds analytically, $\mathbb E[y] = \mathbb E[\sigma\,\mathbf 1[\text{wrong}]]$ for **any** $\beta$: the estimate is unbiased, and there is no denominator to blow up. The coefficient $\beta$ is the variance-optimal $\mathrm{Cov}(\sigma\mathbf 1[\text{wrong}],\,\sigma)/\mathrm{Var}(\sigma)$, computed leave-one-out (`_loo_beta`) so it never scores the shot it was fit on. At $\beta = 0$ it reduces to the plain within-stratum mean $\Gamma P(k)\,\overline{\sigma\mathbf 1[\text{wrong}]}$, and the control variate only shrinks the variance from there. That is `_stratified_error_rate` in `qliff/qec/threshold.py`.

Two consequences:

- **$\Gamma$ never appears in the answer.** The flat estimator averages numbers of size $\Gamma$. This one averages $\pm 1$ signs and multiplies by masses that sum to 1. At $\Gamma = 6.6\times 10^{17}$ that is the difference between an estimator that returns a number and one that does not.
- **The $k=0$ stratum is free.** It contains one trajectory (identity everywhere), so $F_0$ is not estimated but evaluated. On the running example that single shot settles 70.8% of the answer, and `allocate` seats $k=0$ with that one shot rather than spending its full proportional share on it.

<figure class="q-fig">
  <div class="q-fig-title">The two ledgers, side by side</div>
  <ul class="q-legend">
    <li style="--c:var(--bad)">flat importance sampling</li>
    <li style="--c:var(--accent)">stratified, control-variate</li>
  </ul>
  <table>
    <thead>
      <tr><th></th><th style="color:var(--bad)">flat</th><th style="color:var(--accent)">stratified</th></tr>
    </thead>
    <tbody>
      <tr><td>per-shot payload</td><td style="color:var(--bad)">signed weight &plusmn;&Gamma;</td><td style="color:var(--accent)">sign &plusmn;1 + stratum k</td></tr>
      <tr><td>estimator</td><td style="color:var(--bad)">mean(w &middot; wrong)</td><td style="color:var(--accent)">&Sigma;<sub>k</sub> &Gamma;P(k) &middot; mean(y<sub>k</sub>)</td></tr>
      <tr><td>fault-count weights</td><td style="color:var(--bad)">sampled</td><td style="color:var(--accent)">computed</td></tr>
      <tr><td>k = 0 stratum</td><td style="color:var(--bad)">~57% of shots</td><td style="color:var(--accent)">1 shot, evaluated</td></tr>
      <tr><td>residual noise source</td><td style="color:var(--bad)">&Gamma; across all A locations</td><td style="color:var(--accent)">sign cancellation across k faults</td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">Both estimators are unbiased for the same quantity and both run the same trajectories through the same decoder. They differ in what each shot is allowed to carry, and therefore in what sets the error bar.</div>
</figure>

## What survives: the signs

Cancelling $\Gamma$ does not remove the sign problem, it relocates it. The sign in question is the quasiprobability sign $\operatorname{sign}(q_k)$ each branch carries. The estimator keeps every one of them, because the ratio is built from nothing else. What changes is where the cost of those signs lands. Take the expectation of the denominator. A faulty location picks fault branch $j$ with probability $|w_j|/\text{gfault}_i$, so its mean sign is

$$
r_i \;=\; \sum_j \frac{|w_j|}{\text{gfault}_i}\operatorname{sign}(w_j) \;=\; \frac{b_i}{\text{gfault}_i} ,
$$

the ratio of the location's **signed** fault weight to its **absolute** one. With identical locations the mean sign of a stratum-$k$ trajectory is $r^k$, and that is the third column of the mass table: $m_k/(\Gamma P(k)) = r^k$. For amplitude damping,

$$
r \;=\; \frac{q_R + q_Z}{q_R + |q_Z|} \;=\; \frac{0.037660}{0.062340} \;=\; 0.604114 \quad (p = 0.05),
$$

and it barely moves with $p$: 0.6008 at $p=0.01$, 0.6041 at $p = 0.05$, 0.6180 at $p=0.2$. Coherent $R_Z$ is harsher, $r \approx 0.22$ at $\theta = 0.05$ and $0.27$ at $\theta = 0.2$, because two of its three fault branches ($Z$ and $S^\dagger$) carry negative weight.

The measured signs match:

```python
import numpy as np

for k in (0, 1, 2, 3):
    sel = strata == k
    print(f"k={k}  n {int(sel.sum()):4d}  sum(sign) {signs[sel].sum():+6.0f}  mean {signs[sel].mean():.4f}")
# -> k=0  n    1  sum(sign)     +1  mean 1.0000
# -> k=1  n 2292  sum(sign)  +1370  mean 0.5977
# -> k=2  n  595  sum(sign)   +211  mean 0.3546
# -> k=3  n   91  sum(sign)    +11  mean 0.1209
```

At $k=1$ the signs lean $+0.60$ and the stratum is well resolved. By $k=3$ they net a mean near $0.12$, and past that $r^k$ sinks into the sampling noise. The control variate removes the ratio's divide-by-a-vanishing-number failure, but it cannot manufacture information the signs no longer carry: as $r^k \to 0$ each $y$ is almost pure sign and little signal, so $\mathrm{Var}(y)$ climbs and the stratum's contribution turns noisy. Nothing divides by zero, but a stratum whose signs have washed out still spends shots for almost nothing. The [interpolation mode](#interpolate) stops paying for those strata at all.

Notice the exponent. $\Gamma$ is exponential in $A$, the number of **locations**. The surviving cancellation is exponential in $k$, the number of **faults**. Stratification swaps one exponent for the other. Whether that is a good trade depends on the channel, and the [last section](#cost) puts measured numbers on it.

**Sign cancellation inside one stratum**

<SvelteIsland :component="SignTally" />

Legend:
- green `+` = trajectory sign $+1$
- red `-` = trajectory sign $-1$
- filled cell = decoder wrong
- `sum(sign)` = net sign of the stratum (washes out as r^k)

## Beyond the resolvable zone: interpolation {#interpolate}

The signed mean $r^k$ is resolvable only while it stays above the sampling noise, roughly $k \lesssim 7$ for amplitude damping and $k \lesssim 2$ for coherent $R_Z$. Past that, no number of shots recovers $F_k$, so paying for those strata is waste. `interpolate=True` stops sampling them. It pins the shape of $F_k$ at both ends and samples only the transition in between, the closest qliff gets to the paper's smooth logistic $F_k$ (its Fig. 7).

- **Lower end, measured.** For small $k$, `_interpolated_error_rate` runs an **exhaustive** scan: it decodes every $k$-fault configuration, so $F_k$ there is computed, not sampled. This matters because $F_k$ is not trivially zero at small $k$. An unprotected colouring of the code can fail on a **single** amplitude-damping event, real physics that an "errors below the distance are harmless" assumption would miss.
- **Upper end, pinned.** As faults accumulate the logical state fully mixes and $F_k \to 0.5$. Strata above the resolvable zone are pinned there, and the bias that introduces is bounded and reported as the mass-weighted deviation from the pin, never hidden.

```python
from qliff.qec.codes import rotated_surface_code
from qliff.qec.threshold import logical_error_rate

memory = rotated_surface_code(rows=3, cols=3, rounds=2, p=0.05, channel="AMPLITUDE_DAMP", prep=True)
for seed in (0, 1, 2):
    strat, _ = logical_error_rate(memory, "coherent", shots=1200, seed=seed, stratify=True)
    interp, _ = logical_error_rate(memory, "coherent", shots=1200, seed=seed, interpolate=True)
    print(f"seed={seed}  stratify {strat:.5f}   interpolate {interp:.5f}")
# -> seed=0  stratify 0.02295   interpolate 0.02165
# -> seed=1  stratify 0.01442   interpolate 0.02639
# -> seed=2  stratify 0.01984   interpolate 0.02105
```

On this small patch the resolvable zone already covers most of the mass, so interpolation lands in the same range as the full stratified estimate rather than beating it. Its advantage shows when the resolvable zone is a thin slice of the strata that carry mass, the high-$\Gamma$ regime the [next section](#cost) is about.

## The Pauli sanity check

Everything above collapses to something ordinary when the noise is Pauli. Every branch has $q_k \ge 0$, so $\gamma = 1$ and $\Gamma = 1$, the signed fault weight equals the absolute one so $r = 1$ and every trajectory sign is $+1$, and $m_k$ is the Poisson-binomial $P(k)$ itself.

```python
from qliff import Circuit
from qliff.noise.sampler import build_strata

pauli = Circuit(5)
for q in range(5):
    pauli.append("X_ERROR", [q], 0.08)

_locs, _phis, pk, mass = build_strata(pauli.instructions)
print([round(m, 8) for m in mass[:4]])
print([round(x, 8) for x in pk[:4]])
print("identical:", all(abs(m - x) < 1e-12 for m, x in zip(mass, pk)))
# -> [0.65908152, 0.28655718, 0.04983603, 0.00433357]
# -> [0.65908152, 0.28655718, 0.04983603, 0.00433357]
# -> identical: True
```

With every sign $+1$, the control variate's $(\sigma - r_k)$ term vanishes and $y = \mathbf 1[\text{wrong}]$, so each stratum contributes $P(k)$ times its plain failure rate. The method is ordinary stratified sampling: partition by fault count, count failures in each part, recombine with known weights. The signs and the two-distribution split are all a non-Pauli channel adds on top.

::: details Worked example: stratum k = 1 of the 3x3 damping patch

Nine locations, all identical, $a = 0.962340$ and $b = 0.037660$.

1. **Mass.** One location faults, the other eight do not, and there are nine ways to choose which: $m_1 = 9\,a^{8}b = 9 \times 0.962340^{8} \times 0.037660 = 0.249318$.
2. **Sampling odds.** The sampler's per-location fault probability is $\varphi = \text{gfault}/\gamma = 0.062340/1.024679 = 0.060838$, so $P(1) = 9\,(1-\varphi)^{8}\varphi = 0.331392$. It draws stratum 1 more often than its mass deserves, because it is drawing from $|q|$, not $q$.
3. **Weight magnitude.** Every stratum-1 trajectory carries $\Gamma P(1) = 1.245352 \times 0.331392 = 0.412700$, times its sign. The magnitude is identical for all 745 of them.
4. **Mean sign.** The one faulty location picks $Z$ with probability $|q_Z|/\text{gfault} = 0.012340/0.062340 = 0.198$ and $R$ with probability $0.802$, so the mean sign is $0.802 - 0.198 = 0.604114 = r$. Times $\Gamma P(1)$ that is $0.249318 = m_1$: the identity $m_k = \Gamma P(k) r^k$ closes.
5. **The estimate.** The sampler drew 745 trajectories here, 602 with sign $+1$ and 143 with sign $-1$, so $\sum\sigma = 459$ against an expectation of $745 \times 0.604114 = 450$. $\widehat F_1$ is $\sum \sigma\,\mathbf 1[\text{wrong}]$ over that 459, and stratum 1 contributes $m_1 \widehat F_1$ to the logical error rate.

**Result:** the 0.249318 of the answer that lives at $k = 1$ was known before a single shot was taken. The 745 shots were spent only on $F_1$, and the $\Gamma P(1) = 0.4127$ they each carried never entered the arithmetic.

:::

## What it costs {#cost}

The control variate does not need a crossover argument to be safe. At $\beta = 0$ it is a stratified flat mean, and the optimal $\beta$ only lowers the variance from there, so it is never worse than flat by more than sampling noise. What is left to ask is how much it wins, and that is capped by the sign decay $r^k$: past the resolvable zone a stratum's shots carry almost no information no matter how many you take.

Measured on the running patch, with a `prep` round so the damping has something to act on, decoded by the `coherent` decoder, spread of the estimate over eight seeds:

<figure class="q-fig">
  <div class="q-fig-title">Estimator spread over 8 seeds, distance-3 patch, p = 0.05</div>
  <ul class="q-legend">
    <li style="--c:var(--bad)">flat importance sampling</li>
    <li style="--c:var(--accent)">stratified, control-variate</li>
  </ul>
  <table>
    <thead>
      <tr><th>rounds</th><th>A</th><th>&Gamma;</th><th style="color:var(--bad)">flat spread</th><th style="color:var(--accent)">stratified spread</th></tr>
    </thead>
    <tbody>
      <tr><td>2</td><td>18</td><td>1.55</td><td style="color:var(--bad)">0.0066</td><td style="color:var(--accent)">0.0030</td></tr>
      <tr><td>4</td><td>36</td><td>2.41</td><td style="color:var(--bad)">0.0208</td><td style="color:var(--accent)">0.0117</td></tr>
      <tr><td>6</td><td>54</td><td>3.73</td><td style="color:var(--bad)">0.0188</td><td style="color:var(--accent)">0.0224</td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">1200 requested shots per estimate, seeds 0-7, decoder "coherent". allocate seats nearly all of them (1197, 1196, 1196). At &Gamma; around 1.5 to 2.4 the control variate roughly halves the spread. By &Gamma; around 3.7 the sign decay has caught up and the two are level. The retired self-normalised ratio lost to flat at every size here, which is why it was replaced.</div>
</figure>

Read the table as the method's shape, not a verdict. Three things set how far ahead it gets:

- **How badly the signs cancel.** The per-fault discount is $r^k$. Amplitude damping's $r = 0.604$ is steep, so within a handful of faults a stratum's signs have washed out. A channel whose fault branches are mostly positive has $r$ near 1 and barely pays.
- **Where the shots go.** `allocate` runs a pilot pass proportional to $P(k)$, measures each stratum's spread $V_k$, then spends the rest by Neyman, $n_k \propto P(k)\sqrt{V_k}$. Proportional allocation alone only ties flat sampling. The $\sqrt{V_k}$ factor is the win, moving shots off the strata that never vary and onto the ones that carry the failures.
- **How large $\Gamma$ is.** At $\Gamma \approx 2$ flat is barely inconvenienced, so the margin is modest. At $\Gamma = 8.6\times 10^{5}$ flat cannot produce a number at all, whatever its asymptotics say, and a noisy estimate beats none. Surviving the high-$\Gamma$ end is the whole reason the method exists.

::: warning A stratum the budget could not seat is missing, not conservative
`StratifiedDetectorSampler` banks the mass of any stratum it could not seat in `dropped_mass`. Check that field: it is the fraction of the answer the run did not look at. On the running example it is $1.5\times 10^{-13}$, which is fine. If it comes back at $10^{-2}$, the estimate is missing a percent of its own definition.
:::

## Implementation {#implementation}

The tabs rebuild the page in code, all on the same damping patch.

**Pseudocode.** The two estimators side by side, so the structural difference is visible at a glance: what a shot carries, and how the strata recombine.

**Std Python.** Four locations in NumPy, small enough to brute-force. It builds the masses by convolution, enumerates all $3^4$ branch assignments to get the true logical error rate, and checks $\sum_k m_k F_k$ against it to the last digit. It also confirms $m_k/(\Gamma P(k)) = r^k$, the identity the whole page turns on.

**Qliff.** The same objects from the library: `build_strata` for the masses, `WeightedDetectorSampler` for the flat weights, `StratifiedDetectorSampler` for the signs and strata, and `logical_error_rate(..., stratify=True)` (or `interpolate=True`) for the end-to-end estimate.

::: code-group

```text [Pseudocode]
# --- flat importance sampling (tutorial 06) --------------------------------
for shot in 1..N:
    weight = 1
    for location in circuit:
        draw branch k with probability |q_k| / gamma
        weight = weight * sign(q_k) * gamma        # |weight| = Gamma, always
    emit (detection events, weight)
ler = mean over shots of weight * decoder_is_wrong # a mean of +/- Gamma

# --- stratified, control-variate -------------------------------------------
a[i] = identity-branch weight of location i        # a[i] + b[i] = 1
b[i] = summed fault weight of location i
mass = coefficients of prod_i (a[i] + b[i] * x)    # computed, no sampling
phi[i] = gfault[i] / gamma[i]                      # sampling fault odds
P = poisson_binomial(phi)
Gamma = prod_i gamma[i]

ler = 0
for k where |mass[k]| is worth sampling:
    n_k  = shots for stratum k (Neyman: n_k ~ P(k)*sqrt(V_k), k = 0 gets one)
    coef = Gamma * P(k)                            # stratum weight, computed
    r_k  = mass[k] / coef                          # known mean sign E[sign]
    sv = []
    wv = []
    for shot in 1..n_k:
        S = draw k faulty locations from P
        sign = product over i in S of sign(chosen branch weight)
        sv += [sign]
        wv += [sign * decoder_is_wrong]
    beta = leave_one_out Cov(wv, sv) / Var(sv)     # variance-optimal, no bias
    y    = [w - beta * (s - r_k) for s, w in zip(sv, wv)]
    ler  = ler + coef * mean(y)                    # unbiased, no denominator
```

```python [Std Python]
import itertools

import numpy as np

p = 0.05
root = np.sqrt(1.0 - p)
q = np.array([(1.0 - p + root) / 2.0, (1.0 - p - root) / 2.0, p])  # I, Z, R
A = 4

# 1. Every location splits into an identity weight a and a summed fault weight b.
#    Trace preservation forces a + b = 1; the sampler instead sees the ABSOLUTE
#    sums, gfault and gamma, and those do not add up to 1.
a = q[0]
b = q[1:].sum()
gfault = np.abs(q[1:]).sum()
gamma = np.abs(q).sum()
print("a", round(a, 6), " b", round(b, 6), " a+b", round(a + b, 6))
print("gfault", round(gfault, 6), " gamma", round(gamma, 6))
print("phi", round(gfault / gamma, 6), " r = b/gfault", round(b / gfault, 6))
# -> a 0.96234  b 0.03766  a+b 1.0
# -> gfault 0.06234  gamma 1.024679
# -> phi 0.060838  r = b/gfault 0.604114

# 2. Stratum masses = the coefficients of x^k in prod_i (a + b x): analytic, no sampling.
mass = np.array([1.0])
for _ in range(A):
    mass = np.convolve(mass, [a, b])
print("mass", np.round(mass, 6), " sum", round(mass.sum(), 12))
# -> mass [8.57657e-01 1.34254e-01 7.88100e-03 2.06000e-04 2.00000e-06]  sum 1.0

# 3. Brute force over every branch assignment of the 4 locations. Each trajectory
#    has a true signed weight (the product of the q's) and a fault count k. Say the
#    shot is a logical error when two or more locations fired the reset branch.
true_ler = 0.0
per_k = np.zeros(A + 1)
for pick in itertools.product(range(3), repeat=A):
    weight = float(np.prod(q[list(pick)]))
    k = sum(1 for i in pick if i != 0)
    wrong = 1.0 if sum(1 for i in pick if i == 2) >= 2 else 0.0
    true_ler += weight * wrong
    per_k[k] += weight * wrong
print("true LER", round(true_ler, 8))
# -> true LER 0.01401875

# 4. The identity the estimator rests on: LER = sum_k mass[k] * F_k. Note that the
#    conditional rates are ratios of SIGNED masses, so they need not sit in [0, 1];
#    only their mass-weighted sum has to be a probability.
f_k = per_k / mass
print("F_k ", np.round(f_k, 6))
print("sum_k mass[k]*F_k", round(float((mass * f_k).sum()), 8))
# -> F_k  [0.       0.       1.762677 0.607564 1.175289]
# -> sum_k mass[k]*F_k 0.01401875

# 5. Flat sampling gives every trajectory the SAME magnitude, |w| = Gamma, so only
#    the sign moves. Within stratum k the magnitude is Gamma*P(k) and the mean sign
#    is r^k = mass/(Gamma*P(k)), the quantity the estimator turns into F_k.
phi = gfault / gamma
pk = np.array([1.0])
for _ in range(A):
    pk = np.convolve(pk, [1 - phi, phi])
print("Gamma", round(gamma**A, 6))
print("mean sign per stratum", np.round(mass / (gamma**A * pk), 6))
print("r^k                  ", np.round((b / gfault) ** np.arange(A + 1), 6))
# -> Gamma 1.102433
# -> mean sign per stratum [1.       0.604114 0.364953 0.220473 0.133191]
# -> r^k                   [1.       0.604114 0.364953 0.220473 0.133191]
```

```python [Qliff]
import numpy as np

from qliff.noise.sampler import build_strata
from qliff.qec.codes import rotated_surface_code
from qliff.qec.sampler import StratifiedDetectorSampler, WeightedDetectorSampler
from qliff.qec.threshold import logical_error_rate

circuit = rotated_surface_code(rows=3, cols=3, rounds=1, p=0.05, channel="AMPLITUDE_DAMP")

# 1. Flat importance sampling: one magnitude, two signs.
_dets, _obs, weights = WeightedDetectorSampler(circuit).sample(3000, seed=7)
print("distinct |w|:", np.unique(np.round(np.abs(weights), 9)))
print("signs:", int((weights > 0).sum()), "plus /", int((weights < 0).sum()), "minus")
# -> distinct |w|: [1.24535216]
# -> signs: 2710 plus / 290 minus

# 2. The strata, computed rather than sampled.
locs, _phis, pk, mass = build_strata(circuit.instructions)
big = float(np.prod([g for _branches, g in locs]))
print("locations", len(locs), " Gamma", round(big, 6), " sum(mass)", round(sum(mass), 12))
for k in range(4):
    print(f"k={k}  mass {mass[k]:+.6f}  P(k) {pk[k]:.6f}  mean sign {mass[k] / (big * pk[k]):.6f}")
# -> locations 9  Gamma 1.245352  sum(mass) 1.0
# -> k=0  mass +0.707874  P(k) 0.568412  mean sign 1.000000
# -> k=1  mass +0.249318  P(k) 0.331392  mean sign 0.604114
# -> k=2  mass +0.039027  P(k) 0.085869  mean sign 0.364953
# -> k=3  mass +0.003564  P(k) 0.012979  mean sign 0.220473

# 3. The stratified sampler returns SIGNS and stratum labels, never a weight.
_d, _o, signs, strata = StratifiedDetectorSampler(circuit).sample(3000, seed=7)
print("trajectories", len(signs))
for k in np.unique(strata)[:4]:
    sel = strata == k
    print(f"k={k}  n {int(sel.sum()):4d}  sum(sign) {signs[sel].sum():+6.0f}  mean {signs[sel].mean():.4f}")
# -> trajectories 2997
# -> k=0  n    1  sum(sign)     +1  mean 1.0000
# -> k=1  n 2292  sum(sign)  +1370  mean 0.5977
# -> k=2  n  595  sum(sign)   +211  mean 0.3546
# -> k=3  n   91  sum(sign)    +11  mean 0.1209

# 4. End to end. `prep` projects into the code space first, so the damping has an
#    excited population to act on; stratify picks the estimator.
memory = rotated_surface_code(
    rows=3, cols=3, rounds=2, p=0.05, channel="AMPLITUDE_DAMP", prep=True
)
for stratify in (False, True):
    ler, stderr = logical_error_rate(memory, "coherent", shots=1200, seed=0, stratify=stratify)
    print(f"stratify={str(stratify):5s}  LER = {ler:.5f} +/- {stderr:.5f}")
# -> stratify=False  LER = 0.00646 +/- 0.00592
# -> stratify=True   LER = 0.02295 +/- 0.00356
```

:::

One circuit, two ways to spend a shot. Flat importance sampling books $\operatorname{sign}(q)\,\gamma$ at every location and hands the estimator a number of size $\Gamma$. Stratified sampling computes the fault-count masses, spends its shots on the conditional rates, and subtracts the known mean sign so $\Gamma\,P(k)$ never enters the arithmetic. What is left is a sign problem measured in faults rather than in locations, plus the arithmetic of which strata your budget reached. Both feed the same scoreboard: the [logical error rate](./ler), its error bar, and the threshold.
