from __future__ import annotations

from math import sqrt
from typing import Callable, Iterator

from ..circuit import Circuit
from .codes import logical_fidelity
from .decoder import make_decoder
from .dem import DetectorErrorModel
from .sampler import DetectorSampler

# Logical-error-rate measurement + physical-rate sweeps: sample a noisy circuit,
# decode, score predicted vs true observable flips. Pulls decoders (pymatching /
# ldpc) via qliff.qec.decoder, so import this module DIRECTLY -- never via
# qliff.qec.__init__ -- to keep `import qliff` numpy-only.


def logical_error_rate(
    circuit: Circuit,
    decoder_name: str = "mwpm",
    shots: int = 10000,
    seed: int | None = None,
) -> tuple[float, float]:
    """
    (ler, stderr) for one circuit: sample -> decode -> compare. stderr is the
    binomial standard error sqrt(ler*(1-ler)/shots).
    """
    dem = DetectorErrorModel(circuit)
    decoder = make_decoder(decoder_name, dem)
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
