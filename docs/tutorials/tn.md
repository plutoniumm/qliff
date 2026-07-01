---
title: Tensor-Network Decoder
outline: 2
---

# Tensor-Network Decoder <Badge type="info" text="Tutorial 04 of 7" />

> Sum over every possible error at once by contracting a factor graph -- exact maximum likelihood.

<script setup>
import DegeneracyPlay from '../_tut/tn/DegeneracyPlay.svelte'
import TensorPlay from '../_tut/tn/TensorPlay.svelte'
import FactorGraphPlay from '../_tut/tn/FactorGraphPlay.svelte'
import ContractionPlay from '../_tut/tn/ContractionPlay.svelte'
import CostChart from '../_tut/tn/CostChart.svelte'
import TruncationPlay from '../_tut/tn/TruncationPlay.svelte'
</script>

## The right question to ask

A quantum code never tells you which physical errors happened. It hands you a **syndrome**: a short list of parity checks that came out odd. Your job is to guess a correction that undoes the error's effect on the encoded logical information. The catch that breaks naïve decoders is this:

::: tip Many errors, one syndrome, one logical effect
Different physical errors routinely produce the *same* syndrome. Often they also have the *same* effect on the logical qubit. To rank your options correctly you should not pick the single most likely error -- you should add up the probability of *every* error that lands in the same logical class.
:::

Matching (MWPM) and belief propagation answer a slightly wrong question: *what is the single most likely error?* The right question is *which logical class is most likely*, summed over all the errors inside it:

$$
\hat{L} = \arg\max_{L}\; P(L \mid s) \;=\; \arg\max_{L}\; \sum_{e \,\in\, L,\; e \,\vdash\, s} P(e)
$$

The sum runs over every error $e$ that is consistent with the observed syndrome $s$ and belongs to logical class $L$. Computing it exactly is **maximum-likelihood decoding (MLD)**. The tensor network is just the machine that evaluates that sum efficiently -- and because it is exact on the error model, it is never worse than MWPM or BP+OSD on the same model. It is the gold-standard reference decoder.

## Degeneracy, made visible

Take a 3-qubit repetition code. Two parity checks compare neighbouring qubits, and -- as in any real circuit -- each check can also *misreport* itself (a measurement error, labelled `m`). When **both** checks fire, syndrome `(1, 1)`, many distinct error patterns explain it: data flips, readout glitches, and combinations. They do not all agree on the logical outcome. Build the class sums by hand and watch which one wins.

**Class sums for syndrome (1,1)**

<SvelteIsland :component="DegeneracyPlay" />

*Every syndrome-consistent error pattern, with its probability and its logical class. Uncheck a row to drop it from the sum; the bars at the bottom are the running per-class totals, and the winner is their argmax -- exactly what the tensor network computes.*

Legend:

- class I -- no logical flip
- class L -- logical flip
- checkbox: include the row in the running sum

::: tip The summation IS the decoder
Degeneracy is not a nuisance to ignore; it is signal. A decoder that only ever inspects one error throws away the accumulated weight of every other error in the same class. Summing it back is the whole job, and on a 2-D surface code -- where a class can hold exponentially many medium-weight errors -- it is the difference between a working decoder and a failing one.
:::

## Tensors are a language for sums

To evaluate that sum over *all* errors without enumerating them one by one, we need a compact notation for "multiply these arrays and sum over a shared index". That notation is a **tensor network**.

A tensor is just a multi-index array; each index is a *leg*. A vector has one leg, a matrix has two. **Contraction** means summing over a leg shared by two tensors -- the generalized matrix product. Edit the entries below; the shared-leg sum (here over $k$) recomputes live.

**Contract two 2×2 tensors**

<SvelteIsland :component="TensorPlay" />

*Contracting two 2×2 tensors over their shared leg k. Hover a result cell to see exactly which products are summed. This single rule -- sum over shared legs -- scales to the whole decoder.*

Legend:

- row index i (open leg of A)
- column index j (open leg of B)
- cell value (warmer = larger)

Written as an equation, contracting tensors $A$ and $B$ over a shared leg $k$ is

$$
C_{ij} \;=\; \sum_{k} A_{ik}\,B_{kj},
$$

where the summed index $k$ disappears and the free indices $i,j$ become the legs of the result. The two factor tensors of the decoder are special cases of this rule. The **biased-copy** tensor carries the per-mechanism error prior, $\,\mathrm{copy}_{0\dots0}=1-p,\ \mathrm{copy}_{1\dots1}=p$, and 0 on every mixed corner; the **parity** (XOR / Kronecker-δ) tensor is $\,\delta(b_1\oplus\dots\oplus b_n = t)$, equal to 1 only when its leg bits XOR to the pinned target $t$.

::: details Worked example: A biased-copy passes through a parity δ-tensor (p = 0.15)

1. The biased-copy for one mechanism is the prior vector $\mathrm{copy}_k = [\,1-p,\; p\,] = [\,0.85,\; 0.15\,]$ on its shared leg $k$.
2. Send it through a parity δ-tensor $\delta(k \oplus j = t)$ with legs $k$ (shared) and $j$ (open). As a matrix this is $\delta_{t=0}=\bigl[\begin{smallmatrix}1&0\\0&1\end{smallmatrix}\bigr]$ when the detector reads $t=0$.
3. Contract over the shared leg: $C_j = \sum_k \mathrm{copy}_k\,\delta(k\oplus j = 0)$. Each output bit just reads the matching input bit, so $C = [\,0.85,\; 0.15\,]$ -- the prior survives unchanged.
4. Now flip the detector to $t=1$, i.e. $\delta_{t=1}=\bigl[\begin{smallmatrix}0&1\\1&0\end{smallmatrix}\bigr]$. The parity now forces $j = 1 \oplus k$, swapping the two entries: $C = [\,0.15,\; 0.85\,]$.

**Result.** Pinning a parity tensor to the measured syndrome bit **routes probability through the network**: target 0 leaves the prior alone, target 1 swaps it. Chain thousands of these and the contraction sums every error at once -- exactly what `decoder.ts` computes.
:::

::: info Why this is the same operation as the sum
Each leg carries a value in `{0, 1}` (a bit). Summing over a shared leg means "consider both bit values and add". Chain enough of these together and you have summed over every assignment of every bit -- every error configuration -- at once.
:::

## The factor graph for decoding

Now the real construction. We turn the error model into a network with three kinds of tensor, one factor each:

- **biased COPY** (round) -- one per error *mechanism*. It is the binary variable "did this error fire?", a COPY tensor with the prior folded in: $[\,1-p,\; p\,]$ on its all-zero / all-one corners, fanned to every leg the mechanism touches.
- **parity / XOR** (square) -- one per *detector*. It is $1$ exactly when the bits on its legs XOR to the *observed* syndrome bit, and $0$ otherwise. That is how the measurement pins the network.
- **observable** (triangle) -- a parity tensor with one *open* leg left dangling. After contraction that leg carries the predicted logical flip.

**Repetition-code factor graph**

<SvelteIsland :component="FactorGraphPlay" />

*A repetition-code decoding graph. Click a detector (square) to flip its observed syndrome bit -- the parity tensor re-pins to the new value. Mechanisms touching a lit detector are highlighted.*

Legend:

- biased-COPY tensor (mechanism, carries [1-p, p])
- parity tensor (detector, pinned to syndrome bit)
- lit detector (syndrome bit = 1)
- observable parity (triangle, open leg = predicted flip)
- leg / bond (shared index)
- leg touching a lit detector (highlighted)

## Contract = sum over everything

Contracting this network sums over every shared leg -- every error configuration -- and leaves a tiny tensor indexed only by the open observable legs: the **total probability weight of each logical class**. The argmax is the correction. We contract **greedily and pairwise**: at each step we merge the pair whose result has the fewest legs, keeping intermediates small. The order changes the cost but never the value.

Concretely, the full contraction of the network -- biased-copies $\mathrm{copy}$, syndrome-pinned parities $\delta_s$, and the observable parity with open leg $\ell$ -- evaluates exactly the coset sum, one number per logical class:

$$
W(\ell) \;=\; \sum_{e}\ \Bigl[\textstyle\prod_{m} \mathrm{copy}_m(e_m)\Bigr]\ \Bigl[\textstyle\prod_{d} \delta\!\bigl(\partial e|_d = s_d\bigr)\Bigr]\ \delta\!\bigl(\partial e|_{\mathrm{obs}} = \ell\bigr) \;=\; \sum_{e\,\in\,\ell,\ e\,\vdash\, s} P(e),
$$

where $e=(e_m)$ ranges over all mechanism on/off settings, the copy factors supply $P(e)=\prod_m p_m^{e_m}(1-p_m)^{1-e_m}$, the detector δ-factors kill every $e$ inconsistent with the syndrome $s$, and the open leg $\ell$ records the logical class. The decoder returns $\hat{L}=\arg\max_\ell W(\ell)$.

**Greedy pairwise contraction**

<SvelteIsland :component="ContractionPlay" />

*Scrub the greedy contraction of the live code above. Each step merges two tensors over their shared legs; the running 'tensors left' and 'largest intermediate' track the cost. The final tensor is the per-class weight.*

Legend:

- class I weight (no logical flip)
- class L weight (logical flip)
- lit detector button

::: tip This is exactly the qliff decoder
The numbers above come from the same algorithm as `MaxLikelihoodDecoder` in `qliff/qec/tn.py`: build the static tensors once, swap in the syndrome-pinned parity tensors per shot, contract to the open legs, argmax. Pairwise `tensordot` avoids the 52-symbol ceiling of a single whole-network einsum.
:::

## Why exact decoding gets expensive

Contraction is exact, but not free. An intermediate tensor with $k$ legs holds $2^k$ numbers. The largest such $k$ over the whole contraction is the network's **treewidth**, and it sets the cost. For a chain-like repetition code the width stays small, but for a 2-D surface code it grows with the distance -- and $2^k$ explodes.

**Cost vs code distance**

<SvelteIsland :component="CostChart" />

*The cost of summing over errors. Naïvely enumerating all 2^(#mechanisms) error patterns (grey) is hopeless. Greedy tensor contraction (purple) pays only the treewidth -- far smaller, but still exponential in the worst case. Note the log scale.*

Legend:

- brute force: enumerate all 2^(#mechanisms) errors
- TN treewidth: largest intermediate 2^k
- inspected distance d

So exact MLD is the right answer but only affordable up to small-to-mid distances. For anything larger we need to bound the intermediate size *without* abandoning the sum. That is the last idea.

## Bond truncation: trading accuracy for scale

The fix (Bravyi-Suchara-Vargo) is to cap the **bond dimension** χ. Before merging a pair whose shared bond would be huge, compress it: take a thin **singular-value decomposition** of the cut, keep only the χ largest singular values, and split the weight as $A = U\sqrt{S}$ and $B = \sqrt{S}\,V^{\dagger}$. The merged tensor then carries one bond of dimension $\le \chi$ instead of $2^{s}$.

**Bond singular-value spectrum**

<SvelteIsland :component="TruncationPlay" />

*The singular-value spectrum of one bond. Bars past the χ cutoff are dropped; the truncation error is the relative weight of that discarded tail. Slide χ up and the error falls to zero -- at full χ the contraction is bit-for-bit exact.*

Legend:

- kept singular value (k ≤ χ)
- dropped singular value (k > χ)
- χ cutoff (bond dimension)

The cut is a matrix $M$; its thin SVD is $M = \sum_{k} \sigma_k\, u_k v_k^{\dagger}$ with singular values $\sigma_1 \ge \sigma_2 \ge \dots \ge 0$. Keeping the top χ terms is the best rank-χ approximation (Eckart-Young), and the relative Frobenius error of dropping the tail is exactly

$$
\varepsilon(\chi) \;=\; \frac{\lVert M - M_\chi\rVert_F}{\lVert M\rVert_F} \;=\; \sqrt{\frac{\sum_{k>\chi}\sigma_k^2}{\sum_{k}\sigma_k^2}}\,,
$$

which is the percentage printed under the chart. At $\chi = r$ (full rank) the tail is empty and $\varepsilon = 0$.

::: details Worked example: Truncating one 8×8 bond -- which σₖ survive χ = 2?

1. The thin SVD of this bond (the matrix `svdTruncate` builds in `tensor.ts`) has the spectrum $\sigma = [\,4.243,\ 0.646,\ 0.234,\ 0.130,\ 0.106,\ 0.088,\ 0.077,\ 0.071\,]$.
2. Pick $\chi = 2$: keep $\sigma_1=4.243$ and $\sigma_2=0.646$; drop the remaining six $(0.234,\dots,0.071)$. The bond shrinks from dimension $8$ to $\chi = 2$.
3. Total weight $\sum_k \sigma_k^2 = 18.52$; kept weight $4.243^2 + 0.646^2 = 18.42$; discarded tail $\sum_{k>2}\sigma_k^2 = 0.102$.
4. Truncation error $\varepsilon = \sqrt{0.102 / 18.52} = \sqrt{0.00550} \approx 0.0741$.

**Result.** χ = 2 keeps just the top **2 of 8** singular values at a **7.41%** truncation error -- and the bond carries 2 numbers instead of 8. Raise χ to 3 and the error drops to 5.03%; at χ = 8 it is exactly 0 (bit-for-bit exact).
:::

::: tip The χ dial in one sentence
$\chi \to \infty$ is exact maximum-likelihood (no singular value dropped); finite $\chi$ is the best low-rank approximation of each cut -- bounded cost, controllable error. That single knob is what lets the reference decoder scale past where exact contraction dies.
:::

One last thread. Every tensor here held a real probability, but the exact same primitives -- biased copy, parity, contraction, SVD -- work with **complex** entries. Feed them signed *amplitudes* instead of probabilities and read $|\cdot|^2$ at the open legs, and you get the **coherent-noise decoder**: the one decoder family that survives non-Pauli errors like over-rotations and damping, which no probability-based decoder can represent. That is the next explainer.
