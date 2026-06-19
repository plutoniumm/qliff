# Circuits

Stateful `Simulator` work and reusable `Circuit` sampling. Every gate returns
`self`, so calls chain; classical feedback is just plain Python.

## Bell state and its stabilizers

Prepare $|\Phi^+\rangle = (|00\rangle + |11\rangle)/\sqrt{2}$ and read its
canonical stabilizer generators.

```python
from qliff import Simulator

sim = Simulator(2).H(0).CX(0, 1)
sim.canon()        # ['+XX', '+ZZ']
```

The state is stabilized by $+XX$ and $+ZZ$.

## GHZ state on $n$ qubits

Spread one Hadamard across a CX chain to build
$|\mathrm{GHZ}_n\rangle = (|0\dots0\rangle + |1\dots1\rangle)/\sqrt{2}$.

```python
from qliff import Simulator

n = 4
sim = Simulator(n).H(0)
for q in range(n - 1):
    sim.CX(q, q + 1)

sim.canon()        # ['+XXXX', '+ZIIZ', '+IZIZ', '+IIZZ']
```

The generators are $X^{\otimes n}$ plus the neighbouring $Z_iZ_{i+1}$ parities.

## Sample measurement bitstrings

Build a circuit, measure, and draw many shots at once with `Circuit.sample`.

```python
from qliff import Circuit

c = Circuit(2)
c.H(0).CX(0, 1).M(0, 1)

shots = c.sample(1000, seed=0)
```

Every record is `[0, 0]` or `[1, 1]` — the two Bell outcomes, in equal
proportion.

## Mid-circuit measurement and reset

Use `M`/`MR`/`R` mid-circuit and read the running outcomes off `sim.record`.

```python
from qliff import Simulator

sim = Simulator(1, seed=0)
sim.H(0)
sim.MR(0)
sim.X(0)
sim.M(0)

sim.record         # e.g. [0, 1] or [1, 1]
```

`record` lists past outcomes in order; `MR` collapses then resets, so the final
`M` is deterministic. Call `sim.clear()` to empty the record.

## Classically-conditioned correction: teleportation

Teleport a state from qubit 0 onto qubit 2, applying Pauli corrections
conditioned on the two measured bits.

```python
from qliff import Simulator

sim = Simulator(3, seed=0)
sim.H(0)
sim.H(1).CX(1, 2)
sim.CX(0, 1).H(0)
if sim.M(1) == 1:
    sim.X(2)
if sim.M(0) == 1:
    sim.Z(2)

sim.peek("__X")        # +1
```

The message lands on qubit 2 regardless of the random outcomes:
$\langle X\rangle = +1$.

## Read $\langle P\rangle$ without collapse

`peek` returns $\langle P\rangle \in \{-1, 0, +1\}$ and leaves the state
untouched.

```python
from qliff import Simulator

sim = Simulator(2).H(0).CX(0, 1)
sim.peek("ZZ")         # +1
sim.peek("ZI")         # 0
```

A `0` means the state is not an eigenstate of `P`; the simulator is unchanged, so
you can keep going.
