import math
from abc import ABC, abstractmethod

_PAULI1 = ("I", "X", "Y", "Z")

_AXIS_WRAP = {
    "Z": ([], []),
    "X": (["H"], ["H"]),
}


class Channel(ABC):
    """
    A noise channel as stabilizer-channel branches (weight, ops), with ops a
    list of (gate, targets). Pauli channels: probabilities >= 0 summing to 1.
    General channels: real quasiprobabilities (may be < 0), |.| summing to
    gamma >= 1; samplers reweight a trajectory by sign(weight) * gamma.
    """

    is_pauli = True

    @abstractmethod
    def branches(self, targets):
        """
        Return the (weight, ops) branches for the given target qubits, with
        the identity (no-fault) branch first.
        """

    def sample(self, targets, rng):
        """
        Draw one branch with probability |weight| / gamma; return
        (sign(weight) * gamma, ops) -- the importance weight and its gates.
        """
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


class PauliChannel1(Channel):
    """
    Single-qubit Pauli channel applying X, Y, Z with probabilities px, py, pz.
    """

    def __init__(self, px, py, pz):
        self.px = float(px)
        self.py = float(py)
        self.pz = float(pz)

    def branches(self, targets):
        q = targets[0]
        keep = 1.0 - (self.px + self.py + self.pz)

        return [
            (keep, []),
            (self.px, [("X", (q,))]),
            (self.py, [("Y", (q,))]),
            (self.pz, [("Z", (q,))]),
        ]


class PauliChannel2(Channel):
    """
    Two-qubit Pauli channel: the 15 non-identity Paulis each with weight p/15.
    """

    def __init__(self, p):
        self.p = float(p)

    def branches(self, targets):
        a, b = targets[0], targets[1]
        each = self.p / 15.0
        out = [(1.0 - self.p, [])]
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


class PauliRotation(Channel):
    """
    Coherent single-qubit rotation exp(-i theta P / 2) as a quasiprobability
    mixture over {I, Z, S, S_DAG} (Z axis) or that mixture wrapped in
    Hadamards (X axis). Not a Pauli channel; drive it with an importance sampler.
    """

    is_pauli = False

    def __init__(self, axis, theta):
        if axis not in _AXIS_WRAP:
            raise ValueError(f"axis must be 'X' or 'Z', got {axis!r}")
        self.axis = axis
        self.theta = float(theta)

    def branches(self, targets):
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
    Amplitude-damping channel with damping probability p (arXiv:2512.07304).

    Decomposes exactly over {I, Z, reset-to-|0>} with weights q_I, q_Z,
    q_R where q_I = [(1-p)+sqrt(1-p)]/2, q_Z = [(1-p)-sqrt(1-p)]/2 (<0)
    and q_R = p. Sampling overhead gamma = [(1+p)-sqrt(1-p)]/2 ~ 3p/4 with
    negativity 1/3 -- nonunitary, so nearly as cheap as Pauli noise. Not a Pauli
    channel; use an importance sampler.
    """

    is_pauli = False

    def __init__(self, p):
        self.p = float(p)

    def branches(self, targets):
        q = targets[0]
        root = math.sqrt(1.0 - self.p)
        q_i = (1.0 - self.p + root) / 2.0
        q_z = (1.0 - self.p - root) / 2.0

        return [
            (q_i, []),
            (q_z, [("Z", (q,))]),
            (self.p, [("R", (q,))]),
        ]


def Depolarize1(p):
    """
    Single-qubit depolarizing channel (X, Y, Z each with probability p/3).
    """
    return PauliChannel1(p / 3.0, p / 3.0, p / 3.0)


def Depolarize2(p):
    """
    Two-qubit depolarizing channel (15 Paulis each with probability p/15).
    """
    return PauliChannel2(p)


def BitFlip(p):
    """
    Bit-flip channel (X with probability p).
    """
    return PauliChannel1(p, 0.0, 0.0)


def PhaseFlip(p):
    """
    Phase-flip channel (Z with probability p).
    """
    return PauliChannel1(0.0, 0.0, p)


NOISE_FACTORIES = {
    "DEPOLARIZE1": Depolarize1,
    "DEPOLARIZE2": Depolarize2,
    "X_ERROR": BitFlip,
    "Z_ERROR": PhaseFlip,
    "PAULI_CHANNEL_1": lambda arg: PauliChannel1(*arg),
    "RZ": lambda arg: PauliRotation("Z", arg),
    "RX": lambda arg: PauliRotation("X", arg),
    "AMPLITUDE_DAMP": AmplitudeDamping,
}


def make_channel(name, arg):
    """
    Build the noise channel for instruction name, or return arg unchanged
    when it is already a Channel (a custom channel added via
    Circuit.noise).
    """
    if isinstance(arg, Channel):
        return arg

    factory = NOISE_FACTORIES.get(name)
    if factory is None:
        raise NotImplementedError(f"unknown instruction {name!r}")

    return factory(arg)
