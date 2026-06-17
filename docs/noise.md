# Noise

`aaronson.noise` simulates noisy circuits without leaving the stabilizer
formalism. Every channel is written as a quasiprobability mixture of stabilizer
(Clifford) channels,

$$\mathcal{E}(\cdot) = \sum_\mu q_\mu\, \mathcal{S}_\mu(\cdot),$$

and a sampler runs many pure-Clifford trajectories, reweighting each by
$\operatorname{sign}(q_\mu)\,\gamma$ with $\gamma = \sum_\mu |q_\mu|$ the
per-location overhead. Pauli channels have non-negative $q_\mu$ summing to one, so
$\gamma = 1$; coherent and non-unitary channels carry negative weights. This is
the method of [arXiv:2512.07304](https://arxiv.org/abs/2512.07304).

You rarely touch a channel object directly — you add noise to a [`Circuit`](/circuit)
and call `estimate` or `sample`. The classes below are what those methods build.

## Channel

A `Channel` is an abstract base whose subclasses expose a stabilizer-channel
decomposition. A *branch* is a pair `(weight, ops)`, where `ops` is a list of
`(gate, targets)` applied for that branch; the identity (no-fault) branch comes
first.

| Property/Method | Description |
| --- | --- |
| `is_pauli` | `True` if all weights are probabilities (drive with `MonteCarlo`) |
| `branches(targets)` | the `(weight, ops)` decomposition for the given qubits |
| `sample(targets, rng)` | draw one branch as `(sign·gamma, ops)` |

## Channel catalog

Each factory returns a configured `Channel`. The first group is Pauli (positive
weights); the last two are general (signed weights, `is_pauli = False`).

| Channel | Circuit method | Arguments | Description |
| --- | --- | --- | --- |
| `Depolarize1(p)` | `DEPOLARIZE1(q, p)` | $p$ | $X,Y,Z$ each with probability $p/3$ |
| `Depolarize2(p)` | `DEPOLARIZE2(pair, p)` | $p$ | the 15 two-qubit Paulis, each $p/15$ |
| `BitFlip(p)` | `X_ERROR(q, p)` | $p$ | $X$ with probability $p$ |
| `PhaseFlip(p)` | `Z_ERROR(q, p)` | $p$ | $Z$ with probability $p$ |
| `PauliChannel1(px, py, pz)` | `PAULI_CHANNEL_1(q, (px,py,pz))` | $p_x,p_y,p_z$ | arbitrary 1-qubit Pauli channel |
| `PauliRotation(axis, theta)` | `RZ(q, theta)` / `RX(q, theta)` | axis, $\theta$ | coherent rotation $e^{-i\theta P/2}$ |
| `AmplitudeDamping(p)` | `AMPLITUDE_DAMP(q, p)` | $p$ | energy decay $\|1\rangle\to\|0\rangle$ |

### Amplitude damping

`AmplitudeDamping(p)` decomposes **exactly** over $\{I, Z, \text{reset}\}$ with
weights

$$q_I = \tfrac{(1-p)+\sqrt{1-p}}{2},\quad q_Z = \tfrac{(1-p)-\sqrt{1-p}}{2} < 0,\quad q_R = p.$$

Its fault weight is $q_Z + q_R \approx \tfrac34 p$ with negativity
$\eta = \tfrac13$, and the sampling overhead is $\gamma = \sum_\mu|q_\mu| \approx
1 + \tfrac{p}{2}$ — barely above the Pauli value of $1$, so a non-unitary channel
costs nearly as little as Pauli noise. It is not a Pauli channel, so estimate it
with an importance sampler (`estimate` picks one automatically).

## Samplers

A sampler wraps a circuit and runs trajectories. All three expose
`expect(observable, shots, seed=None)`; `MonteCarlo` also exposes
`sample(shots, seed=None)` for measurement records.

| Sampler | Handles | Notes |
| --- | --- | --- |
| `MonteCarlo` | Pauli only | plain trajectories; raises on general channels |
| `ImportanceSampler` | any channel | flat quasiprobability reweighting |
| `StratifiedSampler` | any channel | stratified by fault count $k$ — lowest variance |

`StratifiedSampler` reorganizes the estimate as $F = \sum_k P(k)\,F_k$, where
$P(k)$ is the exact Poisson-binomial probability of $k$ faulty locations and
$F_k$ is the conditional estimate. Because $F_k$ varies slowly with $k$, this
cuts variance sharply versus flat importance sampling at the same shot budget.

::: code-group

```python [Example]
c = Circuit(1)
c.H(0).RZ(0, 0.3)

ImportanceSampler(c).expect("X", 20000)   # unbiased
StratifiedSampler(c).expect("X", 20000)   # same value, lower variance
```

```python [imports]
from aaronson import Circuit
from aaronson.noise import ImportanceSampler, StratifiedSampler
```

:::

> [!TIP]
> Prefer `c.estimate(observable, shots)` — it selects `MonteCarlo` for Pauli
> circuits and `StratifiedSampler` otherwise, so you rarely instantiate a sampler
> by hand.

## Custom channels

Subclass `Channel`, set `is_pauli`, and return the branches — an identity branch
first, then `(weight, ops)` faults (weights may be negative quasiprobabilities).
No Rust or recompilation is involved; drop it into a circuit with
`c.noise(channel, q)`.

::: code-group

```python [Example]
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

```python [imports]
from aaronson import Circuit
from aaronson.noise import Channel
```

:::
