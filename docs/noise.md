# Noise

`aaronson.noise` simulates noisy circuits inside the stabilizer formalism. Each
channel is a quasiprobability mixture of stabilizer (Clifford) channels:

$$\mathcal{E}(\cdot) = \sum_\mu q_\mu\, \mathcal{S}_\mu(\cdot).$$

A sampler runs many pure-Clifford trajectories and reweights each by
$\operatorname{sign}(q_\mu)\,\gamma$, where $\gamma = \sum_\mu |q_\mu|$ is the
per-location overhead. Pauli channels have $q_\mu \ge 0$ summing to one, so
$\gamma = 1$. Coherent and non-unitary channels carry negative weights and
$\gamma > 1$. This is the method of
[arXiv:2512.07304](https://arxiv.org/abs/2512.07304).

You rarely touch a channel directly. Add noise to a [`Circuit`](/circuit), then
call `estimate` or `sample` — the classes below are what those methods build.

## Channel

`Channel` is an abstract base; subclasses expose a stabilizer-channel
decomposition. A *branch* is a pair `(weight, ops)`, where `ops` is a list of
`(gate, targets)`. The identity (no-fault) branch comes first.

| Property/Method | Description |
| --- | --- |
| `is_pauli` | `True` if all weights are probabilities (records are sampleable) |
| `branches(targets)` | the `(weight, ops)` decomposition for the given qubits |
| `sample(targets, rng)` | draw one branch as `(sign·gamma, ops)` |

## Channel catalog

Each factory returns a configured `Channel`. The first five are Pauli (positive
weights); the last two are general (signed weights, `is_pauli = False`).

| Channel | Circuit method | Arguments | Description |
| --- | --- | --- | --- |
| `Depolarize(p)` | `DEPOLARIZE1(q, p)` | $p$ | $X,Y,Z$ each with probability $p/3$ |
| `Depolarize(p, twoq=True)` | `DEPOLARIZE2(pair, p)` | $p$ | the 15 two-qubit Paulis, each $p/15$ |
| `BitFlip(p)` | `X_ERROR(q, p)` | $p$ | $X$ with probability $p$ |
| `PhaseFlip(p)` | `Z_ERROR(q, p)` | $p$ | $Z$ with probability $p$ |
| `PauliChannel(px, py, pz)` | `PAULI_CHANNEL_1(q, (px,py,pz))` | $p_x,p_y,p_z$ | arbitrary 1-qubit Pauli channel (`twoq=True` → 2-qubit depolarizing) |
| `Rotation(axis, theta)` | `RZ(q, theta)` / `RX(q, theta)` | axis, $\theta$ | coherent rotation $e^{-i\theta P/2}$ |
| `AmplitudeDamping(p)` | `AMPLITUDE_DAMP(q, p)` | $p$ | energy decay $\|1\rangle\to\|0\rangle$ |

### Amplitude damping

`AmplitudeDamping(p)` decomposes **exactly** over $\{I, Z, \text{reset}\}$:

$$q_I = \tfrac{(1-p)+\sqrt{1-p}}{2},\quad q_Z = \tfrac{(1-p)-\sqrt{1-p}}{2} < 0,\quad q_R = p.$$

The overhead $\gamma = \tfrac{(1+p)-\sqrt{1-p}}{2} \approx 1 + \tfrac{p}{2}$ sits
barely above the Pauli value of $1$, with negativity $\eta = \tfrac13$. So this
non-unitary channel costs nearly as little to sample as Pauli noise. It is not a
Pauli channel — estimate it with `expect` (`estimate` reweights automatically).

## Sampler

`Sampler` wraps a circuit and runs trajectories. It has two methods.

| Method | Handles | Notes |
| --- | --- | --- |
| `expect(obs, shots, seed=None, stratify=False)` | any channel | importance estimate, unbiased for any noise |
| `sample(shots, seed=None)` | Pauli only | `uint8` array `(shots, measurements)`; raises on a general channel |

`expect` draws one branch per noise location and reweights each trajectory by
$\operatorname{sign}(q_\mu)\,\gamma$. On Pauli noise every weight is $1$, so it is
plain Monte-Carlo. With `stratify=True` it rewrites the estimate as
$F = \sum_k P(k)\,F_k$: $P(k)$ is the exact Poisson-binomial probability of $k$
faulty locations, and $F_k$ the conditional estimate. Since $F_k$ varies slowly
with $k$, this cuts variance sharply at the same shot budget.

```python
from aaronson import Circuit
from aaronson.noise import Sampler

c = Circuit(1)
c.H(0).RZ(0, 0.3)

Sampler(c).expect("X", 20000)
Sampler(c).expect("X", 20000, stratify=True)
```

`sample` is Pauli-only: a measured bitstring cannot be reweighted by a negative
quasiprobability, so a non-Pauli channel raises.

> [!TIP]
> Prefer `c.estimate(observable, shots)`. It uses flat importance sampling for
> Pauli circuits and stratifies otherwise, so you rarely build a `Sampler` by hand.

## Custom channels

Subclass `Channel`, set `is_pauli`, and return the branches: an identity branch
first, then `(weight, ops)` faults (weights may be negative quasiprobabilities).
No Rust or recompilation needed. Drop it into a circuit with `c.noise(channel, q)`.

```python
from aaronson import Circuit
from aaronson.noise import Channel


class Dephase(Channel):
    is_pauli = True

    def __init__(self, p):
        self.p = p

    def branches(self, targets):
        q = targets[0]

        return [(1.0 - self.p, []), (self.p, [("Z", (q,))])]


c = Circuit(1)
c.H(0).noise(Dephase(0.1), 0)
```
