# Error Correction

`qliff.qec` turns a noisy [`Circuit`](/circuit) into decoder inputs: detection
events, a detector error model, and the parity-check / matching exports built from
it. **No decoder is bundled.** The exports drop straight into MWPM (pymatching),
belief propagation, or an ML decoder. Ready-made code circuits let you jump
straight to a logical-error-rate curve.

## Code circuits

Each generator returns a `Circuit` under circuit-level Pauli noise with its
detectors and logical observable already declared.

| Generator | Arguments | Description |
| --- | --- | --- |
| `repetition_code(distance, rounds, p)` | code distance, syndrome rounds, per-round $X$ error $p$ | bit-flip repetition-code $Z$ memory |
| `rotated_surface_code(distance, rounds, p)` | distance, rounds, depolarizing $p$ | rotated planar surface-code $Z$ memory |

```python
from qliff.qec import repetition_code, rotated_surface_code

rep = repetition_code(distance=3, rounds=3, p=0.05)
sur = rotated_surface_code(distance=3, rounds=3, p=0.01)
```

You can also declare your own on any circuit with `c.detector(*recs)` and
`c.observable(index, *recs)`, using stim's `rec[-1]` negative indexing into the
measurement record (see [Circuit](/circuit#detectors-and-observables)).

## DetectorSampler

`circuit.detector_sampler()` returns a sampler whose `sample(shots, seed=None)`
yields two `numpy` `uint8` arrays: the **syndrome** and the **logical labels**. A
detection event is a detector's measured parity XORed with its noiseless value, so
a clean run produces all-zero syndromes.

| Output | Shape | Meaning |
| --- | --- | --- |
| `dets` | `(shots, n_detectors)` | detection events |
| `obs` | `(shots, n_observables)` | logical-observable flips (the labels) |

```python
dets, obs = rep.detector_sampler().sample(10000, seed=0)
```

These feed a decoder directly, or serve as a training set for an ML decoder.

## DetectorErrorModel

`circuit.dem()` builds the error model by propagating each Pauli fault branch
sign-free to the end of the circuit, recording which detectors and observables it
flips. Mechanisms with identical signatures merge as independent errors. It is
exact for Pauli noise.

| Property/Method | Returns | Description |
| --- | --- | --- |
| `mechanisms` | `list` | `(probability, detectors, observables)` per mechanism |
| `check_matrix()` | `(H, priors, obs_matrix)` | $\mathbb{F}_2$ parity-check `H` (detectors×mechanisms), priors, observable matrix — for BP |
| `weights()` | `ndarray` | per-mechanism MWPM weights $\log\frac{1-p}{p}$ |
| `graphlike_edges()` | `list` | mechanisms flipping $\le 2$ detectors, as `(dets, obs, weight)` — a matching graph |

## Decoding and logical error rate

Wire the exports into pymatching, decode the sampled syndromes, and compare to
the labels. `logical_fidelity(predictions, observed)` returns $1 - \text{LER}$.

```python
from pymatching import Matching
from qliff.qec import repetition_code, logical_fidelity

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

Below threshold, the logical error rate falls as distance grows — the signature
of working error correction. See `base/surface_code.py` for full LER / fidelity
tables across distances.

> [!NOTE]
> The detector error model and detection sampler use Pauli-noise trajectories.
> For logical error rates under **coherent** noise, estimate the logical
> observable directly with the [importance sampler](/noise#samplers).
