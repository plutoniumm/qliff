---
title: Minimum-Weight Perfect Matching
outline: 2
---

# Minimum-Weight Perfect Matching (MWPM) <Badge type="info" text="Tutorial 02 of 10" />

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

## Errors you can't see, checks you can measure

A quantum memory stores information in fragile qubits. We can't read them
directly: measuring a qubit destroys the superposition it holds. Instead a
code measures *parity checks*: each check reports whether a small group
of qubits has an even or odd number of errors, without revealing the data.

The simplest example is the **repetition code**. Lay data qubits
in a line and put a Z-check in every gap;
it compares its two neighbours. Click a qubit below to inject an
X error. A check between a flipped and an
unflipped qubit disagrees and lights up.
That lit check is a **detection event**, or *defect*.

**Repetition code**

<SvelteIsland :component="Fig1Problem" />

*Legend: data qubit; X error = flipped qubit; Z-check = quiet; lit check = defect; L / R = boundary node.*

::: tip A whole chain lights only its endpoints
Try *make a chain*: three adjacent errors, yet only two checks fire.
Every interior check sees *two* flips and cancels. The syndrome never
tells you the chain, only where it *starts and ends*. That is the
problem a decoder must solve.
:::

## Defects come in pairs: pick an explanation

Because each error toggles the checks on its two sides, defects are always
created in **pairs** (an end of the line acts as a silent
partner, the *boundary*). The syndrome is only a *set of lit
defects*. The catch: different error patterns produce the same set.

Here the syndrome is fixed: defects at the two highlighted gaps. Flip
between two completely different error chains that both explain it. They
differ by flipping the whole register: the code's logical operator.

**Degenerate syndrome**

<SvelteIsland :component="Fig2Pairs" />

*Legend: X error = flipped qubit; lit check = defect; untouched qubit.*

All consistent, all different. To *decode* we must commit to one. The
guiding principle: pick the **most likely** error. Under
independent noise with small error probability $p$, fewer flips
are exponentially more likely, so we want the explanation that flips the
*fewest* qubits. That is a **minimum-weight** choice, and
the next sections make "weight" precise.

## The syndrome becomes a graph

Forget the qubits for a moment and keep only the lit defects. Make each
defect a **node**. Add one virtual **boundary**
node at each end of the line. Now draw an **edge** between any
two nodes: an edge represents the error chain that would connect them, and
flipping that chain would *remove both defects at once*.

This is what qliff builds. It propagates every possible single
fault through the circuit, records which detectors it flips, and keeps every
mechanism that lights $\le 2$ detectors as a graph edge (a
fault lighting a single detector connects it to the boundary). MWPM works
*only* on this graphlike structure. Hover an edge to read its chain.

**Matching graph**

<SvelteIsland :component="Fig3Graph" />

*Legend: defect node; L / R = boundary node; candidate edge; hovered edge.*

::: info Boundary node = 'L' / 'R'
A defect near an end is often cheapest to cancel by running a short chain
off the edge of the line. The boundary node lets a *single*,
unpaired defect be matched on its own, which is essential when an odd
number of defects fire.
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
**maximising the product of error probabilities**, i.e. finding
the most likely error. The formula in NumPy, at the rates used on this page:

```python
import numpy as np

for p in (0.001, 0.08, 0.2, 0.5):
    print(p, round(float(np.log((1 - p) / p)), 2))
# -> 0.001 6.91
# -> 0.08 2.44
# -> 0.2 1.39
# -> 0.5 0.0
```

Slide $p$ and watch the weight move:

**Edge weight w(p)**

<SvelteIsland :component="Fig4Weights" />

*Legend: w = log((1-p)/p); defect node; candidate edge.*

::: tip Low p makes each flip cost more
At $p=0.001$ a single error carries weight $\approx 6.9$;
at $p=0.2$ only $\approx 1.4$. The cleaner the
hardware, the more expensive each extra flip, so the matcher prefers the
*fewest, shortest* chains. At $p=0.5$ the weight is
$0$ and every explanation is equally likely: the syndrome carries no
information.
:::

## Minimum-weight matching: beat the optimum

A **perfect matching** pairs up *every* defect (with
another defect or with a boundary) so all of them are cancelled. The
**minimum-weight** perfect matching is the cheapest such
pairing, and PyMatching v2 (qliff's default) finds it exactly. For the
small syndromes here we brute-force every pairing.

Your turn. Click two nodes (defects or the `L`/`R`
boxes) to pair them. Match them all, then reveal the optimum and see if you
beat it.

::: details Worked example: decode the default syndrome at p = 0.08
The starting errors are on qubits $\{2,6,7\}$,
which fire checks at gaps $\{1,2,5,7\}$; call
them $g_1,g_2,g_5,g_7$. Each edge costs
$\ell\cdot w$, the chain length times the
per-step weight.

1. Per-step weight: $w=\log\frac{1-p}{p}=\log\frac{0.92}{0.08}\approx 2.44$.
2. Try matching **A**: $g_1\!-\!g_2$ ($\ell=1$, $1\cdot 2.44=2.44$) and $g_5\!-\!g_7$ ($\ell=2$, $2\cdot 2.44=4.88$): total $2.44+4.88=7.33$.
3. Try a crossing matching **C**: $g_1\!-\!L$ ($\ell=2$, 4.88) + $g_2\!-\!g_5$ ($\ell=3$, 7.33) + $g_7\!-\!R$ ($\ell=1$, 2.44): total $14.65$, far worse.
4. The long-crossing matching **D** ($g_1\!-\!g_5$, $g_2\!-\!g_7$) flips chains of length 4 and 5: total $9.77+12.21=21.98$, worse still.

**Result:** Matching **A** wins with total weight **7.33**: the fewest, shortest chains. Click *reveal optimum* below: it shows the same **7.33** and the pairs $g_1\!-\!g_2$, $g_5\!-\!g_7$.
:::

**Build a matching**

<SvelteIsland :component="Fig5Match" />

*Legend: defect node; L / R = boundary node; your pairing; optimum correction.*

## From matching to correction: did the qubit survive?

The matched edges *are* the correction: flip the chain under each arc
and every defect disappears. qliff reads this straight off the
`faults_matrix`: each matched mechanism maps to the
**observable flips** it implies, and `decode_batch`
returns those predicted flips. But removing the defects is not the same as
saving the data.

Define the **residual** as real error XOR correction,

$$r \;=\; e \oplus \hat{e}, \qquad \text{logical error} \iff r = \bar{X} = (1,1,\dots,1).$$

Here $e$ is the true error, $\hat{e}$
the correction, and $\bar X$ the rep-code logical
operator (flip every qubit). If $r=0$ the qubit survives. If
$r$ forms a chain that *wraps the whole line*, connecting
the two boundaries, it equals $\bar X$ and the
logical bit is silently flipped: a logical error.

**Correction vs residual**

<SvelteIsland :component="Fig6Correction" />

*Legend: true X error; lit check = defect; matched pairing; MWPM correction chain.*

::: warning The decoder isn't wrong, only unlucky
With the past-midpoint chain, the *shorter* way to cancel the defects
runs off the opposite end. MWPM returns the most-likely (shortest)
explanation; it is not the one that happened. No graphlike decoder can do
better on this single shot.
:::

## Why it can still fail, and how distance helps

A logical error needs the residual to span the line, which takes a chain
longer than half the code. So failures require roughly
$\ge d/2$ errors, where $d$ is the
**distance** (here the number of data qubits). More qubits => longer
failure chains => exponentially rarer logical errors, as long
as $p$ is below threshold. Concretely the logical error rate
falls like

$$P_L \;\sim\; \binom{d}{\lceil d/2\rceil}\,p^{\,\lceil d/2\rceil}\,(1-p)^{\,\lfloor d/2\rfloor} \;\xrightarrow{p<p_{\mathrm{th}}}\; 0,$$

where $d$ is the distance and $p_{\mathrm{th}}$
the threshold below which growing $d$ wins. The estimator below
is the Monte-Carlo count $P_L \approx \text{fails}/N$:
it samples errors, builds the syndrome, runs the same min-weight matching,
and checks the residual, over thousands of shots.

**Logical error rate vs p**

<SvelteIsland :component="Fig7Ler" />

*Legend: LER sweep (4k-2.5k shots); sampled p point; current p marker; decade gridline.*

::: tip When two matchings tie, it's a coin flip
At the half-way chain, the two cheapest matchings differ by a
logical and have *equal* weight. MWPM must break the tie blindly, so
it is right half the time: an irreducible failure floor. Raising
$d$ moves that tie further out of reach.
:::

**Search replay**

<SvelteIsland :component="Fig7Replay" />

*Legend: candidate edge; chosen optimal pair; correction (final frame).*

## Implementation {#implementation}

Everything above is one pipeline: syndrome to defect list, defect list to
weighted graph, graph to minimum-weight matching, matching to correction,
correction to a logical verdict. The tabs below walk that pipeline three
times: as pseudocode, as a self-contained NumPy program, and through
qliff's decoder stack.

**Pseudocode.** One decode of a single shot. The scoring step compares
against the true error, so it exists only in simulation; hardware stops at
the correction.

**Std Python.** The whole decoder for this page's repetition code, with the
boundary trick and an exhaustive (hence exact) minimum-weight matching.
Part 1 re-derives the worked example above; part 2 Monte-Carlos the logical
error rate. Both LER points land well below their physical rates: the code
helps.

**Qliff.** The same experiment through the library. `repetition_code` emits
the noisy memory circuit, `DetectorErrorModel` extracts the matching graph
(with the same per-step weight the worked example used),
`make_decoder("mwpm")` wraps PyMatching v2, `DetectorSampler` draws
syndromes, and `logical_error_rate` runs the whole sample -> decode ->
compare loop in one call.

::: code-group

```text [Pseudocode]
decode(syndrome):
    defects <- [g for each check g that fired]
    nodes   <- defects + virtual boundary nodes (L, R)
    build the complete graph on nodes; for each pair (u, v):
        weight(u, v) <- (length of the shortest error chain joining u and v)
                        * log((1 - p) / p)
    matching   <- minimum-weight perfect matching of the graph
    correction <- XOR of the qubit chains under the matched pairs
    return correction

score(error, correction):            # simulation only
    residual <- error XOR correction
    # residual has an empty syndrome: identity or a logical operator
    logical error <- (residual == logical operator)
```

```python [Std Python]
import numpy as np

D = 9                        # data qubits; checks sit in the D-1 gaps
LEFT, RIGHT = "L", "R"       # virtual boundary nodes


def syndrome(error):
    """Gap g fires iff qubits g and g+1 disagree."""
    return [g for g in range(len(error) - 1) if error[g] != error[g + 1]]


def chain_qubits(a, b, d):
    """Data qubits flipped by the shortest chain joining nodes a and b."""
    if a == LEFT or b == LEFT:
        g = b if a == LEFT else a
        return list(range(0, g + 1))

    if a == RIGHT or b == RIGHT:
        g = b if a == RIGHT else a
        return list(range(g + 1, d))

    lo, hi = sorted((a, b))
    return list(range(lo + 1, hi + 1))


def all_pairings(defects):
    """Every perfect matching: each defect pairs with a boundary or a later defect."""
    if len(defects) == 0:
        yield []
        return

    first, rest = defects[0], defects[1:]
    for boundary in (LEFT, RIGHT):
        for tail in all_pairings(rest):
            yield [(first, boundary)] + tail

    for k in range(len(rest)):
        remaining = rest[:k] + rest[k + 1:]
        for tail in all_pairings(remaining):
            yield [(first, rest[k])] + tail


def mwpm(defects, d, w):
    """Exact minimum-weight perfect matching by exhaustive search."""
    best_pairs, best_weight = [], 0.0
    for pairs in all_pairings(defects):
        weight = w * sum(len(chain_qubits(a, b, d)) for a, b in pairs)
        if len(best_pairs) == 0 or weight < best_weight:
            best_pairs, best_weight = pairs, weight

    return best_pairs, best_weight


def correction_of(pairs, d):
    """XOR together the chains under the matched pairs."""
    corr = np.zeros(d, dtype=np.uint8)
    for a, b in pairs:
        for q in chain_qubits(a, b, d):
            corr[q] ^= 1

    return corr


# part 1: the worked example (errors on qubits 2, 6, 7 at p = 0.08)
p = 0.08
w = np.log((1.0 - p) / p)
error = np.zeros(D, dtype=np.uint8)
error[[2, 6, 7]] = 1

defects = syndrome(error)
print(defects)
# -> [1, 2, 5, 7]

pairs, weight = mwpm(defects, D, w)
print(pairs, round(float(weight), 2))
# -> [(1, 2), (5, 7)] 7.33

correction = correction_of(pairs, D)
residual = error ^ correction
print(syndrome(residual), int(residual[0]))
# -> [] 0   (no defects left, no logical flip: decoded correctly)

# part 2: Monte-Carlo logical error rate
rng = np.random.default_rng(2026)
for p in (0.1, 0.2):
    w = np.log((1.0 - p) / p)
    fails = 0
    shots = 5000
    for _ in range(shots):
        error = (rng.random(D) < p).astype(np.uint8)
        pairs, _weight = mwpm(syndrome(error), D, w)
        residual = error ^ correction_of(pairs, D)
        # residual has an empty syndrome: all-zero (success) or all-one (logical X)
        if residual[0] == 1:
            fails += 1
    print(f"p={p}: LER = {fails / shots}")
# -> p=0.1: LER = 0.0006
# -> p=0.2: LER = 0.0166
```

```python [Qliff]
import numpy as np

from qliff.qec.codes import repetition_code
from qliff.qec.decoder import make_decoder
from qliff.qec.dem import DetectorErrorModel
from qliff.qec.sampler import DetectorSampler
from qliff.qec.threshold import logical_error_rate

# one round of the d=9 bit-flip repetition code at p = 0.08
circuit = repetition_code(distance=9, rounds=1, p=0.08, channel="X_ERROR")

# the matching graph MWPM consumes
dem = DetectorErrorModel(circuit)
print(dem.is_graphlike(), dem.num_detectors, len(dem.mechanisms))
# -> True 16 9

print(round(float(dem.weights()[0]), 2))
# -> 2.44   (log((1-p)/p), the per-step weight of the worked example)

# sample -> decode -> compare, by hand
decoder = make_decoder("mwpm", dem)
dets, obs = DetectorSampler(circuit).sample(shots=2000, seed=7)
predictions = decoder.decode_batch(dets)
fails = np.any(predictions != obs, axis=1)
print(int(fails.sum()), "fails in", fails.size, "shots")
# -> 1 fails in 2000 shots

# the one-call version: grow the distance at fixed p
for d in (3, 5, 9):
    circuit = repetition_code(distance=d, rounds=1, p=0.08, channel="X_ERROR")
    ler, stderr = logical_error_rate(circuit, decoder_name="mwpm", shots=4000, seed=7)
    print(f"d={d}: LER = {ler:.4f} +/- {stderr:.4f}")
# -> d=3: LER = 0.0195 +/- 0.0022
# -> d=5: LER = 0.0040 +/- 0.0010
# -> d=9: LER = 0.0005 +/- 0.0004
```

:::

::: tip Where matching stops
MWPM is fast, optimal for graphlike codes, and the qliff default. But it
assumes every error lights $\le 2$ detectors. Codes whose faults light
three or more checks (colour codes, many LDPC codes) break that
assumption. For those we hand the same error model to
**belief propagation**, the next decoder, which reasons over
probabilities instead of pairings.
:::
