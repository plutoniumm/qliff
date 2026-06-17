# Simulator API

The top-level surface:

```python
from aaronson import Simulator, Circuit, PauliString, expectation, state_fidelity
```

- [`Simulator`](#simulator) — the ergonomic, stim-style facade you will use most.
- `Circuit` — a stim-like IR with noise, detectors and observables; see
  [Noise](/noise) and [Error Correction](/qec).
- `PauliString`, `expectation`, `state_fidelity` — Pauli observables and metrics.
- `Tableau` — the lower-level native CHP tableau that `Simulator` wraps.
- `__version__` — the package version (sourced from the Rust crate).

This page documents `Simulator`.

## `Simulator`

```python
Simulator(num_qubits, seed=None)
```

A Clifford stabilizer simulator. It starts in the all-zero state
$|0\dots0\rangle$. Pass an integer `seed` to make measurement sampling
reproducible.

Gate methods **return `self`**, so operations chain:

```python
from aaronson import Simulator

print(Simulator(2).H(0).CX(0, 1).canonical_stabilizers())
# ['+XX', '+ZZ']
```

### Target conventions

- **Single-qubit gates** accept one or more targets: `sim.H(0)` or
  `sim.X(0, 1, 2)` applies the gate to each listed qubit.
- **Two-qubit gates** take flattened `(control, target)` pairs:
  `sim.CX(0, 1)` is one CX; `sim.CX(0, 1, 2, 3)` applies CX(0->1) then
  CX(2->3). An odd number of targets raises `ValueError`.
- Iterables are flattened too, so `sim.H([0, 1])` works.

## Single-qubit gates

Each returns `self`. Accepts one or more targets.

| Method | Gate |
| ------ | ---- |
| `H(*q)` | Hadamard |
| `S(*q)` | Phase ($S$), maps $X \to Y$ |
| `S_DAG(*q)` | Inverse phase ($S^\dagger$) |
| `X(*q)` | Pauli $X$ |
| `Y(*q)` | Pauli $Y$ |
| `Z(*q)` | Pauli $Z$ |

```python
from aaronson import Simulator

# S maps X -> Y, so H then S takes |0> to the +Y eigenstate.
print(Simulator(1).H(0).S(0).canonical_stabilizers())
# ['+Y']
```

## Two-qubit gates

Each returns `self`. Takes flattened `(control, target)` pairs.

| Method | Gate |
| ------ | ---- |
| `CX(*t)` | Controlled-$X$ (CNOT) |
| `CNOT(*t)` | Alias for `CX` |
| `CZ(*t)` | Controlled-$Z$ |
| `SWAP(*t)` | Swap two qubits |

```python
from aaronson import Simulator

# GHZ_3 by chaining CX(0->1) then CX(1->2).
ghz = Simulator(3).H(0).CX(0, 1, 1, 2)
print(ghz.canonical_stabilizers())
# ['+XXX', '+ZZI', '+IZZ']
```

## Measurement and reset

| Method | Returns | Description |
| ------ | ------- | ----------- |
| `M(*q)` | `int` or `list[int]` | Measure in the $Z$ basis, collapsing the state. Single target -> `int`; several -> `list`. Appends to `measure_record`. |
| `MR(*q)` | `int` or `list[int]` | Measure, then reset the measured qubit(s) to $|0\rangle$. |
| `R(*q)` | `self` | Reset qubit(s) to $|0\rangle$. |
| `reset(*q)` | `self` | Alias for `R`. |

```python
from aaronson import Simulator

s = Simulator(2).X(0)
print(s.M(0), s.M(1))   # 1 0
print(s.measure_record) # [1, 0]
```

### `measure_record`

```python
sim.measure_record  # -> list[int]
```

The measurement outcomes recorded so far, in order. `clear_record()` empties it
and returns `self`.

## Inspection

### `num_qubits`

```python
sim.num_qubits  # -> int
```

The number of qubits in the register.

### `copy()`

```python
sim.copy()  # -> Simulator
```

A deep copy of the simulator (independent tableau). Useful for testing whether a
measurement is deterministic without disturbing the original state.

### `stabilizers()`

```python
sim.stabilizers()  # -> list[str]
```

The **raw** (non-canonical) signed-Pauli generators, e.g. `'+XX'`, `'-Z'`. These
depend on the gate history.

### `canonical_stabilizers()`

```python
sim.canonical_stabilizers()  # -> list[str]
```

The **canonical** signed-Pauli generators: a unique reduced form for the
stabilizer group. Two simulators describe the same state **iff** their canonical
stabilizers are equal, which makes this the right tool for equality checks.

```python
from aaronson import Simulator

a = Simulator(2).H(0).CX(0, 1)
b = Simulator(2).H(1).CX(1, 0)
assert a.canonical_stabilizers() == b.canonical_stabilizers()
```

## Observables

Two methods read or measure a Pauli operator on the state. Both take a
`PauliString` or a signed string like `"ZZ"` or `"-X"`.

| Method | Returns | Description |
| --- | --- | --- |
| `peek_observable(P)` | `-1 \| 0 \| +1` | $\langle P\rangle$ **without** collapsing the state (`0` if not an eigenstate) |
| `measure_pauli(P, force=None)` | `(value, random)` | **measure** $P$ in place; `value` in `{+1,-1}`, `random` flags a coin flip |

```python
bell = Simulator(2).H(0).CX(0, 1)
bell.peek_observable("ZZ")   # +1, no collapse
bell.measure_pauli("XX")     # (1, False)
```

`measure_pauli` collapses the state and works on multi-qubit stabilizers — the
primitive behind syndrome extraction; pin a random outcome with `force=+1`/`-1`.
See [Observables & Metrics](/observables) for `PauliString`, the `expectation`
free function, and `state_fidelity`.
