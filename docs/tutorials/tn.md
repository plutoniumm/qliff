---
title: Tensor-Network Decoder
outline: 2
---

# Tensor-Network Decoder <Badge type="info" text="Tutorial 04 of 7" />

> Sum over every error at once by contracting a network of small tensors: exact maximum likelihood.

<script setup>
import DegeneracyPlay from '../_tut/tn/DegeneracyPlay.svelte'
import TensorPlay from '../_tut/tn/TensorPlay.svelte'
import FactorGraphPlay from '../_tut/tn/FactorGraphPlay.svelte'
import ContractionPlay from '../_tut/tn/ContractionPlay.svelte'
import CostChart from '../_tut/tn/CostChart.svelte'
import TruncationPlay from '../_tut/tn/TruncationPlay.svelte'
</script>

## The right question to ask

A quantum code never tells you which physical errors happened. It hands you a **syndrome**: a short list of parity checks that came out odd. Your job is to guess a correction that undoes the error's effect on the encoded logical information. The catch:

::: tip Many errors, one syndrome, one logical effect
Different physical errors routinely produce the *same* syndrome, and often the *same* effect on the logical qubit. To rank the options correctly, do not pick the single most likely error; add up the probability of *every* error in each logical class.
:::

Matching (MWPM) and belief propagation answer a slightly wrong question: *what is the single most likely error?* The right question is *which logical class is most likely*, summed over all the errors inside it:

$$
\hat{L} = \arg\max_{L}\; P(L \mid s) \;=\; \arg\max_{L}\; \sum_{e \,\in\, L,\; e \,\vdash\, s} P(e)
$$

The sum runs over every error $e$ that is consistent with the observed syndrome $s$ and belongs to logical class $L$. Evaluating it exactly is **maximum-likelihood decoding (MLD)**. The tensor network is the machine that evaluates it, and because it is exact on the error model it is never worse than MWPM or BP+OSD on the same model.

## Degeneracy, made visible

Take a 3-qubit repetition code. Two parity checks compare neighbouring qubits, and each check can also *misreport* itself (a measurement error, labelled `m`), as checks on hardware do. When **both** checks fire, syndrome `(1, 1)`, many distinct error patterns explain it: data flips, readout glitches, and combinations. They do not all agree on the logical outcome. Build the class sums by hand and watch which one wins.

**Class sums for syndrome (1,1)**

<SvelteIsland :component="DegeneracyPlay" />

*Every syndrome-consistent error pattern, with its probability and its logical class. Uncheck a row to drop it from the sum; the bars at the bottom are the running per-class totals, and the winner is their argmax, which is what the tensor network computes.*

Legend:

- class I: no logical flip
- class L: logical flip
- checkbox: include the row in the running sum

::: tip The summation IS the decoder
A decoder that only inspects one error throws away the weight of every other error in the same class. Summing it back is the whole job. On a 2-D surface code, where a class can hold exponentially many medium-weight errors, that sum is the difference between a working decoder and a failing one.
:::

## Tensors are a language for sums

To evaluate that sum over *all* errors without listing them one by one, we need a compact notation for "multiply these arrays and sum over a shared index". That notation is a **tensor network**.

A tensor is a multi-index array; each index is a *leg*. A vector has one leg, a matrix has two. **Contraction** means summing over a leg shared by two tensors: the generalized matrix product. Edit the entries below; the shared-leg sum (here over $k$) recomputes live.

**Contract two 2x2 tensors**

<SvelteIsland :component="TensorPlay" />

*Contracting two 2x2 tensors over their shared leg k. Hover a result cell to see which products are summed. This single rule (sum over shared legs) is the only operation the decoder uses.*

Legend:

- row index i (open leg of A)
- column index j (open leg of B)
- cell value (warmer = larger)

Written as an equation, contracting tensors $A$ and $B$ over a shared leg $k$ is

$$
C_{ij} \;=\; \sum_{k} A_{ik}\,B_{kj},
$$

where the summed index $k$ disappears and the free indices $i,j$ become the legs of the result. In NumPy the same shared-leg sum is one `einsum` call, with one subscript letter per leg:

```python
import numpy as np

A = np.array([[1.0, 2.0], [3.0, 4.0]])
B = np.array([[5.0, 6.0], [7.0, 8.0]])
C = np.einsum("ik,kj->ij", A, B)  # sum over the shared leg k
print(np.array_equal(C, A @ B))  # -> True
```

::: info Why this is the same operation as the sum
In the decoder every leg carries a bit. Summing over a shared leg means "consider both bit values and add". Chain enough of these together and you have summed over every assignment of every bit, which is every error pattern, at once.
:::

That is the whole plan. What remains is to see which tensors to build, and the rest of the page does it on one tiny decoding problem, carried through to the production decoder.

## The running example

Take the repetition code from the degeneracy demo, but drop the measurement errors. What is left is the smallest problem that still decodes: three mechanisms, two checks, one shot.

**The setup.** A 3-bit repetition code stores one logical bit as `000` or `111`. Check 0 compares bits 0 and 1; check 1 compares bits 1 and 2. Three error mechanisms, one per bit, each fires independently with prior $p = 0.1$. The logical readout is the parity $b_0 \oplus b_1 \oplus b_2$ (0 for `000`, 1 for `111`), so every flip toggles it: an error pattern's logical class is its number of flips mod 2.

| mechanism | flips | lights | prior |
|---|---|---|---|
| $e_0$ | bit 0 | check 0 | 0.1 |
| $e_1$ | bit 1 | checks 0 and 1 | 0.1 |
| $e_2$ | bit 2 | check 1 | 0.1 |

**The shot.** We run once and measure the syndrome $s = 10$: check 0 fired, check 1 stayed quiet.

With only $2^3 = 8$ possible error patterns, brute force works: enumerate, keep the rows whose syndrome is 10, sum per class.

| pattern | $P(e)$ | syndrome | matches $s = 10$? | class |
|---|---|---|---|---|
| (none) | $0.9^3 = 0.729$ | 00 | no | I |
| $e_0$ | $0.1 \cdot 0.9^2 = 0.081$ | 10 | **yes** | L |
| $e_1$ | $0.081$ | 11 | no | L |
| $e_2$ | $0.081$ | 01 | no | L |
| $e_0 e_1$ | $0.1^2 \cdot 0.9 = 0.009$ | 01 | no | I |
| $e_0 e_2$ | $0.009$ | 11 | no | I |
| $e_1 e_2$ | $0.009$ | 10 | **yes** | I |
| $e_0 e_1 e_2$ | $0.1^3 = 0.001$ | 00 | no | L |

Two rows survive. The class sums are

$$
W(\mathrm{I}) = 0.009, \qquad W(\mathrm{L}) = 0.081,
$$

and the argmax says **class L**: report a logical flip, with posterior confidence $0.081 / (0.081 + 0.009) = 90\%$.

Hold on to those two numbers. Everything below is one machine, built three ways, whose output is this same pair of numbers without ever writing the 8-row table. That matters because the table has $2^{\#\text{mechanisms}}$ rows, and a distance-25 surface code has thousands of mechanisms.

## The network, tensor by tensor

The network for the running example has six tensors and nine legs. Every leg is a wire carrying one bit; a tensor entry is the number the tensor assigns to one setting of its legs' bits.

```
[e0]------(check 0)------[e1]------(check 1)------[e2]
  \          pin 1        |          pin 0          /
   \                      |                        /
    +-------------< observable parity >-----------+
                          |
                       open leg L
```

Three kinds of tensor appear.

**A biased-copy per mechanism** (the `[e]` nodes). Mechanism $e_0$ touches check 0 and the logical readout, so its tensor has two legs:

| leg to check 0 | leg to readout | value |
|---|---|---|
| 0 | 0 | 0.9 |
| 1 | 1 | 0.1 |
| 0 | 1 | 0 |
| 1 | 0 | 0 |

Read it as a statement: $e_0$ either did not fire (weight $1-p = 0.9$, both legs report 0) or fired (weight $p = 0.1$, both legs report 1). The zero entries forbid a mechanism from telling one neighbour it fired and another that it did not. $e_2$'s tensor is identical. $e_1$ touches both checks and the readout, so its copy has three legs: 0.9 at `000`, 0.1 at `111`, 0 at the other six entries.

**A parity tensor per check, pinned to the measured bit** (the `(check)` nodes). Check 0 read 1, so its tensor is 1 where its two legs XOR to 1 and 0 elsewhere:

| leg from $e_0$ | leg from $e_1$ | value |
|---|---|---|
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 0 | 0 | 0 |
| 1 | 1 | 0 |

A hard constraint: "exactly one of $e_0, e_1$ fired". Check 1 read 0, so its table is the complement, 1 at `00` and `11`, 0 at `01` and `10`: "$e_1$ and $e_2$ fired together or not at all".

**One observable parity with an open leg** (the `< >` node). Four legs: the three readout legs plus an open leg $L$ that no other tensor touches. Its entry is 1 when the four bits XOR to 0 (8 of its 16 entries), else 0. It forces $L = e_0 \oplus e_1 \oplus e_2$: the open leg carries the pattern's logical class.

Now pick any assignment of the nine bits and multiply the six tensor entries it selects. You get 0 if the assignment violates a copy or a pinned check, and $P(e)$ if it is a syndrome-consistent error pattern, tagged with its class on $L$. Summing that product over all assignments is the brute-force table, term for term. Contraction is a way to organize the sum so the table never materializes.

**The running example as a live network**

<SvelteIsland :component="FactorGraphPlay" />

*The network above, drawn live. It opens on the running example: 3 data qubits, p = 0.1, syndrome (1, 0). Click a check (square) to re-pin it to the other syndrome bit; mechanisms touching a fired check are highlighted. Slide the distance up to grow the chain.*

Legend:

- biased-copy tensor (mechanism, carries [1-p, p])
- parity tensor (check, pinned to its syndrome bit)
- fired check (syndrome bit = 1)
- observable parity (triangle, open leg = predicted flip)
- leg (shared index)
- leg touching a fired check (highlighted)

## Contract it by hand

To contract the network, repeatedly merge two tensors that share legs: multiply entries that agree on the shared bits, sum the shared bits away, keep the rest. Any merge order gives the same final tensor; order only changes the cost. Sweep the chain left to right. Three steps.

**Step 1: absorb $e_0$, check 0, and $e_1$.** Check 0's pin allows only "one of $e_0, e_1$ fired". Merging the two copies with the pinned parity (two pairwise merges) sums $e_0$'s bit away and leaves a tensor $T_1$ with three legs: $e_0$'s readout leg, $e_1$'s leg to check 1, and $e_1$'s readout leg. Its nonzero entries:

| $e_0$ readout | $e_1$ to check 1 | $e_1$ readout | value | reading |
|---|---|---|---|---|
| 0 | 1 | 1 | $0.9 \times 0.1 = 0.09$ | $e_1$ fired, $e_0$ did not |
| 1 | 0 | 0 | $0.1 \times 0.9 = 0.09$ | $e_0$ fired, $e_1$ did not |

The other six entries are 0. Two branches survive, tied at 0.09: each has one flip so far. Bit 2 will break the tie.

**Step 2: absorb check 1 and $e_2$.** Check 1's pin (target 0) forces $e_2 = e_1$. In the top branch $e_1$ fired, so $e_2$ must fire too: $0.09 \times 0.1 = 0.009$. In the bottom branch neither fires: $0.09 \times 0.9 = 0.081$. The result $T_2$ has the three readout legs:

| $e_0$ readout | $e_1$ readout | $e_2$ readout | value | pattern |
|---|---|---|---|---|
| 0 | 1 | 1 | 0.009 | $e_1 e_2$ |
| 1 | 0 | 0 | 0.081 | $e_0$ |

**Step 3: fold in the observable parity.** It XORs the three readout bits onto the open leg. The top row lands on $L = 0$, the bottom on $L = 1$:

$$
W \;=\; [\,W(\mathrm{I}),\ W(\mathrm{L})\,] \;=\; [\,0.009,\ 0.081\,].
$$

The brute-force pair, argmax class L, and no table anywhere. The six inconsistent patterns were never generated: the pinned checks zeroed them out branch by branch, and the class sums accumulated as the sweep moved. Bookkeeping: the biggest tensor the sweep built was $T_1$ with $2^3 = 8$ numbers, and the biggest it ever held was the 16-entry observable parity.

In symbols, the sweep evaluated the coset sum from the top of the page, one number per class:

$$
W(\ell) \;=\; \sum_{e_0, e_1, e_2} \prod_{m} \mathrm{copy}_m(e_m)\ \prod_{d} \delta\!\bigl(\partial e|_d = s_d\bigr)\ \delta\!\bigl(e_0 \oplus e_1 \oplus e_2 = \ell\bigr) \;=\; \sum_{e\,\in\,\ell,\ e\,\vdash\, s} P(e),
$$

where $\partial e|_d$ is the parity that pattern $e$ throws on check $d$. The copy factors supply $P(e)$, the pinned checks kill every pattern with the wrong syndrome, and the observable delta files each survivor under its class $\ell$.

**Contraction of the running example, step by step**

<SvelteIsland :component="ContractionPlay" />

*The same network, contracted by machine. It opens on the running example; scrub through the merges. The decoder picks a greedy order (cheapest merge first) rather than the left-to-right sweep, and lands on the same weights: 9.000e-3 and 8.100e-2. Re-pin the checks or grow the chain to decode other shots.*

Legend:

- class I weight (no logical flip)
- class L weight (logical flip)
- fired check button

::: tip This is the qliff decoder
`MaxLikelihoodDecoder` in `qliff/qec/tn.py` runs this loop: build the copy and observable tensors once per error model, swap in the pinned check tensors per shot, contract pairwise, argmax the final tensor. Pairwise `tensordot` merges also dodge the 52-subscript ceiling of a single whole-network einsum.
:::

## Why exact decoding gets expensive

A tensor with $k$ legs holds $2^k$ numbers. In the sweep above the working tensor never grew past 3 legs, and that stays true for a repetition chain of any length: the boundary between "absorbed" and "not yet absorbed" always cuts the same two or three legs. Cost grows linearly with chain length, which is why the demo above is instant.

Now tile the mechanisms in two dimensions, as a $d \times d$ surface code does. Whatever the merge order, at some point the boundary between absorbed and not-yet has to cut across the lattice: about $d$ legs at once, so the working tensor holds about $2^d$ numbers.

| network | legs on the widest cut | working tensor |
|---|---|---|
| repetition chain, any length | 2-3 | 8 numbers |
| surface code $5 \times 5$ | ~5 | 32 numbers |
| surface code $11 \times 11$ | ~11 | 2,048 numbers |
| surface code $25 \times 25$ | ~25 | 33,554,432 numbers |

The smallest achievable "widest cut" over all merge orders is the network's **treewidth**. Chains have constant treewidth; 2-D grids have treewidth proportional to $d$. Exact contraction pays $2^{\text{treewidth}}$: far better than the $2^{\#\text{mechanisms}}$ table, but still exponential in the distance.

**Cost vs code distance**

<SvelteIsland :component="CostChart" />

*Cost on the repetition chain: the largest intermediate (purple) stays flat as the chain grows, while brute-force enumeration (grey) doubles with every added mechanism. Log scale. For a 2-D code the purple curve would climb exponentially too, with exponent ~d instead of #mechanisms.*

Legend:

- brute force: enumerate all 2^(#mechanisms) errors
- TN cost: largest intermediate 2^k
- inspected distance d

So exact MLD is affordable at small distance and hopeless at large distance, unless the intermediates can be kept small without abandoning the sum. They can, approximately.

## Bond truncation: the chi dial

Freeze the contraction just before a merge. The two tensors about to merge meet at $s$ shared legs: a **bond** of size $2^s$. Flatten each side into a matrix with the bond as the inner index; their product $M = AB$ is everything the pair contributes to the rest of the contraction. Take its thin SVD, $M = \sum_k \sigma_k\, u_k v_k^{\dagger}$ with $\sigma_1 \ge \sigma_2 \ge \dots \ge 0$, keep only the $\chi$ largest singular values, and hand $U\sqrt{S}$ back to one side and $\sqrt{S}\,V^{\dagger}$ to the other. The pair is now joined by one bond of size $\chi$ instead of $2^s$. This is Bravyi-Suchara-Vargo truncation, and $\chi$ is the **bond dimension**.

- **What $\chi$ buys.** Cuts stop growing exponentially: a boundary that held $2^k$ numbers is carried in pieces joined by $\chi$-sized bonds, on the order of $\chi \cdot k$ numbers. For the $d = 25$ cut that is thousands of numbers instead of $2^{25}$.
- **What $\chi$ costs.** The discarded tail. Keeping the top $\chi$ terms is the best rank-$\chi$ approximation of $M$ (Eckart-Young), and the relative error is the weight of what was dropped:

$$
\varepsilon(\chi) \;=\; \frac{\lVert M - M_\chi\rVert_F}{\lVert M\rVert_F} \;=\; \sqrt{\frac{\sum_{k>\chi}\sigma_k^2}{\sum_{k}\sigma_k^2}}\,.
$$

At low noise the spectrum decays fast: the no-error branch and a few light perturbations carry most of the weight, so a small $\chi$ discards little.

**Bond singular-value spectrum**

<SvelteIsland :component="TruncationPlay" />

*One 8x8 bond and its singular values. Bars past the χ cutoff are dropped; the readout prints the truncation error ε(χ). Slide χ up and the error falls; at full χ nothing is dropped and the result is the exact contraction.*

Legend:

- kept singular value (k ≤ χ)
- dropped singular value (k > χ)
- χ cutoff (bond dimension)

::: details Worked example: which σₖ of an 8x8 bond survive χ = 2?

1. The thin SVD of this bond (the matrix `svdTruncate` builds in `tensor.ts`) has the spectrum $\sigma = [\,4.243,\ 0.646,\ 0.234,\ 0.130,\ 0.106,\ 0.088,\ 0.077,\ 0.071\,]$.
2. Pick $\chi = 2$: keep $\sigma_1=4.243$ and $\sigma_2=0.646$; drop the remaining six $(0.234,\dots,0.071)$. The bond shrinks from dimension 8 to 2.
3. Total weight $\sum_k \sigma_k^2 = 18.52$; kept weight $4.243^2 + 0.646^2 = 18.42$; discarded tail $\sum_{k>2}\sigma_k^2 = 0.102$.
4. Truncation error $\varepsilon = \sqrt{0.102 / 18.52} = \sqrt{0.00550} \approx 0.0741$.

**Result.** χ = 2 keeps the top **2 of 8** singular values at a **7.41%** truncation error, and the bond carries 2 numbers instead of 8. Raise χ to 3 and the error drops to 5.03%; at χ = 8 it is 0 and the contraction is the exact one.
:::

::: tip The χ dial in one sentence
$\chi \to \infty$ is exact maximum likelihood (nothing dropped); finite $\chi$ is the best rank-$\chi$ approximation of every cut: bounded cost, measurable error, one knob.
:::

For the running example the dial changes nothing: its bonds are already tiny, and a capped contraction returns the same $[\,0.009,\ 0.081\,]$. Which brings the toy back to the library.

## The toy is the production decoder

`MaxLikelihoodDecoder` builds this construction from any `DetectorErrorModel`: one `biased_copy(degree, p)` per mechanism, one `parity(degree, s_d)` per detector (the DEM's name for a check), one open-legged parity per observable, greedy pairwise `contract`. A one-round distance-3 repetition circuit compiles to the running example's error model, and decoding our shot returns the class computed by hand:

```python
import numpy as np

from qliff.qec import repetition_code
from qliff.qec.tn import MaxLikelihoodDecoder

# one noisy round of the distance-3 repetition code: its DEM is the
# running example's three mechanisms.
circuit = repetition_code(distance=3, rounds=1, p=0.1, channel="X_ERROR")
dem = circuit.dem()

for prior, dets, flips in dem.mechanisms:
    print(prior, sorted(dets), sorted(flips))
# -> 0.1 [0] [0]
# -> 0.1 [0, 1] [0]
# -> 0.1 [1] [0]

# decode the shot s = 10. (The circuit DEM also has two end-of-run
# detectors, 2 and 3, that no mechanism touches; their bits stay 0.)
decoder = MaxLikelihoodDecoder(dem)  # registered as "mld" and "tn"
shot = np.zeros((1, dem.num_detectors), dtype=np.uint8)
shot[0, 0] = 1
print(decoder.decode_batch(shot))  # -> [[1]] (class L, as computed by hand)

# the chi dial: cap every bond at 2. Same answer on this small network.
capped = MaxLikelihoodDecoder(dem, max_bond=2)
print(capped.decode_batch(shot))  # -> [[1]]
```

`max_bond` is the $\chi$ dial from the previous section; `max_bond=None` (the default) is the exact contraction. On this network capping changes nothing; on a large one it is the difference between decoding and running out of memory.

## Implementation {#implementation}

The decoder fits in a page. Three views of the same algorithm: language-neutral pseudocode, a NumPy version of the running example that reproduces every number in the prose, and the qliff pipeline.

**Pseudocode.** Build the network once per error model; per shot only the detector pins change. The contraction order affects cost, never the value.

**Std Python.** The running example twice: brute force over all $2^3$ patterns, then the three-step einsum sweep from the prose. The intermediates `t1` and `t2` match the step tables, and both routes end at `[0.009 0.081]` with argmax class L. A whole-network einsum hits NumPy's 52-subscript ceiling on bigger models, which is why the production decoder merges pairwise with `tensordot` instead.

**Qliff.** The same network with the library primitives (legs are hashable labels instead of einsum letters), then the pipeline at scale: circuit to detector error model to sampled shots to decode, with a χ-capped decoder matching the exact one shot for shot.

::: code-group

```text [Pseudocode]
MLD-DECODE(error model, syndrome s):
  # 1. error-probability tensors: one binary variable per mechanism
  for each mechanism m with prior p_m, detectors D_m, observables O_m:
      T[m] <- biased-copy tensor with one leg per member of D_m and O_m
              (weight 1-p_m on the all-zero corner, p_m on the all-one corner)

  # 2. wire the tensors together by parity constraint
  for each detector d:
      P[d] <- parity tensor over the legs of mechanisms touching d,
              pinned to the observed syndrome bit s_d
  for each observable o:
      Q[o] <- parity tensor over the legs of mechanisms flipping o,
              plus one OPEN leg carrying o's predicted flip

  # 3. contract in a chosen order (greedy pairwise here)
  network <- all T[m], P[d], Q[o]
  while network has more than one tensor:
      pick the sharing pair whose merged tensor has the fewest legs
      optional: SVD-truncate their shared bond to chi   # Bravyi-Suchara-Vargo
      replace the pair by their tensordot over the shared legs

  # 4. read off coset probabilities and pick the likelier logical class
  W <- final tensor, indexed by the open observable legs
  return argmax over L of W(L)
```

```python [Std Python]
from itertools import product

import numpy as np

# the running example: 3-bit repetition code, three mechanisms with prior
# p = 0.1, measured syndrome s = 10 (check 0 fired, check 1 quiet).
p = 0.1
detectors = [{0}, {0, 1}, {1}]  # checks lit by e0, e1, e2
syndrome = (1, 0)

# brute-force MLD: walk all 2^3 patterns, keep the consistent ones,
# sum P(e) per logical class (class = number of flips mod 2).
weights = np.zeros(2)  # index 0 = class I, index 1 = class L

for bits in product((0, 1), repeat=3):
    lit = set()
    prob = 1.0

    for on, dd in zip(bits, detectors):
        prob = prob * (p if on == 1 else 1.0 - p)
        if on == 1:
            lit = lit ^ dd

    hit = tuple(1 if d in lit else 0 for d in (0, 1))
    if hit == syndrome:
        weights[sum(bits) % 2] += prob

print(weights)  # -> [0.009 0.081]


# the same two numbers by contraction. Build the six factor tensors...
def biased_copy(degree, prior):
    t = np.zeros((2,) * degree)
    t[(0,) * degree] = 1.0 - prior
    t[(1,) * degree] = prior

    return t


def parity(degree, target):
    t = np.zeros((2,) * degree)

    for idx in np.ndindex(*t.shape):
        if sum(idx) % 2 == target:
            t[idx] = 1.0

    return t


# ...one einsum letter per leg:
#   a = e0-check0   b = e0-readout   c = e1-check0   d = e1-check1
#   e = e1-readout  f = e2-check1    g = e2-readout  L = open class leg
e0 = biased_copy(2, p)  # legs a, b
e1 = biased_copy(3, p)  # legs c, d, e
e2 = biased_copy(2, p)  # legs f, g
c0 = parity(2, 1)  # legs a, c (pinned to s0 = 1)
c1 = parity(2, 0)  # legs d, f (pinned to s1 = 0)
obs = parity(4, 0)  # legs b, e, g, L

# step 1: absorb e0, check 0, e1 -> T1 with legs b, d, e
t1 = np.einsum("ab,ac,cde->bde", e0, c0, e1)
print(t1[0, 1, 1].round(3), t1[1, 0, 0].round(3))  # -> 0.09 0.09

# step 2: absorb check 1 and e2 -> T2 with legs b, e, g
t2 = np.einsum("bde,df,fg->beg", t1, c1, e2)
print(t2[0, 1, 1].round(3), t2[1, 0, 0].round(3))  # -> 0.009 0.081

# step 3: the observable parity folds b, e, g into the open class leg L
W = np.einsum("beg,begL->L", t2, obs)
print(W)  # -> [0.009 0.081]
print(np.allclose(W, weights))  # -> True
print(int(np.argmax(W)))  # -> 1 (class L: report a logical flip)
```

```python [Qliff]
import numpy as np

from qliff.qec import repetition_code
from qliff.qec.tn import MaxLikelihoodDecoder, Tensor, biased_copy, contract, parity

# the running example with the library primitives. Legs are hashable labels;
# contract() sums away every leg not listed as open.
p = 0.1
network = [
    Tensor(biased_copy(2, p), ("q0-c0", "q0-obs")),
    Tensor(biased_copy(3, p), ("q1-c0", "q1-c1", "q1-obs")),
    Tensor(biased_copy(2, p), ("q2-c1", "q2-obs")),
    Tensor(parity(2, 1), ("q0-c0", "q1-c0")),  # check 0, pinned to 1
    Tensor(parity(2, 0), ("q1-c1", "q2-c1")),  # check 1, pinned to 0
    Tensor(parity(4, 0), ("q0-obs", "q1-obs", "q2-obs", "class")),  # open leg
]
print(contract(network, ["class"]).data)  # -> [0.009 0.081]

# at scale: two noisy rounds, sampled shots, logical error rate.
circuit = repetition_code(distance=3, rounds=2, p=0.05, channel="X_ERROR")
dem = circuit.dem()
print(dem.num_detectors, dem.num_observables, len(dem.mechanisms))  # -> 6 1 6

decoder = MaxLikelihoodDecoder(dem)
dets, obs = circuit.detector_sampler().sample(400, seed=7)
preds = decoder.decode_batch(dets)
print(float(np.mean(np.any(preds != obs, axis=1))))  # logical error rate -> 0.0125

# the capped decoder (chi = 4) decodes all 400 shots identically.
capped = MaxLikelihoodDecoder(dem, max_bond=4)
print(bool(np.array_equal(capped.decode_batch(dets), preds)))  # -> True
```

:::

One last thread. Every tensor here held a probability, but the same primitives (biased copy, parity, contraction, SVD) accept **complex** entries. Feed them signed *amplitudes* instead of probabilities and read $|\cdot|^2$ at the open legs, and you get the **coherent-noise decoder**: the one decoder family that survives non-Pauli errors like over-rotations and damping, which no probability-based decoder can represent. That is the next explainer.
