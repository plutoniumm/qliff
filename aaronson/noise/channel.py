from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod

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

    gamma ~ 3p/4
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


def Depolarize1(p: float) -> PauliChannel:
    # 1Q depol p/3
    return PauliChannel(p / 3.0, p / 3.0, p / 3.0)


def Depolarize2(p: float) -> PauliChannel:
    # 2Q depol p/15
    return PauliChannel(p, twoq=True)


def BitFlip(p: float) -> PauliChannel:
    # X @ px = p, py = pz = 0
    return PauliChannel(p, 0.0, 0.0)


def PhaseFlip(p: float) -> PauliChannel:
    # Z @ pz = p, px = py = 0
    return PauliChannel(0.0, 0.0, p)


NOISE_FACTORIES = {
    "DEPOLARIZE1": Depolarize1,
    "DEPOLARIZE2": Depolarize2,
    "X_ERROR": BitFlip,
    "Z_ERROR": PhaseFlip,
    "PAULI_CHANNEL_1": lambda arg: PauliChannel(*arg),
    "RZ": lambda arg: Rotation("Z", arg),
    "RX": lambda arg: Rotation("X", arg),
    "AMPLITUDE_DAMP": AmplitudeDamping,
}


# for name customisation
def make_channel(name: str, arg: object) -> Channel:
    if isinstance(arg, Channel):
        return arg

    factory = NOISE_FACTORIES.get(name)
    if factory is None:
        raise NotImplementedError(f"unknown instruction {name!r}")

    return factory(arg)
