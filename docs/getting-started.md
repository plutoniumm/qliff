# Getting Started

`qliff` is a Clifford **+** noisy stabilizer simulator.

- **Fast core, Python surface.** The tableau lives in a native Rust core (PyO3 + setuptools-rust); everything you read, extend, or override is plain Python.
- **Reads like paper.** The API is stim-style uppercase, so circuits look the way you write them by hand.

::: tip Stable API (1.0.0)
The public API is stable; breaking changes bump the major version.
:::

## Install

```sh
pip install qliff
```

The wheel ships the compiled core — no Rust toolchain needed. Verify it:

```sh
python -c "from qliff import Simulator; print(Simulator(2).H(0).CX(0,1).canon())"
# ['+XX', '+ZZ']
```

## Core ideas

Four layers, each with its own page:

| Layer | Entry point | What it is |
| --- | --- | --- |
| State | [`Simulator`](/api) | A stabilizer state you drive imperatively with gates and measurements. |
| Program | [`Circuit`](/circuit) | A reusable instruction list with noise, detectors and observables. |
| Observables | [`PauliString`](/observables) | Pauli operators, expectations, and stabilizer-state fidelity. |
| Noise & QEC | [`noise`](/noise), [`qec`](/qec) | Importance-sampled noisy simulation and decoder-ready error-correction primitives. |

`Simulator` vs `Circuit`:

- **`Simulator`** — stateful and immediate. Apply a gate, the tableau changes now. Use it for interactive work and classical feedback.
- **`Circuit`** — a recipe. Build once, then run, sample, or hand to a noise/QEC sampler. Use it to sample many shots or extract an error model.

## Quickstart: a Bell state

The Bell pair is the "hello world" of stabilizer simulation. Three conventions:

- The `Simulator` starts in $|0\dots0\rangle$.
- Single-qubit gates take one or more targets; two-qubit gates take flattened `(control, target)` pairs.
- Every gate method returns `self`, so calls chain.

```python
from qliff import Simulator

sim = Simulator(2).H(0).CX(0, 1)

sim.canon()        # ['+XX', '+ZZ']
sim.peek("ZZ")     # +1
```

Measurements collapse the state and return classical bits. Outcomes append to the
[`record`](/api#record):

```python
sim = Simulator(2, seed=0).H(0).CX(0, 1)
a, b = sim.M(0), sim.M(1)
```

The simulator is stateful, so **classical feedback is just Python** — teleportation
and syndrome correction need no special API:

```python
sim = Simulator(3, seed=0)
sim.H(0)
sim.H(1).CX(1, 2)
sim.CX(0, 1).H(0)
if sim.M(1) == 1:
    sim.X(2)
if sim.M(0) == 1:
    sim.Z(2)
sim.peek("IIX")          # +1
```

## Next steps

- [Simulator](/api) — the full gate, measurement, and inspection reference.
- [Circuit](/circuit) — build programs, sample shots, and auto-estimate observables.
- [Noise](/noise) — Pauli, coherent and amplitude-damping channels.
- [Error Correction](/qec) — detectors, error models, and ready-made codes.
