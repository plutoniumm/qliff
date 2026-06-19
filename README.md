# qliff

A Clifford stabilizer simulator with support for noisy and mid-circuit measurement-based simulation.

- **Clifford stab simulation** via the Aaronson–Gottesman tableau
- **Noisy sim** via stabilizer-channel
  decomposition `E = Σ_μ q_μ S_μ` and **stratified importance sampling**
  ([arXiv:2512.07304](https://arxiv.org/abs/2512.07304)), "nearly as cheap as Pauli noise."
- **Decoder-ready QEC primitives**: detectors, observables, detection-event sampling, a
  detector error model by exact Pauli-frame propagation, and exporters (parity-check matrix +
  priors, matching weights, syndrome/label tensors). These drop
  directly into MWPM (pymatching), BP, or ML decoders.

## Install

```sh
pip install qliff
```

Docs at [plutoniumm.github.io/qliff](https://plutoniumm.github.io/qliff/).

## Clifford simulation

```python
from qliff import Simulator

s = Simulator(2).H(0).CX(0, 1)
s.canon()        # ['+XX', '+ZZ']
s.peek("ZZ")     # +1
s.measure("XX")  # (+1, False)

m0, m1 = Simulator(2).H(0).CX(0, 1).M(0, 1)  # m0 == m1
```

Mid-circuit measurement and classical feedback are just Python — the simulator is stateful,
so conditionals (teleportation, syndrome correction) need no special API:

```python
s = Simulator(3, seed=0)
s.H(0)
s.H(1).CX(1, 2)
s.CX(0, 1).H(0)

if s.M(1) == 1:
    s.X(2)
if s.M(0) == 1:
    s.Z(2)

s.peek("__X")  # +1
```

## Noise
Build `Circuit` with gate/noise methods, then sample or estimate.

`Circuit.estimate` picks the right sampler by default — plain Monte-Carlo when every channel is Pauli, otherwise
stratified importance sampling

```python
from qliff import Circuit

c = Circuit(1)
c.H(0).DEPOLARIZE1(0, 0.1).M(0)
c.sample(1000)

c = Circuit(1)
c.H(0).RZ(0, 0.3)
c.estimate("X", 20000)  # ≈ cos(0.3)

c = Circuit(1)
c.X(0).AMPLITUDE_DAMP(0, 0.3)
c.estimate("Z", 60000)  # ≈ 2p - 1
```

Force the variance strategy with `c.estimate(obs, shots, stratify=False)` (flat) or `stratify=True`
(stratified), or drive the sampler directly: `from qliff.noise import Sampler`, then
`Sampler(c).expect(obs, shots, stratify=True)`. Add a custom channel by subclassing
`qliff.noise.Channel` and dropping it in with `c.noise(ch, q)`.

## Quantum error correction

`qliff.qec` ships code-circuit generators, so you can go straight to a logical-error-rate
curve. Any circuit's detectors and observables are declared with `c.detector(...)` /
`c.observable(...)`, then turned into decoder inputs:

```python
from qliff.qec import rotated_surface_code, logical_fidelity
from pymatching import Matching

c = rotated_surface_code(distance=5, rounds=5, p=0.01)
dem = c.dem()

H, priors, obs_matrix = dem.check_matrix()
m = Matching.from_check_matrix(
  H,
  weights=dem.weights(),
  faults_matrix=obs_matrix
)

dets, flips = c.detector_sampler().sample(20000)
fidelity = logical_fidelity(m.decode_batch(dets), flips)
```

## Extending

Everything you'd customize lives in Python. Add a noise channel by subclassing
`qliff.noise.Channel` and returning its stabilizer-channel `branches`; plug in a custom
sampler or observable; export the DEM to whatever decoder you like. The Rust core stays a thin,
fast tableau engine.

## Develop

```sh
./do develop   # build rust core
./do test
./do lint
./do bench
./do docs      # build docs
./do deploy    # publish the package to PyPI
```

## License
MIT

If you are a company using this, please get a grad student to help you with issues. If you are a grad student, please feel free to email me :)
