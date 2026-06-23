from __future__ import annotations

from math import sqrt
from typing import Callable, Iterator

import numpy as np

from ..circuit import Circuit
from ..noise.channel import make_channel
from .codes import logical_fidelity
from .decoder import make_decoder
from .dem import DetectorErrorModel
from .sampler import DetectorSampler, WeightedDetectorSampler

# Logical-error-rate measurement + physical-rate sweeps: sample a noisy circuit,
# decode, score predicted vs true observable flips. Pulls decoders (pymatching /
# ldpc) via qliff.qec.decoder, so import this module DIRECTLY -- never via
# qliff.qec.__init__ -- to keep `import qliff` numpy-only.


def _build_decoder(circuit: Circuit, decoder_name: str):
    """
    Circuit-aware decoder construction. Prefer the circuit factory (lights up the
    `coherent` non-Pauli decoder once it lands); fall back to a DEM-backed decoder
    so the Pauli decoders (mwpm/bposd/mld/tn) work today.
    """
    try:
        from .decoder import make_circuit_decoder

        return make_circuit_decoder(decoder_name, circuit)
    except (ImportError, AttributeError):
        return make_decoder(decoder_name, DetectorErrorModel(circuit))


def _has_nonpauli_noise(circuit: Circuit) -> bool:
    """
    True if any noise instruction is a non-Pauli (coherent / damping) channel,
    which has no honest detector-error model and needs weighted sampling.
    """
    for name, _targets, arg in circuit.instructions:
        try:
            channel = make_channel(name, arg)
        except NotImplementedError:
            continue

        if not channel.is_pauli:
            return True

    return False


def _weighted_error_rate(
    circuit: Circuit, decoder, shots: int, seed: int | None
) -> tuple[float, float]:
    """
    Quasiprobability LER for non-Pauli noise: the importance-weighted fraction of
    mis-decoded shots. stderr is the standard error of that weighted mean.
    """
    dets, obs, weights = WeightedDetectorSampler(circuit).sample(shots, seed)
    predictions = decoder.decode_batch(dets)

    if shots == 0:
        return 0.0, 0.0

    if obs.shape[1] == 0:
        errors = np.zeros(shots, dtype=np.float64)
    else:
        errors = np.any(predictions != obs, axis=1).astype(np.float64)

    contrib = weights * errors
    ler = float(np.mean(contrib))
    stderr = float(np.std(contrib) / sqrt(shots))

    return min(1.0, max(0.0, ler)), stderr


def logical_error_rate(
    circuit: Circuit,
    decoder_name: str = "mwpm",
    shots: int = 10000,
    seed: int | None = None,
) -> tuple[float, float]:
    """
    (ler, stderr) for one circuit: sample -> decode -> compare. Pauli noise uses
    the binomial standard error sqrt(ler*(1-ler)/shots); non-Pauli noise uses
    importance-weighted sampling (the only honest path for coherent channels).
    """
    decoder = _build_decoder(circuit, decoder_name)

    if _has_nonpauli_noise(circuit):
        return _weighted_error_rate(circuit, decoder, shots, seed)

    dets, obs = DetectorSampler(circuit).sample(shots, seed)
    predictions = decoder.decode_batch(dets)

    ler = 1.0 - logical_fidelity(predictions, obs)
    stderr = sqrt(ler * (1.0 - ler) / shots) if shots > 0 else 0.0

    return ler, stderr


def isweep(
    circuit_fn: Callable[[float], Circuit],
    p_values: list[float],
    decoder_name: str = "mwpm",
    shots: int = 10000,
    seed: int | None = None,
) -> Iterator[tuple[float, float, float]]:
    """
    Stream (p, ler, stderr) one point at a time -- circuit_fn(p) builds the
    circuit for each physical rate. The seed is fixed across points so the curve
    is reproducible.
    """
    for p in p_values:
        circuit = circuit_fn(p)
        ler, stderr = logical_error_rate(circuit, decoder_name, shots, seed)
        yield p, ler, stderr


def sweep(
    circuit_fn: Callable[[float], Circuit],
    p_values: list[float],
    decoder_name: str = "mwpm",
    shots: int = 10000,
    seed: int | None = None,
) -> list[tuple[float, float, float]]:
    """
    Eagerly collect the full (p, ler, stderr) curve; see `isweep` to stream.
    """
    return list(isweep(circuit_fn, p_values, decoder_name, shots, seed))
