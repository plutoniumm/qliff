---
title: Gates in a Stabilizer Simulator
outline: 2
---

# Gates in a Stabilizer Simulator <Badge type="info" text="Tutorial 01 of 7" />

> Cliffords don't move amplitudes -- they conjugate Pauli operators. See why CX makes X copy forward and Z copy backward.

<script setup>
import HeisenbergDemo from '../_tut/gates/HeisenbergDemo.svelte'
import BitsDemo from '../_tut/gates/BitsDemo.svelte'
import SingleGateDemo from '../_tut/gates/SingleGateDemo.svelte'
import CXDemo from '../_tut/gates/CXDemo.svelte'
import PropagationDemo from '../_tut/gates/PropagationDemo.svelte'
import SignsDemo from '../_tut/gates/SignsDemo.svelte'
</script>

## Cliffords conjugate operators, not amplitudes {#heisenberg}

A general $n$-qubit state needs $2^n$ complex amplitudes -- hopeless past ~30 qubits. A **stabilizer simulator** sidesteps that entirely. Instead of the state vector it tracks the Pauli operators that *stabilize* the state: operators $S$ with $S\ket{\psi}=+\ket{\psi}$. The state is pinned down by its stabilizers, so we only ever store and update *operators*.

When a gate $U$ acts, every stabilizer is updated by **conjugation** in the Heisenberg picture, $S \mapsto U S U^{\dagger}$. Why that is the right rule:

$$(U S U^{\dagger})\,(U\ket{\psi}) = U S \ket{\psi} = U\ket{\psi},$$

so if $S$ stabilized the old state, $USU^{\dagger}$ stabilizes the new one $U\ket{\psi}$. No amplitudes appear -- just a Pauli in, a Pauli out. Press a gate and watch the single stabilizer of a 1-qubit state move, and the ket it pins down change with it.

**1-qubit stabilizer under a gate**

<SvelteIsland :component="HeisenbergDemo" />

*The operator IS the state here: +Z pins |0⟩, +X pins |+⟩, −Y pins |−i⟩, ... (colors: X part, Z part, + sign, − sign.)*

::: tip Operators, never 2^n numbers
$H$ on $+Z$ (which is $\ket0$) gives $+X$ (which is $\ket+$) -- exactly the Hadamard basis change. The whole simulation is bookkeeping on a handful of bits per operator, which is why qliff scales to thousands of qubits where a state vector cannot.
:::

## A Pauli is two bits plus a sign {#bits}

To compute with Paulis we encode each single-qubit factor as two bits -- an x bit and a z bit -- plus one global **sign** bit for the whole operator ($0=+$, $1=-$):

**Pauli ↔ bits**

<SvelteIsland :component="BitsDemo" />

*Y is just x=z=1 in the tableau (the i in Y=iXZ lives in the bookkeeping, not these bits). (colors: x bit (1 => has X-part), z bit (1 => has Z-part).)*

::: info The full tableau
A stabilizer state of $n$ qubits is $n$ such rows (qliff stores $2n$ -- also $n$ destabilizers -- but one conjugated row already tells the whole gate story). A gate edits these bits column by column; that is the entire engine.
:::

## Single-qubit gates are tiny bit ops {#single}

Each Clifford is a fixed recipe on the bits. Crucially we read the *original* $x,z$ to update the sign, *then* permute the bits:

$$\textsf{H}: \;\text{sign}\,{\oplus}{=}\,x z,\;\; x{\leftrightarrow}z \qquad \textsf{S}: \;\text{sign}\,{\oplus}{=}\,x z,\;\; z\,{\oplus}{=}\,x$$

$\textsf{X},\textsf{Z},\textsf{Y}$ never move bits at all -- they only flip the sign when they anticommute with what is already there ($\textsf{X}{:}\,\text{sign}\,{\oplus}{=}\,z$, $\textsf{Z}{:}\,\text{sign}\,{\oplus}{=}\,x$). Pick a starting Pauli, apply gates, and watch the bits and the sign rule fire.

**Bit-level gate playground**

<SvelteIsland :component="SingleGateDemo" />

*Set a Pauli, then apply gates. Y→−Y under H is the xz sign term firing. (colors: x bit, z bit, + sign, − sign.)*

::: details Worked example: H on Z, then S on X (every number from the rules)

1. Start at $Z$: bits $(x,z)=(0,1)$, sign $0$.
2. Apply $\textsf{H}$. Sign term $x\cdot z = 0\cdot 1 = 0$, so sign stays $0$. Swap bits: $(0,1)\to(1,0)$.
3. $(1,0)$ with sign $0$ reads as $+X$. So $\textsf H Z\textsf H = X$. ✓
4. Now start fresh at $X$: $(1,0)$, sign $0$. Apply $\textsf S$. Sign term $x z = 1\cdot 0 = 0$; then $z\,{\oplus}{=}\,x$ makes $(1,1)$.

**Result:** $\textsf H Z \textsf H = +X$ and $\textsf S X \textsf S^{\dagger} = +Y$ -- both with **+ signs**. Click *start: Z* then *H* above to reproduce the first; *start: X* then *S* for the second.

:::

## The CX gate -- where intuition breaks {#cx}

Here is the operation that confuses everyone. $\textsf{CX}$ with control $a$ and target $b$ updates a Pauli with qliff's exact rule -- read originals, set the sign, then edit the bits:

$$\text{sign}\,{\oplus}{=}\,x_a z_b (x_b{\oplus}z_a{\oplus}1), \qquad x_b\,{\oplus}{=}\,x_a, \qquad z_a\,{\oplus}{=}\,z_b.$$

Two bit copies fall out, and they go in *opposite directions*: $x_b\,{\oplus}{=}\,x_a$ copies the control's X-part **forward** onto the target, while $z_a\,{\oplus}{=}\,z_b$ copies the target's Z-part **backward** onto the control.

**CX propagator**

<SvelteIsland :component="CXDemo" />

*Choose an input Pauli, then read off CX·input·CX†. Control = q0, target = q1. (colors: X part copies forward, Z part copies backward, Y part, control / target qubit.)*

::: warning Control and target are NOT symmetric
Almost everyone expects CX to "copy the control onto the target" for everything. True for X -- but Z propagates the *other way*, target -> control. $\textsf{X}$ goes forward, $\textsf{Z}$ goes backward. This single fact is the source of almost every stabilizer-simulator bug.
:::

::: details Worked example: The two propagations, in bits

1. **X on the control.** $X_c$ is $x=(1,0),\,z=(0,0)$. Apply $x_b\,{\oplus}{=}\,x_a:\;x_1\,{\oplus}{=}\,1$ -> $x=(1,1)$. Now both qubits carry an X.
2. Sign term $x_a z_b(\dots)=1\cdot 0\cdot(\dots)=0$. Result: $X_c \to X_c X_t$, the **+** forward copy.
3. **Z on the target.** $Z_t$ is $x=(0,0),\,z=(0,1)$. Apply $z_a\,{\oplus}{=}\,z_b:\;z_0\,{\oplus}{=}\,1$ -> $z=(1,1)$. Now both qubits carry a Z.
4. Sign term $x_a z_b(\dots)=0\cdot 1\cdot(\dots)=0$. Result: $Z_t \to Z_c Z_t$, the **backward** copy.

**Result:** $X_c \to X_c X_t$ (forward) and $Z_t \to Z_c Z_t$ (backward), both **+**. Click <em>X<sub>c</sub></em> then <em>Z<sub>t</sub></em> above to watch the bits do exactly this.

:::

For contrast, $\textsf{CZ}$ *is* symmetric ($z_a\,{\oplus}{=}\,x_b,\; z_b\,{\oplus}{=}\,x_a$): it grows a Z on each qubit from the other's X, the same in both directions. And $\textsf{SWAP}=\textsf{CX}(a,b)\,\textsf{CX}(b,a)\,\textsf{CX}(a,b)$.

| CZ generator | → becomes |
| --- | --- |
| `X₀` | `+X₀Z₁` |
| `X₁` | `+Z₀X₁` |
| `Z₀` | `+Z₀` |

## Faults spread through entangling gates {#propagation}

Now the payoff for QEC. Because $\textsf{X}$ copies forward through every $\textsf{CX}$, a *single* fault before an entangling gate becomes a *multi-qubit* error after it. Below is a 4-qubit GHZ / cat-state encoder ($\textsf H\,q_0;\ \textsf{CX}\,0{\to}1;\ \textsf{CX}\,0{\to}2;\ \textsf{CX}\,0{\to}3$) -- the same fan-out of CX gates that a syndrome-extraction round uses. Inject a fault and scrub through the circuit to watch the Pauli "frame" spread.

**Error propagation through a GHZ encoder**

<SvelteIsland :component="PropagationDemo" />

*The boxed letter on each wire is the Pauli currently riding it. Faded gates haven't executed yet at this scrub step. (colors: X on a wire, Z on a wire, injected fault = ring, final support = dot.)*

::: details Worked example: One X on the control lights two detectors

1. Inject $X$ on $q_0$ just before $\textsf{CX}\,0{\to}1$ (set inject = X, qubit q0, before gate #1).
2. $\textsf{CX}\,0{\to}1$ sends $X_0 \to X_0 X_1$ -- the fault is now on *two* data qubits.
3. If $q_0$ also feeds $\textsf{CX}\,0{\to}2$ the X keeps copying forward: a chain of X's across the support.
4. On a 1-D code each flipped data qubit sits under a parity check, but only the **two ends** of the flipped chain break parity: every interior check sees two flips and stays quiet.

**Result:** One physical $X$ error -> a chain of flipped qubits whose **two endpoints light up**. That is precisely the "defects come in pairs" you met on the **matching** page: the two ends of a propagated error are the endpoints MWPM tries to reconnect.

:::

::: tip Why decoders see correlated checks
Propagation is what makes one fault touch several checks. The pairs MWPM matches, the correlated checks belief propagation reasons over, and the detector-error-model edges all trace back to this: a Pauli fault, conjugated forward through the circuit's CX gates, ends up supported on several detectors.
:::

## Signs, phases, and the only randomness {#signs}

The sign bit is small but load-bearing. $+Z$ stabilizes $\ket0$, so a $Z$ measurement returns **0**; $-Z$ stabilizes $\ket1$ and returns **1**. The sign *is* the measurement outcome. The CX sign term $x_a z_b(x_b{\oplus}z_a{\oplus}1)$ keeps these eigenvalues consistent as operators combine.

**Sign carries the outcome**

<SvelteIsland :component="SignsDemo" />

*An X flips +Z↔−Z, i.e. |0⟩↔|1⟩ -- the sign bit alone tracks the Z-measurement result. (colors: + sign → measures 0, − sign → measures 1.)*

::: info Gates are deterministic; only measurement rolls dice
Every gate on this page is a *deterministic* rewrite of operator bits -- nothing random. In a Clifford simulator the **only** source of randomness is measuring a Pauli that anticommutes with a stabilizer, where the outcome is a fair coin and the tableau is updated to match. That clean split -- deterministic operator updates, random only at measurement -- is what makes the whole scheme efficient and exactly samplable.
:::

## Why this scales -- and where it goes next {#scales}

Tally the cost. A single-qubit gate edits one column's bits; a $\textsf{CX}$ touches just **two** columns. Each gate is $O(n)$ bit operations across the rows, and the whole state is $O(n^2)$ bits -- versus $2^n$ complex amplitudes for a state vector. That gap is the entire reason qliff can simulate noisy circuits on thousands of qubits.

**Every gate as a bit rule**

| gate | sign ^= | bit update | effect |
| --- | --- | --- | --- |
| `H(a)` | `x_a · z_a` | `swap x_a ↔ z_a` | X↔Z, Y→−Y |
| `S(a)` | `x_a · z_a` | `z_a ^= x_a` | X→Y, Z→Z |
| `S†(a)` | `x_a · ¬z_a` | `z_a ^= x_a` | X→−Y |
| `X(a)` | `z_a` | -- | phase on Z,Y |
| `Z(a)` | `x_a` | -- | phase on X,Y |
| `Y(a)` | `x_a ^ z_a` | -- | phase on X,Z |
| `CX(a,b)` | `x_a·z_b·(x_b^z_a^1)` | `x_b ^= x_a; z_a ^= z_b` | X fwd, Z back |
| `CZ(a,b)` | `x_a·x_b·(z_a^z_b)` | `z_a ^= x_b; z_b ^= x_a` | symmetric |

*The complete rule set used on this page -- copied from qliff's tableau core. (The sign column is computed from the original bits.)*

::: tip Where these gates reappear
The Cliffords $\{\,I, Z, S, S^{\dagger}\,\}$ you met here are exactly the basis the **coherent-noise** page expands a small rotation into. And the faults you watched propagate through CX gates are the very edges that **MWPM**, **belief propagation**, and the **tensor-network** decoder consume. Operators in, operators out -- all the way up the stack.
:::
