# Getting Started

`aaronson` is a Clifford **+** noisy stabilizer simulator. The tableau lives in a
native Rust core (PyO3/maturin); everything you read, extend, or override is
plain Python. The API is stim-style uppercase, so circuits read the way you would
write them on paper.

::: warning Early development (0.1.0)
APIs may change freely pre-1.0.
:::

## Install

```sh
pip install aaronson
```

The wheel ships the compiled core, so no Rust toolchain is needed to use the
package. Verify the install:

```sh
python -c "from aaronson import Simulator; print(Simulator(2).H(0).CX(0,1).canonical_stabilizers())"
# ['+XX', '+ZZ']
```

## Core ideas

The library is built from four layers, each documented on its own page.

| Layer | Entry point | What it is |
| --- | --- | --- |
| State | [`Simulator`](/api) | A stabilizer state you drive imperatively with gates and measurements. |
| Program | [`Circuit`](/circuit) | A reusable instruction list with noise, detectors and observables. |
| Observables | [`PauliString`](/observables) | Pauli operators, expectations, and stabilizer-state fidelity. |
| Noise & QEC | [`noise`](/noise), [`qec`](/qec) | Importance-sampled noisy simulation and decoder-ready error-correction primitives. |

A `Simulator` is stateful and immediate — apply a gate and the tableau changes
now. A `Circuit` is a recipe — you build it once, then run it, sample it, or
hand it to a noise or QEC sampler. Use the simulator for interactive work and
classical feedback; use the circuit when you want to sample many shots or extract
an error model.

## Quickstart: a Bell state

The Bell pair is the "hello world" of stabilizer simulation. The `Simulator`
starts in $|0\dots0\rangle$; single-qubit gates take one or more targets,
two-qubit gates take flattened `(control, target)` pairs, and every gate method
returns `self` so calls chain.

```python
from aaronson import Simulator

sim = Simulator(2).H(0).CX(0, 1)   # (|00> + |11>) / sqrt(2)

sim.canonical_stabilizers()        # ['+XX', '+ZZ'] — stabilized by +XX and +ZZ
sim.peek_observable("ZZ")          # +1, read without collapsing the state
```

Measurements collapse the state and return classical bits; outcomes append to the
[`measure_record`](/api#measure-record).

```python
sim = Simulator(2, seed=0).H(0).CX(0, 1)
a, b = sim.M(0), sim.M(1)          # perfectly correlated: a == b
```

Because the simulator is stateful, **classical feedback is just Python** — no
special API is needed for teleportation or syndrome correction:

```python
sim = Simulator(3, seed=0)
sim.H(0)                            # message qubit
sim.H(1).CX(1, 2)                   # Bell pair on (1, 2)
sim.CX(0, 1).H(0)
if sim.M(1): sim.X(2)               # apply corrections conditioned on outcomes
if sim.M(0): sim.Z(2)
sim.peek_observable("__X")          # +1: |+> teleported to qubit 2
```

## Next steps

- [Simulator](/api) — the full gate, measurement, and inspection reference.
- [Circuit](/circuit) — build programs, sample shots, and auto-estimate observables.
- [Noise](/noise) — Pauli, coherent and amplitude-damping channels.
- [Error Correction](/qec) — detectors, error models, and ready-made codes.
