from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from .._types import Branch, Op, Targets

_PAULI1 = ("I", "X", "Y", "Z")

_AXIS_WRAP = {
    "Z": ([], []),
    "X": (["H"], ["H"]),
}


class Channel(ABC):
    """
    Stabilizer-channel
     branches are (weight, ops);
     ops are list(gate, targets).

    Pauli:
        weights >= 0, sum to 1.
    General:
        may be < 0, |.| sum to gamma >= 1
        sampler weights trajectory by sign(weight) * gamma.
    """

    is_pauli = True

    @abstractmethod
    def branches(self, targets: Targets) -> list[Branch]:
        # (weight, ops) branches for targets; identity (no-fault) branch first.
        ...

    def sample(self, targets: Targets, rng: random.Random) -> tuple[float, list[Op]]:
        # Draw one branch w.p. |weight| / gamma; return (sign(weight) * gamma, ops).
        branches = self.branches(targets)
        gamma = sum(abs(w) for w, _ in branches)
        threshold = rng.random() * gamma
        acc = 0.0
        for weight, ops in branches:
            acc += abs(weight)
            if threshold <= acc:
                return ((1.0 if weight >= 0.0 else -1.0) * gamma, ops)

        weight, ops = branches[-1]

        return ((1.0 if weight >= 0.0 else -1.0) * gamma, ops)


class PauliChannel(Channel):
    """
    1Q:
        X@px, Y@py, Z@pz
    2Q:
        All combinations but at px/15.
        py, pz are dead here
    """

    def __init__(
        self,
        px: float,
        py: float = 0.0,
        pz: float = 0.0,
        twoq: bool = False,
    ):
        self.px = float(px)
        self.py = float(py)
        self.pz = float(pz)
        self.twoq = twoq

    def branches(self, targets: Targets) -> list[Branch]:
        if self.twoq:
            a, b = targets[0], targets[1]
            each = self.px / 15.0

            out = [(1.0 - self.px, [])]
            for pa in _PAULI1:
                for pb in _PAULI1:
                    if pa == "I" and pb == "I":
                        continue

                    ops = []
                    if pa != "I":
                        ops.append((pa, (a,)))
                    if pb != "I":
                        ops.append((pb, (b,)))

                    out.append((each, ops))

            return out

        q = targets[0]
        keep = 1.0 - (self.px + self.py + self.pz)

        return [
            (keep, []),
            (self.px, [("X", (q,))]),
            (self.py, [("Y", (q,))]),
            (self.pz, [("Z", (q,))]),
        ]


class Rotation(Channel):
    """
    Coherent 1Q rotation gate exp(-i theta P / 2), non Pauli error. Non-Clifford, so the channel is quasiprob mix of Cliffords:
        Z axis: weighted {I, Z, S, S_DAG} (the Cliffords diagonal in Z).
        X axis: same mixture wrapped in H each side, since RX = H RZ H.
    """

    is_pauli = False

    def __init__(self, axis: str, theta: float):
        if axis not in _AXIS_WRAP:
            raise ValueError(f"axis must be 'X' or 'Z', got {axis!r}")

        self.axis = axis
        self.theta = float(theta)

    def branches(self, targets: Targets) -> list[Branch]:
        q = targets[0]
        cos = math.cos(self.theta)
        sin = math.sin(self.theta)
        bd = (1.0 - cos - sin) / 4.0
        cores = [
            (bd + cos, None),
            (bd, "Z"),
            (bd + sin, "S"),
            (bd, "S_DAG"),
        ]
        pre, post = _AXIS_WRAP[self.axis]

        out = []
        for weight, core in cores:
            ops = [(g, (q,)) for g in pre]
            if core is not None:
                ops.append((core, (q,)))

            ops += [(g, (q,)) for g in post]
            out.append((weight, ops))

        return out


class AmplitudeDamping(Channel):
    """
    AD prob p. Exact over {I, Z, R=Reset}:
        q_I = [(1-p)+sqrt(1-p)]/2,
        q_Z = [(1-p)-sqrt(1-p)]/2 (<0),
        q_R = p.

    gamma = sum|q_k| = sqrt(1-p) + p  (~ 1 + p/2 for small p; peaks at 1.25 near p=3/4).
    """

    is_pauli = False

    def __init__(self, p: float):
        self.p = float(p)

    def branches(self, targets: Targets) -> list[Branch]:
        q = targets[0]

        root = math.sqrt(1.0 - self.p)
        q_i = (1.0 - self.p + root) / 2.0
        q_z = (1.0 - self.p - root) / 2.0

        return [
            (q_i, []),
            (q_z, [("Z", (q,))]),
            (self.p, [("R", (q,))]),
        ]


def Depolarize(p: float, twoq: bool = False) -> PauliChannel:
    # depol: 1Q over {X,Y,Z} at p/3, or 2Q over the 15 Pauli pairs at p/15
    if twoq:
        return PauliChannel(p, twoq=True)

    return PauliChannel(p / 3.0, p / 3.0, p / 3.0)


def BitFlip(p: float) -> PauliChannel:
    # X @ px = p, py = pz = 0
    return PauliChannel(p, 0.0, 0.0)


def PhaseFlip(p: float) -> PauliChannel:
    # Z @ pz = p, px = py = 0
    return PauliChannel(0.0, 0.0, p)


@dataclass(frozen=True)
class ChannelMeta:
    """
    One noise channel's factory plus the facts every consumer re-derives by name:
    the human `label`, the native scalar-strength `arg_shape` ("p"/"theta"/"vec3"),
    whether it acts on qubit PAIRS (`two_qubit`), and Pauli-ness. This is the single
    source of truth -- a new channel is ONE entry in CHANNEL_META below.
    """

    factory: Callable[..., Channel]
    channel_cls: type[Channel]
    label: str
    arg_shape: str
    two_qubit: bool = False

    @property
    def is_pauli(self) -> bool:
        # Pauli-ness lives on the Channel subclass; read it, never duplicate it.
        return self.channel_cls.is_pauli


# Source of truth for every noise channel: factory + UI/builder metadata, keyed by
# instruction name. Add a channel here once and NOISE_FACTORIES, the arg-shape sets,
# and the server channel table (later pass) all pick it up.
CHANNEL_META: dict[str, ChannelMeta] = {
    "DEPOLARIZE1": ChannelMeta(
        factory=Depolarize,
        channel_cls=PauliChannel,
        label="Depolarizing (1Q)",
        arg_shape="p",
    ),
    "DEPOLARIZE2": ChannelMeta(
        factory=lambda arg: Depolarize(arg, twoq=True),
        channel_cls=PauliChannel,
        label="Depolarizing (2Q)",
        arg_shape="p",
        two_qubit=True,
    ),
    "X_ERROR": ChannelMeta(
        factory=BitFlip,
        channel_cls=PauliChannel,
        label="Bit flip (X)",
        arg_shape="p",
    ),
    "Z_ERROR": ChannelMeta(
        factory=PhaseFlip,
        channel_cls=PauliChannel,
        label="Phase flip (Z)",
        arg_shape="p",
    ),
    "PAULI_CHANNEL_1": ChannelMeta(
        factory=lambda arg: PauliChannel(*arg),
        channel_cls=PauliChannel,
        label="Pauli channel (1Q)",
        arg_shape="vec3",
    ),
    "RZ": ChannelMeta(
        factory=lambda arg: Rotation("Z", arg),
        channel_cls=Rotation,
        label="Z rotation",
        arg_shape="theta",
    ),
    "RX": ChannelMeta(
        factory=lambda arg: Rotation("X", arg),
        channel_cls=Rotation,
        label="X rotation",
        arg_shape="theta",
    ),
    "AMPLITUDE_DAMP": ChannelMeta(
        factory=AmplitudeDamping,
        channel_cls=AmplitudeDamping,
        label="Amplitude damping",
        arg_shape="p",
    ),
}


# name -> factory view, derived from CHANNEL_META. Kept as the historical public
# access so importers stay valid: NOISE_FACTORIES[name](arg), `.get(name)`,
# `name in NOISE_FACTORIES`, and iteration over names all behave as before.
NOISE_FACTORIES = {name: meta.factory for name, meta in CHANNEL_META.items()}


# for name customisation
def make_channel(name: str, arg: object) -> Channel:
    if isinstance(arg, Channel):
        return arg

    factory = NOISE_FACTORIES.get(name)
    if factory is None:
        raise NotImplementedError(f"unknown instruction {name!r}")

    return factory(arg)


# A scalar strength p maps onto each channel's NATIVE arg shape: PAULI_CHANNEL_1
# wants a (px, py, pz) vector, DEPOLARIZE2 acts on target PAIRS, everything else is
# a scalar-arg single-qubit op. Both sets are DERIVED from CHANNEL_META so they can
# never drift from it. They are shared by the template builders (qec/codes.py) and
# the free-form spec builder (qec/lattice.py) -- a new channel declares its arg shape
# once in CHANNEL_META, and every circuit builder picks it up. Without this a builder
# that hard-codes `append(ch, [q], p)` crashes on PAULI_CHANNEL_1 (float is not
# iterable) and mis-shapes DEPOLARIZE2 (one target, not a pair).
_VECTOR_CHANNELS = {
    name for name, meta in CHANNEL_META.items() if meta.arg_shape == "vec3"
}
_TWO_QUBIT_CHANNELS = {name for name, meta in CHANNEL_META.items() if meta.two_qubit}


def channel_arg(channel: str, p: float) -> object:
    """
    The arg a scalar strength p becomes for `channel`: a (px, py, pz) split for
    vector channels, else p unchanged.
    """
    if channel in _VECTOR_CHANNELS:
        return (p / 3.0, p / 3.0, p / 3.0)

    return p


def apply_data_noise(append, channel: str, qubits, p: float) -> None:
    """
    Emit per-round data noise for `channel` at strength p onto `qubits`, via the
    `append(name, targets, arg)` callback (e.g. Circuit.append). Scalar 1Q channels
    hit every qubit; PAULI_CHANNEL_1 spreads p over (px, py, pz); DEPOLARIZE2 acts on
    adjacent qubit pairs (the last qubit is dropped if the count is odd).
    """
    qubits = list(qubits)
    if channel in _TWO_QUBIT_CHANNELS:
        for i in range(0, len(qubits) - 1, 2):
            append(channel, [qubits[i], qubits[i + 1]], p)

        return

    arg = channel_arg(channel, p)
    for q in qubits:
        append(channel, [q], arg)
