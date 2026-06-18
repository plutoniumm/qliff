# Error Correction

Turn a noisy code circuit into decoder inputs: detection events, a detector error
model, and the matching/parity-check exports built from it. No decoder is
bundled — the exports feed pymatching, BP, or an ML decoder directly.

## Repetition-code memory experiment

Build a distance-$d$ bit-flip $Z$-memory circuit and sample its detection events
and logical labels.

```python
from aaronson.qec import repetition_code

rep = repetition_code(distance=3, rounds=3, p=0.05)
dets, obs = rep.detector_sampler().sample(10000, seed=0)
```

`dets` has shape `(10000, n_detectors)` of detection events; `obs` holds the
logical-observable flips (the labels). A clean run gives all-zero syndromes.

## Rotated surface-code memory experiment

The same interface scales to a 2-D code; here a distance-3 rotated surface code
under depolarizing noise.

```python
from aaronson.qec import rotated_surface_code

sur = rotated_surface_code(distance=3, rounds=3, p=0.01)
dets, obs = sur.detector_sampler().sample(10000, seed=0)
```

Lower per-step error rate $p$ and larger distance both drive the logical error
rate down.

## Export a detector error model

`dem()` propagates each Pauli fault to the circuit end; `check_matrix()` returns
the parity-check `H`, the priors, and the observable matrix for BP decoders.

```python
from aaronson.qec import repetition_code

rep = repetition_code(distance=3, rounds=3, p=0.05)
dem = rep.dem()

H, priors, obs_matrix = dem.check_matrix()
# H:          (n_detectors x n_mechanisms) uint8 parity-check matrix
# priors:     per-mechanism fault probabilities
# obs_matrix: (n_observables x n_mechanisms) uint8
```

`H` is detectors $\times$ mechanisms; `priors` carries each mechanism's
probability $p$.

## Decode with pymatching and measure the logical fidelity

Wire the exports into MWPM, decode the sampled syndromes, and compare to the
labels. `logical_fidelity` returns $1 - \text{LER}$.

```python
from pymatching import Matching
from aaronson.qec import repetition_code, logical_fidelity

rep = repetition_code(distance=3, rounds=3, p=0.05)
dem = rep.dem()
H, priors, obs_matrix = dem.check_matrix()

matching = Matching.from_check_matrix(
    H, weights=dem.weights(), faults_matrix=obs_matrix
)

dets, obs = rep.detector_sampler().sample(20000, seed=0)
predicted = matching.decode_batch(dets)
fidelity = logical_fidelity(predicted, obs)   # 1 - logical error rate
```

`fidelity` is close to $1$ below threshold and climbs toward $1$ as the distance
grows — the signature of working error correction.

> [!NOTE]
> The detector error model and detection sampler use Pauli-noise trajectories.
> For logical error rates under **coherent** noise, estimate the logical
> observable directly with the [importance sampler](/noise#samplers).
