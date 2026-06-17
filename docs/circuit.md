# Circuit

A `Circuit` is a stim-like instruction list: gates, noise, measurements,
detectors and observables, recorded once and reused. You build it with the same
uppercase methods as the [`Simulator`](/api), then run it, sample it, or hand it
to a noise or QEC sampler.

```python
from aaronson import Circuit

c = Circuit(2)
c.H(0).CX(0, 1).M(0, 1)   # methods return self, so calls chain
```

`Circuit(num_qubits=0)` grows its width automatically as you reference higher
qubit indices, so the argument is only a hint.

## Building blocks

Every instruction is a triple `(name, targets, arg)`. The fluent methods are thin
wrappers over [`append`](#low-level-and-custom-channels); use whichever reads
better.

### Gates and measurement

These mirror the simulator exactly and take one or more targets (two-qubit gates
take flattened `(control, target)` pairs).

| Method | Effect |
| --- | --- |
| `H, S, S_DAG, X, Y, Z` | single-qubit Clifford gates |
| `CX` (`CNOT`), `CZ`, `SWAP` | two-qubit Clifford gates |
| `M(*q)` | measure in the $Z$ basis (appends to the record) |
| `MR(*q)` | measure, then reset to $\|0\rangle$ |
| `R(*q)` | reset to $\|0\rangle$ |

### Noise

Noise methods take the target(s) first, then the channel parameter. See
[Noise](/noise) for the channels themselves.

| Method | Parameter | Channel |
| --- | --- | --- |
| `DEPOLARIZE1(q, p)` | $p$ | single-qubit depolarizing |
| `DEPOLARIZE2(pair, p)` | $p$ | two-qubit depolarizing |
| `X_ERROR(q, p)`, `Z_ERROR(q, p)` | $p$ | bit-flip / phase-flip |
| `PAULI_CHANNEL_1(q, (px,py,pz))` | tuple | arbitrary 1-qubit Pauli channel |
| `RZ(q, theta)`, `RX(q, theta)` | $\theta$ | coherent rotation |
| `AMPLITUDE_DAMP(q, p)` | $p$ | amplitude damping (non-unitary) |

### Detectors and observables

A **detector** is a set of measurement records whose parity is deterministic in
the noiseless circuit; a **observable** is a logical degree of freedom tracked
across the run. Record indices use stim's `rec[-1]` convention — negative indices
count back from the measurements declared so far.

| Method | Description |
| --- | --- |
| `detector(*recs)` | declare a detector over the given measurement records |
| `observable(index, *recs)` | declare logical observable `index` over records |

```python
c = Circuit(1)
c.M(0)            # rec[-2] after the next line
c.X_ERROR(0, 0.1)
c.M(0)            # rec[-1]
c.detector(-1, -2)   # parity of the two measurements
c.observable(0, -1)
```

## Running and sampling

| Method | Returns | Description |
| --- | --- | --- |
| `run(seed=None)` | `Simulator` | apply a **noiseless** circuit and return the final state; raises if it contains noise |
| `sample(shots, seed=None)` | `list[list[int]]` | measurement records over `shots` Pauli-noise trajectories |
| `estimate(observable, shots=10000, method="auto", seed=None)` | `float` | reweighted estimate of $\langle O\rangle$ |
| `detector_sampler()` | `DetectorSampler` | a sampler of detection events (see [QEC](/qec)) |
| `dem()` | `DetectorErrorModel` | the detector error model (see [QEC](/qec)) |

`estimate` chooses the sampler for you: plain Monte-Carlo when every channel is
Pauli, otherwise the stratified importance sampler that stays unbiased for
coherent and non-unitary noise. Override it with `method`:

| `method` | Sampler | Use when |
| --- | --- | --- |
| `"auto"` | picks below | default |
| `"montecarlo"` | `MonteCarlo` | all channels are Pauli |
| `"importance"` | `ImportanceSampler` | flat importance sampling |
| `"stratified"` | `StratifiedSampler` | general noise, lowest variance |

```python
c = Circuit(1)
c.H(0).RZ(0, 0.3)
c.estimate("X", 20000)          # ~ cos(0.3), auto-stratified
c.estimate("X", 20000, method="importance")
```

## Properties

| Property | Description |
| --- | --- |
| `num_qubits` | register width (grows as instructions are added) |
| `num_measurements` | count of `M`/`MR` outcomes recorded so far |
| `instructions` | the underlying `(name, targets, arg)` list |
| `detectors`, `observables` | the declared detectors and observables |
| `is_pauli` | `True` if every noise instruction is a Pauli channel |

## Low-level and custom channels

`append(name, targets, arg=None)` adds any instruction directly, and
`noise(channel, *targets)` drops in a custom [`Channel`](/noise#custom-channels)
instance:

```python
from aaronson.noise import BitFlip

c = Circuit(1)
c.append("H", 0)            # equivalent to c.H(0)
c.noise(BitFlip(0.1), 0)    # any Channel subclass works
```
