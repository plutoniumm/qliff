# Noise

Add channels to a `Circuit`, then sample trajectories with `Sampler`. `sample`
returns Pauli-noise measurement records; `expect` reweights each trajectory by
the signed quasiprobability weights, staying unbiased for coherent and
non-unitary noise too.

## Pauli noise records

Apply a bit-flip $X$ error with probability $p$ and sample the noisy
measurement records.

```python
from qliff import Circuit
from qliff.noise import Sampler

c = Circuit(1)
c.X_ERROR(0, 0.25)
c.M(0)

records = Sampler(c).sample(5000, seed=0)
ones = sum(r[0] for r in records) / 5000    # ~ 0.25
```

About a quarter of the shots flip to `1`, matching the error rate $p = 0.25$.

## Estimate an observable under depolarizing noise

`DEPOLARIZE1` shrinks every expectation; estimate $\langle X\rangle$ over many
trajectories.

```python
from qliff import Circuit
from qliff.noise import Sampler

c = Circuit(1)
c.H(0)
c.DEPOLARIZE1(0, 0.1)

est = Sampler(c).expect("X", 5000, seed=0)   # ~ 1 - 4p/3 = 0.867
```

Depolarizing with $p = 0.1$ damps $\langle X\rangle$ from $1$ toward
$1 - \tfrac{4}{3}p$.

## Coherent rotation with importance sampling

A coherent `RZ` rotation is not a Pauli channel, so `expect` reweights each
trajectory by its signed quasiprobability weight.

```python
from qliff import Circuit
from qliff.noise import Sampler

c = Circuit(1)
c.H(0).RZ(0, 0.3)

est = Sampler(c).expect("X", 20000, seed=0)   # ~ cos(0.3) = 0.955
```

The estimate tracks the exact $\langle X\rangle = \cos\theta$.

## Lower variance with stratification

`stratify=True` gives the same unbiased answer but strata by fault count for
much lower variance.

```python
from qliff import Circuit
from qliff.noise import Sampler

c = Circuit(1)
c.H(0).RZ(0, 0.3)

est = Sampler(c).expect("X", 20000, seed=0, stratify=True)   # ~ cos(0.3)
```

Same $\cos\theta$ target, smaller error bars at equal shots. (Or just call
`c.estimate("X", 20000)` and let it pick the sampler.)

## A custom channel

Subclass `Channel`: return an identity branch first, then `(weight, ops)` faults.
This is a pure $Z$ dephasing channel.

```python
from qliff import Circuit
from qliff.noise import Channel, Sampler

class Dephase(Channel):
    is_pauli = True

    def __init__(self, p):
        self.p = p

    def branches(self, targets):
        q = targets[0]
        return [(1.0 - self.p, []), (self.p, [("Z", (q,))])]


c = Circuit(1)
c.H(0).noise(Dephase(0.1), 0)

est = Sampler(c).expect("X", 5000, seed=0)   # ~ 1 - 2p = 0.8
```

A $Z$ flip with probability $p$ damps $\langle X\rangle$ by $1 - 2p$. No Rust or
recompilation — any `Channel` subclass drops straight into a circuit.
