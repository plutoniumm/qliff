# Observables & Metrics

A `PauliString` is an $n$-qubit Pauli operator. The `metrics` helpers read
expectations and state fidelities off a simulator. Together they cover the
"measure something" half of the library, complementing the gates and channels.

## PauliString

A `PauliString` stores $i^{\,\text{phase}}\,P_1\otimes\cdots\otimes P_n$ as $X$
and $Z$ bit lists plus a phase in $0\ldots3$: $0\to+1$, $1\to+i$, $2\to-1$,
$3\to-i$. Valid observables are Hermitian, i.e. have even phase.

```python
from aaronson import PauliString

p = PauliString.parse("-XYZ")   # phase 2, then X, Y, Z
```

### Constructors

| Constructor | Description |
| --- | --- |
| `PauliString(x, z, phase=0)` | from explicit $X$/$Z$ bit lists |
| `PauliString.parse(s)` | from a string: `"+XYZ"`, `"-Y"`, `"+iXZ"`, `"X_Z"` (`_` = identity) |
| `PauliString.identity(n)` | the $n$-qubit identity |
| `PauliString.from_sparse(n, ops, phase=0)` | from `{qubit: 'X'\|'Y'\|'Z'}`, others identity |

### Properties and methods

| Property/Method | Description |
| --- | --- |
| `x`, `z`, `phase` | the $X$/$Z$ bit lists and the phase (`0..3`) |
| `n` | number of qubits |
| `tuple()` | `(sign, x, z)` with `sign` in `{0,1}`; raises for non-Hermitian phases |
| `commutes_with(other)` | whether the two Paulis commute |
| `a * b` | Pauli product, tracking the $i$ phase exactly |

```python
from aaronson import PauliString

x = PauliString.parse("X")
z = PauliString.parse("Z")

(x * z)                         # -iY  (phase tracked)
x.commutes_with(z)              # False
PauliString.from_sparse(3, {0: "X", 2: "Z"})   # +XIZ
```

## Reading observables

Both live on the [`Simulator`](/api). `expectation` is a free-function alias for
`peek`. `P` is a `PauliString` or a signed string such as `"ZZ"` or `"-X"`.

| Call | Returns | Description |
| --- | --- | --- |
| `sim.peek(P)` | `-1 \| 0 \| +1` | $\langle P\rangle$ **without** collapsing the state |
| `expectation(sim, P)` | `-1 \| 0 \| +1` | free-function form of the above |
| `sim.measure(P, force=None)` | `(value, random)` | **measure** $P$ in place; `value` in `{+1,-1}` |

- `peek` returns $\langle P\rangle$ and never collapses. A `0` means the state is
  not an eigenstate of `P`.
- `measure` collapses the state, returning the eigenvalue and whether the outcome
  was a coin flip. It handles multi-qubit stabilizers — the primitive behind
  syndrome extraction.
- `force=+1` / `force=-1` pins a random outcome, projecting onto a chosen
  eigenspace.

```python
from aaronson import Simulator

bell = Simulator(2).H(0).CX(0, 1)

bell.peek("ZZ")             # +1, no collapse
bell.measure("XX")          # (1, False): deterministic +1
Simulator(2).measure("XX")  # (±1, True): random on |00>
```

## State fidelity

`fidelity(a, b)` returns the exact overlap $|\langle a|b\rangle|^2$ between two
simulators' stabilizer states. It measures each stabilizer generator of `a` on a
copy of `b`, so the result is always a power of two.

```python
from aaronson import Simulator, fidelity

fidelity(Simulator(1), Simulator(1).H(0))   # 0.5  (|0> vs |+>)

a = Simulator(2).H(0).CX(0, 1)
fidelity(a, a.copy())                        # 1.0
fidelity(a, a.copy().Z(0))                   # 0.0  (|Phi+> vs |Phi->)
```
