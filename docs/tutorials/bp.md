---
title: Belief Propagation
outline: 2
---

# Belief Propagation <Badge type="info" text="Tutorial 03 of 7" />

> Let qubits and checks exchange probabilities until they agree on the likeliest error.

<script setup>
import TannerDemo from '../_tut/bp/TannerDemo.svelte'
import PriorGauge from '../_tut/bp/PriorGauge.svelte'
import DanceDemo from '../_tut/bp/DanceDemo.svelte'
import BeliefsDemo from '../_tut/bp/BeliefsDemo.svelte'
import StuckDemo from '../_tut/bp/StuckDemo.svelte'
</script>

## Why another decoder?

In the previous chapter, **minimum-weight perfect matching** turned a syndrome into a graph and paired up the lit detectors. That trick only works when every possible error touches *at most two* detectors -- then each error is an *edge* and decoding is graph matching.

But most codes aren't so tidy. A single fault can flip three, four, or a dozen parity checks at once. Now an error is no longer an edge: it's a node wired to all the checks it disturbs. Matching has nothing to match. We need a decoder that lives on the *full bipartite graph* of errors and checks.

::: tip The one-line intuition
**Belief propagation is neighbours gossiping until they agree.** Every possible error and every parity check holds an opinion -- "I probably did/didn't fire," "my parity is/ isn't satisfied" -- and they trade these opinions back and forth along the edges. After a few rounds, the opinions (hopefully) settle on the single most likely error.
:::

This is exactly what qliff's `BpOsdDecoder` does. It hands the code's check matrix to belief propagation, and -- when BP can't decide -- to a cleanup step called **OSD**. By the end of this page you'll have run both, live, on a real example where plain matching would be helpless.

## The Tanner graph

Everything BP does happens on one picture: the **Tanner graph** (a "factor graph"). It has two kinds of node:

- **Variables** (circles, top) -- one per *error mechanism*: a possible fault, like "qubit 3 picked up an X."
- **Checks** (squares, bottom) -- one per *detector*: a parity measurement that lights up if an odd number of its neighbouring errors fired.

We draw an edge from error $e_m$ to detector $d_c$ exactly when $H_{cm}=1$ -- i.e. mechanism $m$ flips detector $c$. That matrix $H$ is the same one qliff builds from the circuit (`dem.check_matrix()` returns $H$, the priors, and the observable map).

Click a detector to "light" it -- that's a **syndrome**, the only thing the decoder actually observes. Hover any node to see who it talks to.

**Tanner graph**

<SvelteIsland :component="TannerDemo" />

*A small Tanner graph. Squares are detectors (parity checks); circles are error mechanisms. Click a detector to toggle the syndrome; hover a node to highlight its edges.*

Legend:
- variable node = error mechanism (circle)
- check node = detector (square)
- lit check (syndrome bit = 1)
- edge: mechanism flips detector

::: info Contrast with matching
Detector $d_1$ here touches *three* error mechanisms. Matching would choke on it. BP doesn't care how many edges a node has -- it just keeps gossiping along all of them.
:::

## Beliefs as log-odds

Before any gossip, each error mechanism has a **prior**: the channel probability $p$ that it fired. BP doesn't pass probabilities around directly -- it passes their **log-likelihood ratio** (LLR):

$$
\ell = \log\frac{1-p}{p} = \log\frac{P(\text{no error})}{P(\text{error})}.
$$

Why log-odds? Because along the way BP needs to *combine independent evidence*, and in log-space combining evidence is just **addition**. The sign and size carry all the meaning:

- $\ell \gg 0$ -- confident there's **no error** (small $p$).
- $\ell \approx 0$ -- a coin flip; the mechanism is undecided.
- $\ell < 0$ -- the evidence now favours an **error**.

**Prior p -> LLR**

<SvelteIsland :component="PriorGauge" />

*Drag the prior $p$. The gauge shows the resulting prior LLR $\ell = \log\frac{1-p}{p}$ in nats -- exactly the number qliff seeds BP with per mechanism.*

Legend:
- $\ell < 0$: favours error
- $\ell > 0$: favours no error

::: tip Posterior, the other direction
After gossiping, BP has a *posterior* LLR per mechanism. Convert back with $p = \tfrac{1}{1+e^{\ell}}$. The hard decision is dead simple: declare an error whenever the posterior LLR goes **negative**.
:::

## The message-passing dance

Now the gossip itself. Two kinds of message flow along every edge, and we alternate them each iteration. Below, a true error sits on one bit (cyan ring); only the lit detectors are observed. Step through and watch the beliefs flow.

**Variable -> check.** A mechanism tells each neighbouring detector its log-odds, *using its prior plus what every* other *detector told it* (never echoing a check's own message back):

$$
m_{m\to c} \;=\; \ell_m \;+\!\!\sum_{c'\neq c} m_{c'\to m}.
$$

**Check -> variable** is the clever part. A detector enforces a parity constraint, and the exact rule for combining log-odds through an XOR is the **tanh rule**:

$$
\tanh\frac{m_{c\to m}}{2} \;=\; (-1)^{s_c}\!\!\prod_{m'\neq m}\tanh\frac{m_{m'\to c}}{2},
$$

where $s_c$ is that detector's syndrome bit (a lit detector flips the sign, pushing its neighbours toward *disagreeing*). Solving for the outgoing message gives the rule `bp.ts` actually evaluates:

$$
m_{c\to m} \;=\; 2\,\mathrm{atanh}\!\Big[(-1)^{s_c}\!\!\prod_{m'\neq m}\tanh\tfrac{m_{m'\to c}}{2}\Big].
$$

This is precisely `bp_method="product_sum"` -- sum-product BP in the log domain.

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

*Real sum-product BP on a 7-bit repetition code. Dots are live messages, sized and coloured (heat) by magnitude. Belief rings on each mechanism track its posterior P(error); rings/labels turn red once a mechanism is called an error.*

Legend:
- live message (size/heat = |LLR|)
- belief ring = posterior P(error)
- true error mechanism
- called an error (hard decision)

Iteration **0** is just the priors -- every belief is the same calm positive number. As messages flow, the detectors next to the true error start shouting "something flipped near me," and the beliefs of the mechanisms between two lit detectors collapse toward error.

## Reading the answer

Once the messages stop changing, BP *converged*. Each mechanism's **posterior LLR** sums its prior and *all* incoming check messages (no back-edge dropped this time); thresholding at zero gives the hard decision $\hat e$:

$$
L_m \;=\; \ell_m + \sum_{c} m_{c\to m}, \qquad \hat e_m = \begin{cases}1 & L_m < 0\\ 0 & L_m \ge 0\end{cases}
$$

The proof that it's self-consistent: feed $\hat e$ back through $H$ and check it reproduces the very syndrome we started with.

::: details One mechanism's posterior and hard decision
A mechanism with prior $p=0.06$ (so $\ell = \log\frac{0.94}{0.06} = 2.752$) sits between two lit detectors that now send it strong "error" messages $-2.0$ and $-1.6$.

1. Sum prior + all incoming: $L = 2.752 + (-2.0) + (-1.6) = -0.848$.
2. Convert to a probability: $p = \tfrac{1}{1+e^{L}} = \tfrac{1}{1+e^{-0.848}} = 0.70$.
3. Threshold: $L < 0$, so the hard decision is $\hat e = 1$.

**Result:** The two detectors *outvoted* the prior: a mechanism that started 94% safe is now called an **error** ($P \approx 0.70$). One lukewarm prior is no match for two confident neighbours -- that's evidence adding up in log-space.
:::

**Posterior beliefs**

<SvelteIsland :component="BeliefsDemo" />

*Posterior beliefs at the current iteration. Bars grow left (red) toward 'error', right toward 'no error'; intensity tracks confidence. The 'true' mechanism is marked in cyan.*

Legend:
- bar left = error ($\ell < 0$)
- bar right = no error ($\ell > 0$)
- true mechanism (cyan label)

The recovered mechanism vector then maps through the observable matrix ($\text{obs} = O\,\hat{e} \bmod 2$) to say which *logical* observables flipped -- the actual output qliff hands back. Try moving the true error around in the panel above; for the repetition code, BP nails it every time.

::: info So far, so easy
The repetition code is *graphlike* and loop-free near a single error, so BP glides to the answer. That's the happy path. Next we break it.
:::

## When BP gets stuck

Quantum codes are **degenerate**: genuinely different errors can have identical syndromes and identical likelihoods. When the graph also has short cycles, BP's "independent evidence" assumption breaks -- and the beliefs can **oscillate forever**, never committing to an answer.

Here's a tiny hand-built code that traps it. Detector $d_0$ touches all four mechanisms; $d_1$ and $d_2$ each pair two of them. The syndrome lights $d_0,d_1$; the obvious fix is mechanism $e_0$ alone. But the symmetry makes mechanisms $e_0$ and $e_1$ perfectly tied. Watch:

**Degenerate trap**

<SvelteIsland :component="StuckDemo" />

*A degenerate trap. Step the iteration: the hard decision flips between e0,e1 and nothing on every round, and the posteriors for e0 and e1 stay locked together -- BP never decides. (It is genuinely not converging; this is not an animation loop.)*

Legend:
- lit check
- unsatisfied check (residual = 1)
- oscillating belief ring

::: warning The symmetric trap
Notice $e_0$ and $e_1$ always carry the *identical* posterior -- and it keeps flipping sign. BP has split its belief symmetrically between two indistinguishable stories and can't break the tie. No number of extra iterations helps. This is exactly the failure mode that sinks plain BP on real quantum codes (colour codes, surface codes with short cycles).
:::

## OSD to the rescue

**BP proposes, OSD disposes.** Ordered-statistics decoding doesn't throw away BP's work -- it uses BP's soft output to make a *decisive* guess. qliff runs `osd_method="osd_cs"` with `osd_order=7`. The recipe:

1. **Order by reliability.** Sort the mechanisms by $|L_m|$ -- most confident first. Even when BP can't decide *between* $e_0$ and $e_1$, it *is* sure that $e_2,e_3$ stayed quiet.
2. **Solve a full-rank core exactly.** Walk that ordered list and Gaussian-eliminate over $\mathbb{F}_2$ to pull out a most-reliable set of independent pivot columns $\mathcal{P}$, then solve that square subsystem $H_{\mathcal{P}}\,\hat e_{\mathcal{P}} \;=\; s \pmod 2$ (free columns set to 0). This forces a recovery that *exactly* reproduces the syndrome -- no more oscillation.
3. **Search small corrections (order 7).** Flip up to $7$ of the least-reliable free columns, re-solve, and keep the *lowest-weight* consistent answer found.

<div class="qtut">
<figure class="q-fig">
  <div class="q-fig-title">BP + OSD</div>
  <p><strong>1 -- reliability order.</strong> Columns most-reliable-first; bar length is the posterior reliability |L| (heat-capped at 5). BP is sure e2, e3 stayed quiet but cannot break the e0/e1 tie.</p>
  <ul class="q-bars">
    <li style="--v:.91;--c:var(--x)"><b>e2 <span class="q-chip" style="--c:var(--accent)">pivot</span></b><span class="q-track"></span><i>4.56</i></li>
    <li style="--v:.91;--c:var(--x)"><b>e3 <span class="q-chip" style="--c:var(--muted)">free</span></b><span class="q-track"></span><i>4.56</i></li>
    <li style="--v:.17;--c:var(--z)"><b>e0 <span class="q-chip" style="--c:var(--accent)">pivot</span></b><span class="q-track"></span><i>0.83</i></li>
    <li style="--v:.17;--c:var(--z)"><b>e1 <span class="q-chip" style="--c:var(--muted)">free</span></b><span class="q-track"></span><i>0.83</i></li>
  </ul>
  <p><strong>2 -- solved recovery.</strong> Solve the pivot core exactly (free columns = 0), then search order-7 flips of the least-reliable free columns.</p>
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
OSD turns BP's *almost-an-answer* into a guaranteed syndrome-consistent, low-weight recovery. Crucially, BP+OSD works on the **general bipartite graph** -- including *non-graphlike* codes (colour codes, dense LDPC) where a detector touches more than two errors and MWPM has no graph to match. That generality is the whole reason it sits alongside matching in the decoder zoo.
:::

BP+OSD is fast and general, but it isn't *optimal*: OSD's combination search is a heuristic, not an exhaustive sum over every error. The next chapter contracts a tensor network to do exactly that -- **exact maximum-likelihood decoding** -- weighing every consistent error at once.
