---
title: Minimum-Weight Perfect Matching
outline: 2
---

# Minimum-Weight Perfect Matching (MWPM) <Badge type="info" text="Tutorial 02 of 7" />

> Turn a syndrome into a graph, then pair up the defects as cheaply as possible.

<script setup>
import Fig1Problem from '../_tut/mwpm/Fig1Problem.svelte'
import Fig2Pairs from '../_tut/mwpm/Fig2Pairs.svelte'
import Fig3Graph from '../_tut/mwpm/Fig3Graph.svelte'
import Fig4Weights from '../_tut/mwpm/Fig4Weights.svelte'
import Fig5Match from '../_tut/mwpm/Fig5Match.svelte'
import Fig6Correction from '../_tut/mwpm/Fig6Correction.svelte'
import Fig7Ler from '../_tut/mwpm/Fig7Ler.svelte'
import Fig7Replay from '../_tut/mwpm/Fig7Replay.svelte'
</script>

## Errors you can't see, checks that can talk

A quantum memory stores information in fragile qubits. We can't peek at them
directly -- measuring a qubit destroys the superposition it holds. Instead a
code measures *parity checks*: each check reports whether a small group
of qubits has an even or odd number of errors, without revealing the data.

The simplest example is the **repetition code**. Lay data qubits
in a line and put a Z-check in every gap;
it compares its two neighbours. Click a qubit below to inject an
X error. A check between a flipped and an
unflipped qubit disagrees and lights up
-- that lit check is a **detection event**, or *defect*.

**Repetition code**

<SvelteIsland :component="Fig1Problem" />

*Click data qubits to flip them. A check fires iff its two neighbours disagree.*

*Legend: data qubit; X error (flipped qubit); Z-check (quiet); lit check (defect); boundary node (L / R).*

::: tip A whole chain lights only its endpoints
Try *make a chain*: three adjacent errors, yet only two checks fire.
Every interior check sees *two* flips and cancels. The syndrome never
tells you the chain -- only where it *starts and ends*. That is the
entire problem a decoder must solve.
:::

## Defects come in pairs -- pick an explanation

Because each error toggles the checks on its two sides, defects are always
created in **pairs** (an end of the line acts as a silent
partner -- the *boundary*). The syndrome is just a *set of lit
defects*. The catch: different error patterns produce the very same set.

Here the syndrome is fixed -- defects at the two highlighted gaps. Flip
between two completely different error chains that both explain it. They
differ by flipping the whole register: exactly the code's logical operator.

**Degenerate syndrome**

<SvelteIsland :component="Fig2Pairs" />

*Both patterns light exactly the same defects (gaps 2 and 6). Which one really happened? The syndrome can't tell us.*

*Legend: X error (flipped qubit); lit check (defect); untouched qubit.*

All consistent, all different. To *decode* we must commit to one. The
guiding principle: pick the **most likely** error. Under
independent noise with small error probability $p$, fewer flips
are exponentially more likely -- so we want the explanation that flips the
*fewest* qubits. That is a **minimum-weight** choice, and
the next sections make "weight" precise.

## The syndrome becomes a graph

Forget the qubits for a moment and keep only the lit defects. Make each
defect a **node**. Add one virtual **boundary**
node at each end of the line. Now draw an **edge** between any
two nodes: an edge represents the error chain that would connect them -- and
flipping that chain would *remove both defects at once*.

This is exactly what qliff builds. It propagates every possible single
fault through the circuit, records which detectors it flips, and keeps every
mechanism that lights $\le 2$ detectors as a graph edge (a
fault lighting just one detector connects it to the boundary). MWPM works
*only* on this graphlike structure. Hover an edge to read its chain.

**Matching graph**

<SvelteIsland :component="Fig3Graph" />

*Dashed grey = every candidate edge of the matching graph (defect$\leftrightarrow$defect and defect$\leftrightarrow$boundary). Hover to inspect a chain.*

*Legend: defect node; boundary node (L / R); candidate edge; hovered edge.*

::: info Boundary node = 'L' / 'R'
A defect near an end is often cheapest to cancel by running a short chain
off the edge of the line. The boundary node lets a *single*,
unpaired defect be matched on its own -- essential when an odd number of
defects fire.
:::

## Edge weight = log-odds of the chain

What makes one edge "cheaper" than another? Each edge is a chain of
independent errors. A chain of length $\ell$ happens with
probability $\propto p^{\ell}(1-p)^{\dots}$. To turn a
*product* of probabilities into a *sum* we can minimise, take a
logarithm. qliff assigns every mechanism the weight

$$w \;=\; \log\frac{1-p}{p},$$

per unit of chain length, straight out of
`DetectorErrorModel.weights()`. Minimising the total matched
weight $\sum \log\frac{1-p}{p}$ is the same as
**maximising the product of error probabilities** -- i.e. finding
the most likely error. Slide $p$ and watch the weight move:

**Edge weight w(p)**

<SvelteIsland :component="Fig4Weights" />

*Lower physical error rate -> higher weight per chain step -> the matcher fights harder to use short chains.*

*Legend: w = log((1-p)/p); defect node; candidate edge.*

::: tip Low p costs MORE
At $p=0.001$ a single error carries weight $\approx 6.9$;
at $p=0.2$ only $\approx 1.4$. The cleaner the
hardware, the more expensive each extra flip -- so the matcher prefers the
*fewest, shortest* chains. At $p=0.5$ the weight is
$0$ and every explanation is equally likely: noise has won.
:::

## Minimum-weight matching -- beat the optimum

A **perfect matching** pairs up *every* defect -- with
another defect or with a boundary -- so all of them are cancelled. The
**minimum-weight** perfect matching is the cheapest such
pairing, and PyMatching v2 (qliff's default) finds it exactly. For the
small syndromes here we brute-force every pairing.

Your turn. Click two nodes (defects or the `L`/`R`
boxes) to pair them. Match them all, then reveal the optimum and see if you
beat it.

::: details Worked example -- Decode the default syndrome at p = 0.08
The starting errors are on qubits $\{2,6,7\}$,
which fire checks at gaps $\{1,2,5,7\}$ -- call
them $g_1,g_2,g_5,g_7$. Each edge costs
$\ell\cdot w$, the chain length times the
per-step weight.

1. Per-step weight: $w=\log\frac{1-p}{p}=\log\frac{0.92}{0.08}\approx 2.44$.
2. Try matching **A**: $g_1\!-\!g_2$ ($\ell=1$, $1\cdot 2.44=2.44$) and $g_5\!-\!g_7$ ($\ell=2$, $2\cdot 2.44=4.88$): total $2.44+4.88=7.33$.
3. Try a crossing matching **C**: $g_1\!-\!L$ ($\ell=2$, 4.88) + $g_2\!-\!g_5$ ($\ell=3$, 7.33) + $g_7\!-\!R$ ($\ell=1$, 2.44): total $14.65$ -- far worse.
4. The long-crossing matching **D** ($g_1\!-\!g_5$, $g_2\!-\!g_7$) flips chains of length 4 and 5: total $9.77+12.21=21.98$, worse still.

**Result:** Matching **A** wins with total weight **7.33** -- the fewest, shortest chains. Click *reveal optimum* below: it shows the same **7.33** and the pairs $g_1\!-\!g_2$, $g_5\!-\!g_7$.
:::

**Build a matching**

<SvelteIsland :component="Fig5Match" />

*Click defects / boundary boxes to build your own matching. Cyan arcs = your pairs.*

*Legend: defect to pair; boundary node (L / R); your pairing; optimum correction.*

## From matching to correction -- did the qubit survive?

The matched edges *are* the correction: flip the chain under each arc
and every defect disappears. qliff reads this straight off the
`faults_matrix` -- each matched mechanism maps to the
**observable flips** it implies, and `decode_batch`
returns those predicted flips. But removing the defects is not the same as
saving the data.

Define the **residual** as real error XOR correction,

$$r \;=\; e \oplus \hat{e}, \qquad \text{logical error} \iff r = \bar{X} = (1,1,\dots,1).$$

Here $e$ is the true error, $\hat{e}$
the correction, and $\bar X$ the rep-code logical
operator (flip every qubit). If $r=0$ the qubit survives. If
$r$ forms a chain that *wraps the whole line* -- connecting
the two boundaries -- it equals $\bar X$ and the
logical bit is silently flipped: a logical error.

**Correction vs residual**

<SvelteIsland :component="Fig6Correction" />

*Green band = MWPM's correction. Compare it with the true error to read the residual.*

*Legend: true X error; lit check (defect); matched pairing; MWPM correction chain.*

::: warning The decoder isn't wrong -- it's unlucky
With the past-midpoint chain, the *shorter* way to cancel the defects
runs off the opposite end. MWPM faithfully returns the most-likely (shortest)
explanation; it just isn't the one that happened. No graphlike decoder can do
better on this single shot.
:::

## Why it can still fail -- and how distance saves you

A logical error needs the residual to span the line, which takes a chain
longer than half the code. So failures require roughly
$\ge d/2$ errors, where $d$ is the
**distance** (here the number of data qubits). More qubits => a
longer wall for noise to climb => exponentially rarer logical errors, as long
as $p$ is below threshold. Concretely the logical error rate
falls like

$$P_L \;\sim\; \binom{d}{\lceil d/2\rceil}\,p^{\,\lceil d/2\rceil}\,(1-p)^{\,\lfloor d/2\rfloor} \;\xrightarrow{p<p_{\mathrm{th}}}\; 0,$$

where $d$ is the distance and $p_{\mathrm{th}}$
the threshold below which growing $d$ wins. The estimator below
is just the Monte-Carlo count $P_L \approx \text{fails}/N$:
it samples errors, builds the syndrome, runs the same min-weight matching,
and checks the residual, over thousands of shots.

**Logical error rate vs p**

<SvelteIsland :component="Fig7Ler" />

*Live logical error rate of the MWPM-decoded repetition code. Raise the distance and watch reliability improve while p stays fixed.*

*Legend: LER sweep (4k-2.5k shots); sampled p point; current p marker; decade gridline.*

::: tip When two matchings tie, it's a coin flip
Exactly at the half-way chain, the two cheapest matchings differ by a
logical and have *equal* weight. MWPM must break the tie blindly, so
it's right half the time -- the irreducible failure floor. Pushing
$d$ up moves that knife-edge further away.
:::

MWPM is fast, optimal for graphlike codes, and the qliff default. But it
assumes every error lights $\le 2$ detectors. Codes whose
faults light three or more checks -- colour codes, many LDPC codes -- break
that assumption. For those we hand the same graph to
**belief propagation**, the next decoder, which reasons over
probabilities instead of pairings.

**Search replay**

<SvelteIsland :component="Fig7Replay" />

*Optional: step through the brute-force search revealing the optimal pairs one at a time on the graph from step 3/4.*

*Legend: candidate edge; chosen optimal pair; correction (final frame).*
