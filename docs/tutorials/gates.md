---
title: Gates in a Stabilizer Simulator
outline: 2
---

# Gates in a Stabilizer Simulator <Badge type="info" text="Tutorial 01 of 10" />

<script setup>
import HeisenbergDemo from '../_tut/gates/HeisenbergDemo.svelte'
import BitsDemo from '../_tut/gates/BitsDemo.svelte'
import SingleGateDemo from '../_tut/gates/SingleGateDemo.svelte'
import CXDemo from '../_tut/gates/CXDemo.svelte'
import PropagationDemo from '../_tut/gates/PropagationDemo.svelte'
import SignsDemo from '../_tut/gates/SignsDemo.svelte'
</script>

## Cliffords conjugate operators, not amplitudes {#heisenberg}

A general $n$-qubit state needs $2^n$ complex amplitudes, which is intractable past ~30 qubits. A **stabilizer simulator** sidesteps that entirely. Instead of the state vector it tracks the Pauli operators that *stabilize* the state: operators $S$ with $S\ket{\psi}=+\ket{\psi}$. The state is pinned down by its stabilizers, so we only ever store and update *operators*.

When a gate $U$ acts, every stabilizer is updated by **conjugation** in the Heisenberg picture, $S \mapsto U S U^{\dagger}$. Why that is the right rule:

$$(U S U^{\dagger})\,(U\ket{\psi}) = U S \ket{\psi} = U\ket{\psi},$$

so if $S$ stabilized the old state, $USU^{\dagger}$ stabilizes the new one $U\ket{\psi}$. No amplitudes appear: a Pauli goes in and a Pauli comes out. Press a gate and watch the single stabilizer of a 1-qubit state move, and the ket it pins down change with it.

**1-qubit stabilizer under a gate**

<SvelteIsland :component="HeisenbergDemo" />

::: tip Operators, never 2^n numbers
$H$ on $+Z$ (which is $\ket0$) gives $+X$ (which is $\ket+$), the Hadamard basis change. The whole simulation is bookkeeping on a handful of bits per operator, which is why qliff scales to thousands of qubits where a state vector cannot.
:::

## A Pauli is two bits plus a sign {#bits}

To compute with Paulis we encode each single-qubit factor as two bits (an x bit and a z bit) plus one global **sign** bit for the whole operator ($0=+$, $1=-$):

**Pauli ↔ bits**

<SvelteIsland :component="BitsDemo" />

::: info The full tableau
A stabilizer state of $n$ qubits is $n$ such rows (qliff stores $2n$ rows, the extra $n$ being destabilizers, but one conjugated row already tells the whole gate story). A gate edits these bits column by column; that is the entire engine.
:::

## Single-qubit gates are tiny bit ops {#single}

Each Clifford is a fixed recipe on the bits. The order matters: read the *original* $x,z$ to update the sign, *then* permute the bits:

$$\textsf{H}: \;\text{sign}\,{\oplus}{=}\,x z,\;\; x{\leftrightarrow}z \qquad \textsf{S}: \;\text{sign}\,{\oplus}{=}\,x z,\;\; z\,{\oplus}{=}\,x$$

$\textsf{X},\textsf{Z},\textsf{Y}$ never move bits at all; they only flip the sign when they anticommute with what is already there ($\textsf{X}{:}\,\text{sign}\,{\oplus}{=}\,z$, $\textsf{Z}{:}\,\text{sign}\,{\oplus}{=}\,x$). Pick a starting Pauli, apply gates, and watch the bits and the sign rule fire.

**Bit-level gate playground**

<SvelteIsland :component="SingleGateDemo" />

::: details Worked example: H on Z, then S on X (every number from the rules)

1. Start at $Z$: bits $(x,z)=(0,1)$, sign $0$.
2. Apply $\textsf{H}$. Sign term $x\cdot z = 0\cdot 1 = 0$, so sign stays $0$. Swap bits: $(0,1)\to(1,0)$.
3. $(1,0)$ with sign $0$ reads as $+X$. So $\textsf H Z\textsf H = X$. ✓
4. Now start fresh at $X$: $(1,0)$, sign $0$. Apply $\textsf S$. Sign term $x z = 1\cdot 0 = 0$; then $z\,{\oplus}{=}\,x$ makes $(1,1)$.

**Result:** $\textsf H Z \textsf H = +X$ and $\textsf S X \textsf S^{\dagger} = +Y$, both with **+ signs**. Click *start: Z* then *H* above to reproduce the first; *start: X* then *S* for the second.

:::

The H step of that example is four lines of arithmetic:

```python
x, z, sign = 0, 1, 0                    # start at +Z
sign = sign ^ (x & z)                   # H sign term, from the original bits
x, z = z, x                             # H swaps x and z
print(("+" if sign == 0 else "-") + "IXZY"[x + 2 * z])  # -> +X
```

## The CX gate: two propagation directions {#cx}

The two-qubit case follows the same recipe, with one asymmetry. $\textsf{CX}$ with control $a$ and target $b$ updates a Pauli with qliff's rule (read the original bits, set the sign, then edit the bits):

$$\text{sign}\,{\oplus}{=}\,x_a z_b (x_b{\oplus}z_a{\oplus}1), \qquad x_b\,{\oplus}{=}\,x_a, \qquad z_a\,{\oplus}{=}\,z_b.$$

Two bit copies fall out, and they go in *opposite directions*: $x_b\,{\oplus}{=}\,x_a$ copies the control's X-part **forward** onto the target, while $z_a\,{\oplus}{=}\,z_b$ copies the target's Z-part **backward** onto the control.

**CX propagator**

<SvelteIsland :component="CXDemo" />

::: warning Control and target are NOT symmetric
A natural guess is that CX copies the control onto the target for everything. That holds for X, but Z propagates the *other way*, target -> control. $\textsf{X}$ goes forward, $\textsf{Z}$ goes backward. Getting this direction wrong is a common source of stabilizer-simulator bugs.
:::

::: details Worked example: The two propagations, in bits

1. **X on the control.** $X_c$ is $x=(1,0),\,z=(0,0)$. Apply $x_b\,{\oplus}{=}\,x_a:\;x_1\,{\oplus}{=}\,1$ -> $x=(1,1)$. Now both qubits carry an X.
2. Sign term $x_a z_b(\dots)=1\cdot 0\cdot(\dots)=0$. Result: $X_c \to X_c X_t$, the **+** forward copy.
3. **Z on the target.** $Z_t$ is $x=(0,0),\,z=(0,1)$. Apply $z_a\,{\oplus}{=}\,z_b:\;z_0\,{\oplus}{=}\,1$ -> $z=(1,1)$. Now both qubits carry a Z.
4. Sign term $x_a z_b(\dots)=0\cdot 1\cdot(\dots)=0$. Result: $Z_t \to Z_c Z_t$, the **backward** copy.

**Result:** $X_c \to X_c X_t$ (forward) and $Z_t \to Z_c Z_t$ (backward), both **+**. Click <em>X<sub>c</sub></em> then <em>Z<sub>t</sub></em> above to watch the bits do this.

:::

For contrast, $\textsf{CZ}$ *is* symmetric ($z_a\,{\oplus}{=}\,x_b,\; z_b\,{\oplus}{=}\,x_a$): it grows a Z on each qubit from the other's X, the same in both directions. And $\textsf{SWAP}=\textsf{CX}(a,b)\,\textsf{CX}(b,a)\,\textsf{CX}(a,b)$.

| CZ generator | → becomes |
| --- | --- |
| `X₀` | `+X₀Z₁` |
| `X₁` | `+Z₀X₁` |
| `Z₀` | `+Z₀` |

## Faults spread through entangling gates {#propagation}

This propagation is what QEC cares about. Because $\textsf{X}$ copies forward through every $\textsf{CX}$, a *single* fault before an entangling gate becomes a *multi-qubit* error after it. Below is a 4-qubit GHZ / cat-state encoder ($\textsf H\,q_0;\ \textsf{CX}\,0{\to}1;\ \textsf{CX}\,0{\to}2;\ \textsf{CX}\,0{\to}3$), the same fan-out of CX gates that a syndrome-extraction round uses. Inject a fault and scrub through the circuit to watch the Pauli "frame" spread.

**Error propagation through a GHZ encoder**

<SvelteIsland :component="PropagationDemo" />

::: details Worked example: One X on the control lights two detectors

1. Inject $X$ on $q_0$ just before $\textsf{CX}\,0{\to}1$ (set inject = X, qubit q0, before gate #1).
2. $\textsf{CX}\,0{\to}1$ sends $X_0 \to X_0 X_1$: the fault is now on *two* data qubits.
3. If $q_0$ also feeds $\textsf{CX}\,0{\to}2$ the X keeps copying forward: a chain of X's across the support.
4. On a 1-D code each flipped data qubit sits under a parity check, but only the **two ends** of the flipped chain break parity: every interior check sees two flips and stays quiet.

**Result:** One physical $X$ error -> a chain of flipped qubits whose **two endpoints light up**. That is precisely the "defects come in pairs" you met on the **matching** page: the two ends of a propagated error are the endpoints MWPM tries to reconnect.

:::

::: tip Why decoders see correlated checks
Propagation is what makes one fault touch several checks. The pairs MWPM matches, the correlated checks belief propagation reasons over, and the detector-error-model edges all trace back to this: a Pauli fault, conjugated forward through the circuit's CX gates, ends up supported on several detectors.
:::

## Signs, phases, and the only randomness {#signs}

The sign bit is more than bookkeeping. $+Z$ stabilizes $\ket0$, so a $Z$ measurement returns **0**; $-Z$ stabilizes $\ket1$ and returns **1**. The sign *is* the measurement outcome. The CX sign term $x_a z_b(x_b{\oplus}z_a{\oplus}1)$ keeps these eigenvalues consistent as operators combine.

**Sign carries the outcome**

<SvelteIsland :component="SignsDemo" />

::: info Gates are deterministic; only measurement rolls dice
Every gate on this page is a *deterministic* rewrite of operator bits; nothing is random. In a Clifford simulator the **only** source of randomness is measuring a Pauli that anticommutes with a stabilizer, where the outcome is a fair coin and the tableau is updated to match. That split (deterministic operator updates, randomness only at measurement) is what makes the whole scheme efficient and exactly samplable.
:::

## Why this scales, and where it goes next {#scales}

Tally the cost. A single-qubit gate edits one column's bits; a $\textsf{CX}$ touches only **two** columns. Each gate is $O(n)$ bit operations across the rows, and the whole state is $O(n^2)$ bits, versus $2^n$ complex amplitudes for a state vector. That gap is the entire reason qliff can simulate noisy circuits on thousands of qubits.

**Every gate as a bit rule**

| gate | sign ^= | bit update | effect |
| --- | --- | --- | --- |
| `H(a)` | `x_a · z_a` | `swap x_a ↔ z_a` | X↔Z, Y→−Y |
| `S(a)` | `x_a · z_a` | `z_a ^= x_a` | X→Y, Z→Z |
| `S†(a)` | `x_a · ¬z_a` | `z_a ^= x_a` | X→−Y |
| `X(a)` | `z_a` | (none) | phase on Z,Y |
| `Z(a)` | `x_a` | (none) | phase on X,Y |
| `Y(a)` | `x_a ^ z_a` | (none) | phase on X,Z |
| `CX(a,b)` | `x_a·z_b·(x_b^z_a^1)` | `x_b ^= x_a; z_a ^= z_b` | X fwd, Z back |
| `CZ(a,b)` | `x_a·x_b·(z_a^z_b)` | `z_a ^= x_b; z_b ^= x_a` | symmetric |

*The complete rule set used on this page, copied from qliff's tableau core. (The sign column is computed from the original bits.)*

## Implementation {#implementation}

The table above is the whole engine. The tabs below write it down three ways: pseudocode for the row update (the invariant is the order: the sign term reads the original bits, and only then do the bits move), a minimal NumPy version whose prints reproduce every worked example on this page, and the same checks through qliff's API, where `Simulator(n)` starts in $\ket{0\cdots0}$, gate methods conjugate the stored stabilizers in place (and return `self`, so they chain), and `stabilizers()` reads back the signed rows.

::: code-group

```text [Pseudocode]
apply_gate(row, gate):
    # row = (x[0..n), z[0..n), sign): one conjugated Pauli
    # step 1: fold the ORIGINAL bits into the sign
    # step 2: permute or XOR the bits

    H(a):
        sign ^= x[a] AND z[a]
        swap x[a], z[a]

    S(a):
        sign ^= x[a] AND z[a]
        z[a] ^= x[a]

    CX(a, b):                # a = control, b = target
        sign ^= x[a] AND z[b] AND (x[b] XOR z[a] XOR 1)
        x[b] ^= x[a]         # X copies forward (control to target)
        z[a] ^= z[b]         # Z copies backward (target to control)
```

```python [Std Python]
import numpy as np

X_BITS = {"I": 0, "X": 1, "Y": 1, "Z": 0}
Z_BITS = {"I": 0, "X": 0, "Y": 1, "Z": 1}


def row(letters):
    """One tableau row: x bits, z bits, sign bit (0 = +, 1 = -)."""
    x = np.array([X_BITS[c] for c in letters], dtype=np.uint8)
    z = np.array([Z_BITS[c] for c in letters], dtype=np.uint8)
    return x, z, 0


def show(x, z, sign):
    body = "".join("IXZY"[int(x[j]) + 2 * int(z[j])] for j in range(len(x)))
    return ("-" if sign == 1 else "+") + body


def H(x, z, sign, a):
    sign = sign ^ int(x[a] & z[a])  # sign from the ORIGINAL bits
    x[a], z[a] = z[a], x[a]
    return sign


def S(x, z, sign, a):
    sign = sign ^ int(x[a] & z[a])
    z[a] = z[a] ^ x[a]
    return sign


def CX(x, z, sign, a, b):
    sign = sign ^ int(x[a] & z[b] & (x[b] ^ z[a] ^ 1))
    x[b] = x[b] ^ x[a]  # X copies forward: control -> target
    z[a] = z[a] ^ z[b]  # Z copies backward: target -> control
    return sign


x, z, sign = row("Z")
sign = H(x, z, sign, 0)
print("H Z H     =", show(x, z, sign))  # -> H Z H     = +X

x, z, sign = row("X")
sign = S(x, z, sign, 0)
print("S X S_dag =", show(x, z, sign))  # -> S X S_dag = +Y

x, z, sign = row("Y")
sign = H(x, z, sign, 0)
print("H Y H     =", show(x, z, sign))  # -> H Y H     = -Y

x, z, sign = row("XI")
sign = CX(x, z, sign, 0, 1)
print("CX on X_c =", show(x, z, sign))  # -> CX on X_c = +XX

x, z, sign = row("IZ")
sign = CX(x, z, sign, 0, 1)
print("CX on Z_t =", show(x, z, sign))  # -> CX on Z_t = +ZZ
```

```python [Qliff]
from qliff import Simulator

# |0> is stabilized by +Z; H conjugates it to +X (H Z H = +X)
sim = Simulator(1)
print(sim.stabilizers())  # -> ['+Z']
sim.H(0)
print(sim.stabilizers())  # -> ['+X']

# S sends +X to +Y (S X S_dag = +Y)
sim.S(0)
print(sim.stabilizers())  # -> ['+Y']

# CX: X on the control copies forward, Z on the target copies backward
sim = Simulator(2)
sim.H(0)
print(sim.stabilizers())  # -> ['+XI', '+IZ']
sim.CX(0, 1)
print(sim.stabilizers())  # -> ['+XX', '+ZZ']

# the sign is the measurement outcome: X flips +Z to -Z, so M reads 1
sim = Simulator(1)
sim.X(0)
print(sim.stabilizers())  # -> ['-Z']
print(sim.M(0))           # -> 1
```

:::

::: tip Where these gates reappear
The Cliffords $\{\,I, Z, S, S^{\dagger}\,\}$ you met here are the basis the **coherent-noise** page expands a small rotation into. And the faults you watched propagate through CX gates are the edges that **MWPM**, **belief propagation**, and the **tensor-network** decoder consume. Operators in, operators out, all the way up the stack.
:::
