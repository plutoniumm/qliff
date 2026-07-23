---
title: Belief Propagation
outline: 2
---

# Belief Propagation <Badge type="info" text="Tutorial 03 of 10" />

<script setup>
import TannerDemo from '../_tut/bp/TannerDemo.svelte'
import PriorGauge from '../_tut/bp/PriorGauge.svelte'
import DanceDemo from '../_tut/bp/DanceDemo.svelte'
import BeliefsDemo from '../_tut/bp/BeliefsDemo.svelte'
import StuckDemo from '../_tut/bp/StuckDemo.svelte'
</script>

## Why another decoder?

In the previous chapter, **minimum-weight perfect matching** turned a syndrome into a graph and paired up the lit detectors. That trick only works when every possible error touches *at most two* detectors: each error is then an *edge* and decoding is graph matching.

But most codes aren't so tidy. A single fault can flip three, four, or a dozen parity checks at once. Now an error is no longer an edge: it's a node wired to all the checks it disturbs. Matching has nothing to match. We need a decoder that lives on the *full bipartite graph* of errors and checks.

::: tip The one-line intuition
**Belief propagation is neighbours gossiping until they agree.** Every possible error and every parity check holds an opinion ("I probably did/didn't fire", "my parity is/isn't satisfied") and they trade these opinions back and forth along the edges. After a few rounds, the opinions (hopefully) settle on the single most likely error.
:::

This is what qliff's `BpOsdDecoder` does. It hands the code's check matrix to belief propagation and, when BP can't decide, to a cleanup step called **OSD**. By the end of this page you'll have run both, live, on an example where plain matching does not apply.

## The Tanner graph

Everything BP does happens on one picture: the **Tanner graph** (a "factor graph"). It has two kinds of node:

- **Variables** (circles, top): one per *error mechanism*, a possible fault like "qubit 3 picked up an X."
- **Checks** (squares, bottom): one per *detector*, a parity measurement that lights up if an odd number of its neighbouring errors fired.

We draw an edge from error $e_m$ to detector $d_c$ exactly when $H_{cm}=1$, i.e. when mechanism $m$ flips detector $c$. That matrix $H$ is the same one qliff builds from the circuit (`dem.check_matrix()` returns $H$, the priors, and the observable map).

Click a detector to "light" it: the lit pattern is a **syndrome**, the only thing the decoder observes. The readout under the graph then does the decoder's whole job by brute force: it tests all $2^5 = 32$ subsets of mechanisms against $H\,e = s$, keeps the consistent ones, and ranks them by probability. Hover any node to see who it talks to.

**Tanner graph**

<SvelteIsland :component="TannerDemo" />

Legend:
- circle = error mechanism
- square = detector
- lit square = syndrome bit 1
- edge = mechanism flips detector
- highlighted row = likeliest explanation

Two things to notice. Light all three detectors and the top of the list becomes a *tie*: two explanations with the same weight, hence the same probability. That is **degeneracy**, and it returns later as the thing that traps BP. Second, the brute-force ranking only works because this toy has 32 candidates; a real code has thousands of mechanisms and $2^{\text{thousands}}$ subsets. BP exists to find the same winner without enumerating them.

::: info Contrast with matching
Detector $d_1$ here touches *three* error mechanisms. Matching cannot handle it. BP doesn't care how many edges a node has; it keeps gossiping along all of them.
:::

## Beliefs as log-odds

Before any gossip, each error mechanism has a **prior**: the channel probability $p$ that it fired. BP doesn't pass probabilities around directly; it passes their **log-likelihood ratio** (LLR):

$$
\ell = \log\frac{1-p}{p} = \log\frac{P(\text{no error})}{P(\text{error})}.
$$

Why log-odds? Because along the way BP needs to *combine independent evidence*, and in log-space combining evidence is **addition**. The sign and size carry all the meaning:

- $\ell \gg 0$: confident there's **no error** (small $p$).
- $\ell \approx 0$: a coin flip; the mechanism is undecided.
- $\ell < 0$: the evidence now favours an **error**.

Two lines of numpy compute it; note $p=0.06$, the prior used by this page's repetition-code demos:

```python
import numpy as np

p = np.array([0.5, 0.1, 0.06, 0.01])
print(np.round(np.log((1 - p) / p), 3))
# -> [0.    2.197 2.752 4.595]
```

**Prior p -> LLR**

<SvelteIsland :component="PriorGauge" />

Legend:
- $\ell < 0$ = favours error
- $\ell > 0$ = favours no error

::: tip Posterior, the other direction
After gossiping, BP has a *posterior* LLR per mechanism. Convert back with $p = \tfrac{1}{1+e^{\ell}}$. The hard decision is a threshold at zero: declare an error whenever the posterior LLR goes **negative**.
:::

## The message-passing loop

Now the gossip itself. A **message** is a single number: a log-odds opinion about one mechanism, sent along one edge of the Tanner graph. Each iteration has two half-steps. First every mechanism tells each of its detectors how likely it currently is to have fired; then every detector replies with what its measured parity says about that mechanism. One rule governs both directions: a node talking to a neighbour sums up everything it heard *except* what that neighbour itself said, so no opinion is echoed back to its source and double-counted as fresh evidence. Repeat until the numbers stop changing.

Here are the two half-steps as update rules; the demo underneath runs them live on a 7-bit repetition code where a true error sits on one bit (cyan ring) and only the lit detectors are observed.

**Variable -> check.** A mechanism tells each neighbouring detector its log-odds, *using its prior plus what every* other *detector told it* (never echoing a check's own message back):

$$
m_{m\to c} \;=\; \ell_m \;+\!\!\sum_{c'\neq c} m_{c'\to m}.
$$

**Check -> variable** is the harder update. A detector enforces a parity constraint, and the exact rule for combining log-odds through an XOR is the **tanh rule**:

$$
\tanh\frac{m_{c\to m}}{2} \;=\; (-1)^{s_c}\!\!\prod_{m'\neq m}\tanh\frac{m_{m'\to c}}{2},
$$

where $s_c$ is that detector's syndrome bit (a lit detector flips the sign, pushing its neighbours toward *disagreeing*). Solving for the outgoing message gives the rule the demo's `bp.ts` evaluates:

$$
m_{c\to m} \;=\; 2\,\mathrm{atanh}\!\Big[(-1)^{s_c}\!\!\prod_{m'\neq m}\tanh\tfrac{m_{m'\to c}}{2}\Big].
$$

This is `bp_method="product_sum"`: sum-product BP in the log domain.

::: details One check -> variable message by hand
Take an unlit detector $s_c = 0$ with three neighbours sending in messages $m_{1\to c}=1.2$, $m_{2\to c}=-0.8$, $m_{3\to c}=2.0$. What does it tell neighbour 1?

1. Drop the back-edge: combine only the *other* two, $m_{2\to c}$ and $m_{3\to c}$.
2. Take $\tanh(m/2)$ of each: $\tanh(-0.4)=-0.3799$, $\tanh(1.0)=0.7616$.
3. Multiply (the check is unlit, so the sign is $+1$): $(-0.3799)(0.7616)=-0.2894$.
4. Invert: $m_{c\to 1}=2\,\mathrm{atanh}(-0.2894)=-0.5958$.

**Result:** The outgoing message is **-0.60**: *negative*, so this detector nudges neighbour 1 toward "you fired," but only weakly (small magnitude) because the -0.8 message was itself unsure. Had the detector been *lit* ($s_c=1$), the sign flips and it would instead send **+0.5958**.
:::

**Message passing**

<SvelteIsland :component="DanceDemo" />

Legend:
- dot = live message (size/heat = |LLR|)
- belief ring = posterior P(error)
- cyan ring = true error mechanism
- red ring/label = called an error

Iteration **0** shows the priors alone: every belief is the same positive number. As messages flow, the detectors next to the true error report strong evidence of a flip, and the beliefs of the mechanisms between two lit detectors collapse toward error.

## Reading the answer

Once the messages stop changing, BP *converged*. Each mechanism's **posterior LLR** sums its prior and *all* incoming check messages (no back-edge dropped this time); thresholding at zero gives the hard decision $\hat e$:

$$
L_m \;=\; \ell_m + \sum_{c} m_{c\to m}, \qquad \hat e_m = \begin{cases}1 & L_m < 0\\ 0 & L_m \ge 0\end{cases}
$$

The self-consistency check: feed $\hat e$ back through $H$ and confirm it reproduces the syndrome we started with.

::: details One mechanism's posterior and hard decision
A mechanism with prior $p=0.06$ (so $\ell = \log\frac{0.94}{0.06} = 2.752$) sits between two lit detectors that now send it strong "error" messages $-2.0$ and $-1.6$.

1. Sum prior + all incoming: $L = 2.752 + (-2.0) + (-1.6) = -0.848$.
2. Convert to a probability: $p = \tfrac{1}{1+e^{L}} = \tfrac{1}{1+e^{-0.848}} = 0.70$.
3. Threshold: $L < 0$, so the hard decision is $\hat e = 1$.

**Result:** The two detectors *outvoted* the prior: a mechanism that started 94% safe is now called an **error** ($P \approx 0.70$). One lukewarm prior is no match for two confident neighbours; that is evidence adding up in log-space.
:::

**Posterior beliefs**

<SvelteIsland :component="BeliefsDemo" />

Legend:
- bar left = error ($\ell < 0$)
- bar right = no error ($\ell > 0$)
- cyan label = true mechanism

The recovered mechanism vector then maps through the observable matrix ($\text{obs} = O\,\hat{e} \bmod 2$) to say which *logical* observables flipped, which is the output qliff hands back. Try moving the true error around in the panel above; for the repetition code, BP recovers it every time.

::: info The easy case
The repetition code is *graphlike* and loop-free near a single error, so BP settles on the answer without trouble. Next we construct a case where it cannot.
:::

## When BP gets stuck

Quantum codes are **degenerate**: distinct errors can have identical syndromes and identical likelihoods. When the graph also has short cycles, BP's "independent evidence" assumption breaks, and the beliefs can **oscillate forever**, never committing to an answer.

Here's a tiny hand-built code that traps it. Detector $d_0$ touches all four mechanisms; $d_1$ and $d_2$ each pair two of them. The syndrome lights $d_0,d_1$; the obvious fix is mechanism $e_0$ alone. But the symmetry leaves mechanisms $e_0$ and $e_1$ tied. Step through the iterations below.

**Degenerate trap**

<SvelteIsland :component="StuckDemo" />

Legend:
- lit check = syndrome bit 1
- unsatisfied check = residual 1
- oscillating belief ring = BP never decides

::: warning The symmetric trap
Notice that $e_0$ and $e_1$ always carry the *identical* posterior, and that it keeps flipping sign. BP has split its belief symmetrically between two indistinguishable stories and can't break the tie. No number of extra iterations helps. This is the failure mode that defeats plain BP on practical quantum codes (colour codes, surface codes with short cycles).
:::

## OSD to the rescue

**BP proposes, OSD disposes.** Ordered-statistics decoding doesn't throw away BP's work: it uses BP's soft output to make a *decisive* guess. qliff runs `osd_method="osd_cs"` with `osd_order=7`. The recipe:

1. **Order by reliability.** Sort the mechanisms by $|L_m|$, most confident first. Even when BP can't decide *between* $e_0$ and $e_1$, it *is* sure that $e_2,e_3$ stayed quiet.
2. **Solve a full-rank core exactly.** Walk that ordered list and Gaussian-eliminate over $\mathbb{F}_2$ to pull out a most-reliable set of independent pivot columns $\mathcal{P}$, then solve that square subsystem $H_{\mathcal{P}}\,\hat e_{\mathcal{P}} \;=\; s \pmod 2$ (free columns set to 0). This forces a recovery that reproduces the syndrome; the oscillation is gone.
3. **Search small corrections (order 7).** Flip up to $7$ of the least-reliable free columns, re-solve, and keep the *lowest-weight* consistent answer found.

<div class="qtut">
<figure class="q-fig">
  <div class="q-fig-title">BP + OSD</div>
  <p><strong>Step 1: reliability order.</strong> Columns most-reliable-first; bar length is the posterior reliability |L| (heat-capped at 5). BP is sure e2, e3 stayed quiet but cannot break the e0/e1 tie.</p>
  <ul class="q-bars">
    <li style="--v:.91;--c:var(--x)"><b>e2 <span class="q-chip" style="--c:var(--accent)">pivot</span></b><span class="q-track"></span><i>4.56</i></li>
    <li style="--v:.91;--c:var(--x)"><b>e3 <span class="q-chip" style="--c:var(--muted)">free</span></b><span class="q-track"></span><i>4.56</i></li>
    <li style="--v:.17;--c:var(--z)"><b>e0 <span class="q-chip" style="--c:var(--accent)">pivot</span></b><span class="q-track"></span><i>0.83</i></li>
    <li style="--v:.17;--c:var(--z)"><b>e1 <span class="q-chip" style="--c:var(--muted)">free</span></b><span class="q-track"></span><i>0.83</i></li>
  </ul>
  <p><strong>Step 2: solved recovery.</strong> Solve the pivot core exactly (free columns = 0), then search order-7 flips of the least-reliable free columns.</p>
  <p>order-0 (free = 0): <code>1000</code>, weight 1</p>
  <p>after order-7 search: <code>1000</code>, weight 1</p>
  <p><span class="q-chip" style="--c:var(--ok)">reproduces syndrome 110</span> BP + OSD recovers <code>e0</code> where plain BP spun forever.</p>
  <ul class="q-legend">
    <li style="--c:var(--accent)">pivot column (solved exactly)</li>
    <li style="--c:var(--muted)">free column</li>
    <li style="--c:var(--ok)">syndrome-matching recovery</li>
  </ul>
  <div class="q-fig-note">OSD applied to BP's stuck output. Columns are listed most-reliable-first; the pivot core is solved exactly to force a syndrome-matching recovery.</div>
</figure>
</div>

::: tip Why qliff ships BP+OSD
OSD turns BP's *almost-an-answer* into a guaranteed syndrome-consistent, low-weight recovery. BP+OSD works on the **general bipartite graph**, including *non-graphlike* codes (colour codes, dense LDPC) where a detector touches more than two errors and MWPM has no graph to match. That generality is why it sits alongside matching in qliff's decoder set.
:::

## Implementation {#implementation}

The demos above run sum-product BP in the browser; the same algorithm fits in a page of Python. The tabs below give three levels: pseudocode for the message schedule, a numpy version you can modify, and the production decoder qliff ships.

**Pseudocode.** One BP decode is an initialise / iterate / read-out loop over the Tanner graph. Everything lives on the edges where $H_{cm} = 1$.

**Std Python.** The same loop in numpy, run first on the 7-bit repetition code from the message-passing demo (true error on bit 3), then on the degenerate trap. The trap's transcript shows the split beliefs: $e_0$ and $e_1$ carry identical posteriors whose sign flips every iteration, so the hard decision alternates between `1100` and `0000`. An order-0 OSD step then breaks the tie as the figure above walks through, because the reliability *ranking* is stable even though the signs never settle.

**Qliff.** `BpOsdDecoder` wraps the `ldpc` library's BP+OSD (`bp_method="product_sum"`, `osd_method="osd_cs"`, `osd_order=7`) behind qliff's batch decoder interface; `make_decoder("bposd", dem)` builds the same object by name. The colour-code memory below has weight-6 checks, so single faults flip three detectors: MWPM refuses the model outright while BP+OSD decodes it.

::: code-group

```text [Pseudocode]
BP(H, priors, syndrome, max_iter):
    for each mechanism m:                        # initialise from the priors
        llr[m] = log((1 - priors[m]) / priors[m])
        msg_v2c[m -> c] = llr[m]          for every check c with H[c, m] = 1

    for iter in 1 .. max_iter:
        for each check c:                        # check -> variable (tanh rule)
            sign = -1 if syndrome[c] = 1 else +1
            msg_c2v[c -> m] = 2 * atanh(sign * product over m' != m
                                        of tanh(msg_v2c[m' -> c] / 2))

        for each mechanism m:                    # variable -> check
            msg_v2c[m -> c] = llr[m] + sum over c' != c of msg_c2v[c' -> m]

        for each mechanism m:                    # marginals + hard decision
            L[m] = llr[m] + sum over all c of msg_c2v[c -> m]
            e_hat[m] = 1 if L[m] < 0 else 0

        if H @ e_hat = syndrome (mod 2):         # converged: stop
            return e_hat

    return e_hat                                 # stuck: hand L to OSD
```

```python [Std Python]
import numpy as np


def run_bp(H, priors, syndrome, iters):
    """Log-domain sum-product BP; returns the posterior LLRs after each iteration."""
    n_checks, n_vars = H.shape
    prior_llr = np.log((1.0 - priors) / priors)

    # messages live on the edges of the Tanner graph (where H[c, m] == 1)
    var_to_check = np.where(H == 1, prior_llr[np.newaxis, :], 0.0)
    check_to_var = np.zeros((n_checks, n_vars))
    history = []

    for _ in range(iters):
        # check -> variable: the tanh rule, sign flipped by lit detectors
        for c in range(n_checks):
            sign = -1.0 if syndrome[c] == 1 else 1.0
            for m in range(n_vars):
                if H[c, m] == 0:
                    continue
                prod = sign
                for m2 in range(n_vars):
                    if H[c, m2] == 1 and m2 != m:
                        prod = prod * np.tanh(var_to_check[c, m2] / 2.0)
                prod = np.clip(prod, -1.0 + 1e-12, 1.0 - 1e-12)
                check_to_var[c, m] = 2.0 * np.arctanh(prod)

        # variable -> check: prior plus every OTHER check's message
        posterior = prior_llr + check_to_var.sum(axis=0)
        var_to_check = np.where(H == 1, posterior[np.newaxis, :] - check_to_var, 0.0)
        history.append(posterior)

    return history


# the 7-bit repetition code from the demo: check c compares bits c and c+1
n = 7
H_rep = np.zeros((n - 1, n), dtype=np.uint8)
for c in range(n - 1):
    H_rep[c, c] = 1
    H_rep[c, c + 1] = 1

priors = np.full(n, 0.06)
true_error = np.array([0, 0, 0, 1, 0, 0, 0], dtype=np.uint8)
syndrome = (H_rep @ true_error) % 2
print(syndrome)  # -> [0 0 1 1 0 0]

history = run_bp(H_rep, priors, syndrome, iters=10)
decision = (history[-1] < 0).astype(np.uint8)
print(decision)  # -> [0 0 0 1 0 0 0]
print(np.array_equal((H_rep @ decision) % 2, syndrome))  # -> True

# the degenerate trap: d0 touches all four mechanisms, d1/d2 pair them up
H_trap = np.array([
    [1, 1, 1, 1],
    [1, 1, 0, 0],
    [0, 0, 1, 1],
], dtype=np.uint8)
trap_priors = np.full(4, 0.08)
trap_syndrome = np.array([1, 1, 0], dtype=np.uint8)

trap_history = run_bp(H_trap, trap_priors, trap_syndrome, iters=6)
for it, L in enumerate(trap_history, start=1):
    hard = (L < 0).astype(np.uint8)
    print(it, np.round(L, 2), hard)
# -> 1 [-1.36 -1.36  3.52  3.52] [1 1 0 0]
# -> 2 [1.36 1.36 3.52 3.52] [0 0 0 0]
# -> 3 [-1.17 -1.17  4.2   4.2 ] [1 1 0 0]
# -> 4 [1.17 1.17 4.2  4.2 ] [0 0 0 0]
# -> 5 [-1.09 -1.09  4.33  4.33] [1 1 0 0]
# -> 6 [1.09 1.09 4.33 4.33] [0 0 0 0]


def osd0(H, syndrome, posterior):
    """OSD order 0: sort columns by |LLR|, GF(2)-eliminate, solve pivots (free = 0)."""
    n_checks, n_vars = H.shape
    order = np.argsort(-np.abs(posterior), kind="stable")
    rows = np.column_stack([H, syndrome]).astype(np.uint8)
    pivot_row = {}
    rank = 0

    for col in order:
        if rank == n_checks:
            break
        hits = [r for r in range(rank, n_checks) if rows[r, col] == 1]
        if len(hits) == 0:
            continue  # dependent on earlier pivots: stays a free column
        rows[[rank, hits[0]]] = rows[[hits[0], rank]]
        for r in range(n_checks):
            if r != rank and rows[r, col] == 1:
                rows[r] ^= rows[rank]
        pivot_row[col] = rank
        rank += 1

    recovery = np.zeros(n_vars, dtype=np.uint8)
    for col, r in pivot_row.items():
        recovery[col] = rows[r, n_vars]

    return recovery


# reliability ranking is decisive even though the signs never settled
print(np.argsort(-np.abs(trap_history[-1]), kind="stable"))  # -> [2 3 0 1]

recovery = osd0(H_trap, trap_syndrome, trap_history[-1])
print(recovery)  # -> [1 0 0 0]
print((H_trap @ recovery) % 2)  # -> [1 1 0]
```

```python [Qliff]
from qliff.qec import DetectorErrorModel, DetectorSampler
from qliff.qec import hex_color_code, logical_fidelity
from qliff.qec.decoder import BpOsdDecoder, make_decoder

# a colour-code memory: weight-6 checks, so single faults flip 3 detectors
circuit = hex_color_code(distance=2, rounds=2, p=0.01)
dem = DetectorErrorModel(circuit)

H, priors, obs_matrix = dem.check_matrix()
print(H.shape)  # -> (27, 36)
print(dem.is_graphlike(), dem.max_degree())  # -> False 3

# matching refuses this DEM outright
try:
    make_decoder("mwpm", dem)
except ValueError as err:
    print(str(err)[:34])  # -> MWPM needs a graphlike error model

# BP+OSD decodes it: sample syndromes, decode, compare to the true flips
decoder = BpOsdDecoder(dem)  # equivalently: make_decoder("bposd", dem)
detections, observed = DetectorSampler(circuit).sample(shots=200, seed=7)
predicted = decoder.decode_batch(detections)
print(logical_fidelity(predicted, observed))  # -> 0.99
```

:::

BP+OSD is fast and general, but it isn't *optimal*: OSD's combination search is a heuristic, not an exhaustive sum over every error. The next chapter contracts a tensor network to do that: **exact maximum-likelihood decoding**, weighing every consistent error at once.
