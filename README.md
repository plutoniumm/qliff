# aaronson

A Clifford + noisy stabilizer simulator with a native Rust core.

- **Noise-free Clifford simulation** via the CHP / Aaronson–Gottesman tableau (bit-packed,
  in Rust), with a stim-style uppercase API (`H`, `S`, `CX`, `CZ`, `M`, `R`, …). Verified
  against [stim](https://github.com/quantumlib/Stim) on random Clifford circuits.
- **Noisy simulation of general — including coherent — noise** via stabilizer-channel
  decomposition `E = Σ_μ q_μ S_μ` and **stratified importance sampling**
  ([arXiv:2512.07304](https://arxiv.org/abs/2512.07304)), "nearly as cheap as Pauli noise."
- **Decoder-ready QEC primitives**: detectors, observables, detection-event sampling, a
  detector error model by exact Pauli-frame propagation, and exporters (parity-check matrix +
  priors, matching weights, syndrome/label tensors). No decoder is bundled — these drop
  straight into MWPM (pymatching), BP, or ML decoders.

> 🚧 Early development (0.1.0). APIs may change freely pre-1.0.

## Install

```sh
pip install aaronson
```

Full documentation (quickstart, Simulator, Circuit, observables, noise, QEC) lives at
[plutoniumm.github.io/aaronson](https://plutoniumm.github.io/aaronson/).

## Clifford simulation

```python
from aaronson import Simulator, state_fidelity

s = Simulator(2).H(0).CX(0, 1)        # Bell state (gates chain)
s.canonical_stabilizers()              # ['+XX', '+ZZ']
s.peek_observable("ZZ")                # +1   (read an expectation, no collapse)
s.measure_pauli("XX")                  # (+1, False) — multi-qubit stabilizer measurement

m0, m1 = Simulator(2).H(0).CX(0, 1).M(0, 1)   # correlated: m0 == m1
```

Mid-circuit measurement and classical feedback are just Python — the simulator is stateful,
so conditionals (teleportation, syndrome correction) need no special API:

```python
s = Simulator(3, seed=0)
s.H(0)                                  # message qubit
s.H(1).CX(1, 2)                         # Bell pair
s.CX(0, 1).H(0)
if s.M(1): s.X(2)                       # classical feedback
if s.M(0): s.Z(2)
s.peek_observable("__X")                # +1: state teleported to qubit 2
```

## Noise

Build a `Circuit` with fluent gate/noise methods, then sample or estimate. `Circuit.estimate`
picks the right sampler by default — plain Monte-Carlo when every channel is Pauli, otherwise
stratified importance sampling (unbiased even for coherent/non-unitary noise).

```python
from aaronson import Circuit

# Pauli noise
c = Circuit(1)
c.H(0).DEPOLARIZE1(0, 0.1).M(0)
c.sample(1000)                          # measurement records

# coherent noise: <X> after a small Z-rotation, reproduced exactly
c = Circuit(1)
c.H(0).RZ(0, 0.3)
c.estimate("X", 20000)                  # ≈ cos(0.3), auto-stratified

# general non-unitary noise: amplitude damping (arXiv:2512.07304)
c = Circuit(1)
c.X(0).AMPLITUDE_DAMP(0, 0.3)
c.estimate("Z", 60000)                  # ≈ 2p - 1, matches the exact channel
```

Override the auto choice with `c.estimate(obs, shots, method="importance")`, or drive a sampler
directly: `from aaronson.noise import MonteCarlo, ImportanceSampler, StratifiedSampler`. Add a
custom channel by subclassing `aaronson.noise.Channel` and dropping it in with `c.noise(ch, q)`.

## Quantum error correction

`aaronson.qec` ships code-circuit generators, so you can go straight to a logical-error-rate
curve. Any circuit's detectors and observables are declared with `c.detector(...)` /
`c.observable(...)`, then turned into decoder inputs:

```python
from aaronson.qec import rotated_surface_code, logical_fidelity
import pymatching

c = rotated_surface_code(distance=5, rounds=5, p=0.01)
dem = c.dem()                                            # detector error model
H, priors, obs_matrix = dem.check_matrix()               # feed BP, or MWPM:
m = pymatching.Matching.from_check_matrix(H, weights=dem.weights(), faults_matrix=obs_matrix)

dets, flips = c.detector_sampler().sample(20000)         # syndrome + label tensors (numpy)
fidelity = logical_fidelity(m.decode_batch(dets), flips) # 1 - logical error rate
```

Both the repetition and rotated surface codes show the logical error rate falling with
distance below threshold. See `base/surface_code.py` for full LER / fidelity tables.

## Extending

Everything you'd customize lives in Python. Add a noise channel by subclassing
`aaronson.noise.Channel` and returning its stabilizer-channel `branches`; plug in a custom
sampler or observable; export the DEM to whatever decoder you like. The Rust core stays a thin,
fast tableau engine.

## Develop

```sh
./do develop   # build the native core into the active env
./do test      # run the exam test suite
./do lint      # qudit-style view/ linter + black  (./do lint --fix to autofix)
./do bench     # benchmarks + correctness vs stim (installs the `bench` extra)
./do docs      # build the VitePress docs site
./do deploy    # build wheel + sdist and upload to PyPI
```

## License

MIT
