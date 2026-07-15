---
title: Logical Error Rate & Fidelity
outline: 2
---

# Logical Error Rate & Fidelity <Badge type="info" text="Tutorial 07 of 7" />

> Sample, decode, and compare; then read the threshold off a sweep with error bars.

<script setup>
import ShotsDemo from '../_tut/ler/ShotsDemo.svelte'
import TruthTable from '../_tut/ler/TruthTable.svelte'
import ConvergeDemo from '../_tut/ler/ConvergeDemo.svelte'
import WeightedDemo from '../_tut/ler/WeightedDemo.svelte'
import SweepDemo from '../_tut/ler/SweepDemo.svelte'
import ThresholdDemo from '../_tut/ler/ThresholdDemo.svelte'
</script>

## The verdict of one shot {#verdict}

A round of error correction ends with a single yes/no question: *did the logical qubit survive?* We run the noisy circuit, read out the syndrome, hand it to a decoder, and the decoder announces which logical observables it thinks were flipped: its **prediction**. We also know the **truth**, because in simulation we tracked the true errors. The shot is a **logical error** when the prediction disagrees with the truth.

That is the whole verdict, and it is what qliff computes: $\text{shot is wrong} \iff \text{predicted} \neq \text{true}$. Below is a grid of shots. Each cell shows `predicted / true` for the logical observable. Click a cell to flip the decoder's guess and watch the running rate.

**Shot verdicts**

<SvelteIsland :component="ShotsDemo" />

Legend:
- green: predicted = true (survived)
- red: predicted != true (logical error)

*48 decoded shots, each cell reading predicted / true for the logical observable. Green = decoder agreed with the truth (corrected); red = it disagreed (a logical error). The LER is the red fraction.*

## Fidelity and LER {#fidelity}

Stack up many shots and the rate of red cells is the **logical error rate**. Its complement is the **logical fidelity**, the fraction of shots that came through clean. In qliff this is one line (`codes.py`):

$$P_L = \frac{1}{N}\sum_{i=1}^{N} \mathbf{1}\!\left[\text{pred}_i \neq \text{obs}_i\right] = \frac{\text{fails}}{N}, \qquad F = 1 - P_L.$$

Here $P_L$ is the logical error rate, $F$ the fidelity, $N$ the number of shots, and $\mathbf{1}[\cdot]$ the indicator that is 1 when shot $i$ fails (predicted $\neq$ observed) and 0 otherwise, so the sum is the failure count.

A subtlety appears when a code protects more than one logical qubit (the toric code has two). Each shot then has a *row* of observables. qliff's rule is strict: the shot fails if **any** column disagrees, in code $\texttt{np.any}(\text{pred} \neq \text{obs},\, \text{axis}=1)$. Getting most observables right is not partial credit.

**Try the np.any rule**

<SvelteIsland :component="TruthTable" />

## It's a Monte-Carlo estimate, so it has error bars {#montecarlo}

We never see the true LER directly; we *estimate* it by sampling a finite number of shots $N$. That makes the reported LER a sample mean, and sample means jitter. For ordinary (Pauli) noise the verdict per shot is a coin flip, so the spread of the estimate is the textbook **binomial standard error**, which is what qliff returns alongside the LER:

$$\mathrm{stderr} = \sqrt{\dfrac{\mathrm{LER}\,(1-\mathrm{LER})}{N}} \;\propto\; \dfrac{1}{\sqrt{N}}.$$

The demo below runs a seeded Monte-Carlo in your browser: the distance-$d$ repetition code under bit-flip noise, decoded by majority vote. A logical error happens when more than $d/2$ of the $d$ bits flip; that probability is a binomial tail (the green line). Watch the estimate converge and the $\pm\,\mathrm{stderr}$ band taper as $N$ grows.

**Convergence with N**

<SvelteIsland :component="ConvergeDemo" />

Legend:
- running LER estimate (purple line)
- $\pm 1\sigma$ binomial band
- exact LER (green dash)

*Seeded Monte-Carlo of the repetition code. x = shots N (log); y = running LER estimate (% of shots). The purple trace is the running estimate; the band is $\pm 1\sigma = \pm\,\mathrm{stderr}$; the green dashed line is the exact LER. The band shrinks like $1/\sqrt{N}$.*

::: details An error bar from 37 failures in N = 4000 shots

1. Count the verdicts: the decoder was wrong on **37** of $N = 4000$ shots (qliff: a shot fails iff predicted $\neq$ observed).
2. The Monte-Carlo estimate is the failure fraction: $P_L = \tfrac{\text{fails}}{N} = \tfrac{37}{4000} = 0.00925$.
3. Fidelity is its complement: $F = 1 - P_L = 0.99075$.
4. The binomial standard error: $\sigma = \sqrt{\tfrac{P_L(1-P_L)}{N}} = \sqrt{\tfrac{0.00925 \cdot 0.99075}{4000}} \approx 0.00151$.
5. To *halve* the bar you need $4\times$ the shots ($\sigma \propto 1/\sqrt{N}$): $N = 16{,}000$ drops $\sigma$ to $\approx 0.00076$.

**Result:** Report $P_L = 0.0093 \pm 0.0015$ (fidelity $F \approx 0.9908$). Quartering the error bar costs **16x** the shots.

:::

::: info Why rare errors are expensive
Push `p` down or `d` up and the true LER can fall below 0.45%. With few shots you may see *zero* errors and report LER = 0 with a deceptively tiny error bar. To resolve a LER of $\varepsilon$ you need roughly $N \gtrsim 1/\varepsilon$ shots to see even a handful of errors; the deeper the suppression, the more shots it costs.
:::

## The weighted case: coherent noise {#weighted}

Coherent noise (a small over-rotation, amplitude damping) is *not* a random Pauli flip, so no valid detector-error model exists to sample from. qliff's way around this is **importance sampling**: it draws stabilizer trajectories from a quasiprobability and attaches a **signed weight** $w$ to each shot. The LER becomes a weighted mean (`threshold.py: _weighted_error_rate`):

$$\mathrm{LER} = \operatorname*{mean}_{\text{shots}}\big(w \cdot \text{error}\big), \qquad \mathrm{stderr} = \dfrac{\operatorname{std}(w \cdot \text{error})}{\sqrt{N}},$$

with the result clamped to $[0,1]$. The weights average to one, so the estimate is unbiased, but their spread inflates the variance. Each weight has magnitude $\gamma$, so $\operatorname{var}(w\cdot\text{error}) \approx \gamma^2 P_L$ and the error bar grows by a factor of $\gamma$ over the Pauli case:

$$\sigma_{\text{w}} \approx \gamma\,\sqrt{\dfrac{P_L}{N}} = \gamma\,\sigma_{\text{binom}} \;\Longrightarrow\; N_{\text{w}} \approx \gamma^2\,N_{\text{binom}}\ \text{for the same bar.}$$

The negativity $\gamma \ge 1$ from the coherent-noise engine measures that spread: bigger $\gamma$ means noisier weights, a wider error bar, and many more shots for the same precision. (This ties back to the coherent-noise and noise-sampling pages.)

**Coherent shot cost**

<SvelteIsland :component="WeightedDemo" />

Legend:
- Pauli: shots for 10% error bar
- coherent ($\gamma$): inflated shot budget

*Importance-weighted LER. Bars compare shots needed for a 10% relative error bar: Pauli (binomial) vs coherent (variance inflated by $\gamma^2$). The estimate stays unbiased as $\gamma$ grows, but the standard error grows too: you pay for non-Pauli noise in shots.*

::: details The gamma cost: how many more shots at gamma = 2?

1. Take a true LER of $P_L \approx 0.00116$ (the repetition code at $p=0.05,\ d=5$).
2. A Pauli (binomial) run needs $N_{\text{binom}} = \tfrac{1-P_L}{P_L\,(0.1)^2} \approx 86{,}247$ shots for a 10% relative bar.
3. Coherent noise carries weights of magnitude $\gamma = 2$, inflating the variance by $\gamma^2 = 4$.
4. So the same bar now costs $N_{\text{w}} = \gamma^2 N_{\text{binom}} \approx 4 \times 86{,}247 \approx 344{,}988$ shots.

**Result:** A modest $\gamma = 2$ already quadruples the shot budget; at $\gamma = 3$ the factor is **9x**. Non-Pauli noise is expensive.

:::

## The sweep: LER versus p {#sweep}

One LER is a single dot. The interesting object is the **curve**: how the logical error rate responds as we dial the physical rate $p$ up and down. qliff's `sweep(circuit_fn, p_values, ...)` does this: it rebuilds the circuit at each $p$, runs the sample -> decode -> compare loop, and yields a $(p,\ \mathrm{LER},\ \mathrm{stderr})$ triple per point, with the **seed held fixed** across points so the curve is reproducible.

Below, the smooth line is the exact repetition-code LER and the points are seeded Monte-Carlo with binomial error bars. At small $p$ the code *helps*: the LER sits far below the break-even dashed line $\mathrm{LER} = p$. Push $p$ too high and majority vote starts losing: the code *hurts*.

**LER vs p sweep**

<SvelteIsland :component="SweepDemo" />

Legend:
- exact LER(p) curve
- Monte-Carlo point ($\pm 1\sigma$)

*A reproducible LER(p) sweep for one distance d: x = physical rate p, y = logical rate $P_L$ (log). Exact curve plus seeded Monte-Carlo with binomial error bars: the same (p, ler, stderr) triples qliff's sweep yields.*

## The threshold plot {#threshold}

This plot is the central result of the field. Draw LER versus $p$ on log-log axes for several code **distances** at once, and the curves **cross** at a single point, the **threshold** $p_{th}$:

- **Below $p_{th}$:** bigger $d$ gives **lower** LER. Adding qubits drives the error rate toward zero: error correction *works*, and works better the more you scale.
- **Above $p_{th}$:** bigger $d$ gives **higher** LER. Your hardware is too noisy; adding qubits only adds places to fail.

The plot below uses a standard **phenomenological model** (it is a model, not a fit): $\mathrm{LER}(p,d) \approx A\,(p/p_{th})^{\lceil d/2 \rceil}$, softly saturating above threshold. The crossing is not drawn in by hand; it *emerges* from that exponent as you move the sliders.

**Threshold crossing**

<SvelteIsland :component="ThresholdDemo" />

Legend:
- one line per distance $d$
- $p_{th}$ (curves cross)
- break-even $\mathrm{LER} = p$

*LER vs p (log-log) for several distances d. x = physical rate p, y = logical rate $P_L$. Curves cross at $p_{th}$ (dashed gold), the threshold. Below it, more distance = less logical error; above it, more distance = more. Dotted grey is break-even $\mathrm{LER} = p$.*

::: tip Read it off
Find the crossing. To its left, the steepest (highest-$d$) curve is on the bottom: scaling helps. To its right, that same curve is on top: scaling hurts. A qliff threshold plot is this same picture, with each point produced by a sample -> decode -> compare run instead of a formula.
:::

## The whole pipeline {#pipeline}

Every number on this page comes from the same five-stage loop, repeated $N$ times and averaged:

$$\underbrace{\text{noise}}_{\text{1}} \rightarrow \underbrace{\text{syndrome}}_{\text{2}} \rightarrow \underbrace{\text{decode}}_{\text{3}} \rightarrow \underbrace{\text{compare}}_{\text{4}} \rightarrow \underbrace{\mathrm{LER} = 1 - \text{fidelity}}_{\text{5}}$$

Stage 1 injects errors (Pauli channels sample directly; coherent channels need the weighted sampler from the previous page). Stage 2 reads the stabilizers into a syndrome. Stage 3 is the decoder (MWPM, belief propagation, or a tensor network from the first three pages). Stage 4 is the one-bit verdict of section 1. Stage 5 averages the verdicts into the LER and its error bar.

## Implementation {#implementation}

The same pipeline at three levels of detail in the tabs below: language-free pseudocode, a self-contained NumPy miniature you can check by hand, and the qliff API.

**Pseudocode.** Everything on this page reduces to a counting loop plus one square root; the threshold plot is that loop inside two more.

**Std Python.** A miniature end-to-end pipeline with no qliff: the distance-$d$ repetition code under iid bit flips, decoded by majority vote (the model behind the convergence demo above). The exact LER is a binomial tail, so every Monte-Carlo number can be checked against a closed form. Every estimate lands within a couple of error bars of the exact tail, and the crossing is already visible: below this code's pseudo-threshold ($p = 0.5$), $d=5$ beats $d=3$ by an order of magnitude; above it, the ordering flips and more distance makes things worse.

**Qliff.** The same pipeline against the qliff API: `logical_error_rate` wraps sample -> decode -> compare for one circuit, and `sweep` (or the streaming `isweep`) repeats it across physical rates with the seed held fixed. The first stanza builds the pieces by hand with `DetectorSampler`, `make_decoder`, and `logical_fidelity`; import `qliff.qec.threshold` directly rather than through `qliff.qec`, so that plain `import qliff` stays numpy-only.

::: code-group

```text [Pseudocode]
estimate_ler(code, p, shots, seed):
    circuit = build_noisy_memory(code, p)       # syndrome-extraction rounds at rate p
    detectors, truth = sample(circuit, shots, seed)
    errors = 0
    for each shot s:
        prediction = decode(detectors[s])       # decoder's guess at the observable flips
        if prediction != truth[s]:              # any observable wrong -> logical error
            errors = errors + 1
    ler    = errors / shots
    stderr = sqrt(ler * (1 - ler) / shots)      # binomial error bar
    return ler, stderr

threshold_plot(code_family, distances, p_values):
    for d in distances:
        for p in p_values:
            plot(p, estimate_ler(code_family(d), p, shots, seed))
    # one curve per distance; the curves cross at the threshold p_th
```

```python [Std Python]
from math import comb

import numpy as np


def repetition_ler(d, p, shots, seed):
    """Monte-Carlo LER of a distance-d repetition code under iid bit flips."""
    rng = np.random.default_rng(seed)
    flips = rng.random((shots, d)) < p
    # majority vote fails exactly when more than d/2 bits flipped
    wrong = np.sum(flips, axis=1) > d / 2
    ler = float(np.mean(wrong))
    stderr = float(np.sqrt(ler * (1.0 - ler) / shots))
    return ler, stderr


def exact_ler(d, p):
    """Exact LER: the binomial tail P[more than d/2 of d bits flip]."""
    tail = 0.0
    for k in range(d // 2 + 1, d + 1):
        tail += comb(d, k) * p**k * (1.0 - p) ** (d - k)
    return tail


shots = 200000
for p in [0.05, 0.6]:
    for d in [3, 5]:
        ler, stderr = repetition_ler(d, p, shots, seed=42)
        print(f"p={p} d={d}: LER = {ler:.5f} +/- {stderr:.5f} (exact {exact_ler(d, p):.5f})")
# -> p=0.05 d=3: LER = 0.00710 +/- 0.00019 (exact 0.00725)
# -> p=0.05 d=5: LER = 0.00099 +/- 0.00007 (exact 0.00116)
# -> p=0.6 d=3: LER = 0.64917 +/- 0.00107 (exact 0.64800)
# -> p=0.6 d=5: LER = 0.68407 +/- 0.00104 (exact 0.68256)
```

```python [Qliff]
from qliff.qec.codes import logical_fidelity, repetition_code, rotated_surface_code
from qliff.qec.decoder import make_decoder
from qliff.qec.dem import DetectorErrorModel
from qliff.qec.sampler import DetectorSampler
from qliff.qec.threshold import logical_error_rate, sweep

# the pipeline by hand: sample -> decode -> compare
circuit = repetition_code(distance=5, rounds=3, p=0.05, channel="X_ERROR")
dets, obs = DetectorSampler(circuit).sample(4000, seed=7)
decoder = make_decoder("mwpm", DetectorErrorModel(circuit))
predictions = decoder.decode_batch(dets)
print(f"LER = {1.0 - logical_fidelity(predictions, obs):.4f}")
# -> LER = 0.0022

# the same point in one call, with the binomial error bar included
ler, stderr = logical_error_rate(circuit, decoder_name="mwpm", shots=4000, seed=7)
print(f"LER = {ler:.4f} +/- {stderr:.4f}")
# -> LER = 0.0022 +/- 0.0007


# the sweep: circuit_fn(p) rebuilds the code at each physical rate
def surface(d):
    def circuit_fn(p):
        return rotated_surface_code(rows=d, cols=d, rounds=3, p=p)

    return circuit_fn


for d in [3, 5]:
    curve = sweep(
        surface(d),
        p_values=[0.01, 0.08],
        decoder_name="mwpm",
        shots=1000,
        seed=11,
    )
    for p, ler, stderr in curve:
        print(f"d={d} p={p}: LER = {ler:.4f} +/- {stderr:.4f}")
# -> d=3 p=0.01: LER = 0.0030 +/- 0.0017
# -> d=3 p=0.08: LER = 0.1090 +/- 0.0099
# -> d=5 p=0.01: LER = 0.0010 +/- 0.0010
# -> d=5 p=0.08: LER = 0.0750 +/- 0.0083
```

:::

Both physical rates sit below this circuit family's threshold, so $d=5$ suppresses the LER further than $d=3$ at each point. Choosing well: pick several **distances** to expose the crossing; use enough **shots** that the rarest LER you care about is resolved ($N \gtrsim 1/\mathrm{LER}$, and $\times\,\gamma^2$ more for coherent noise); pick a **decoder** matched to your code; and **fix the seed** so the whole sweep is reproducible.

::: info The series in summary
Three decoders turn a syndrome into a correction: **matching**, **belief propagation**, and **tensor networks**. Two noise pages model the input: **coherent channels** as signed quasiprobabilities, sampled into **weighted trajectories**. This final page is the scoreboard: feed decoder and noise into sample -> decode -> compare, average the verdicts, and read the **logical error rate**, its **error bar**, and the **threshold** that says whether scaling up will save you.
:::
