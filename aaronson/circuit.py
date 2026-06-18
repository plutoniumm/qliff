from .noise.channel import NOISE_FACTORIES, make_channel
from .simulator import CLIFFORD_OPS, Simulator


class Circuit:
    """
    A stim-like IR over the Simulator: ordered (name, targets, arg)
    instructions plus detectors and observables. Build fluently with uppercase
    gate/measurement/noise methods mirroring the Simulator (c.H(0),
    c.DEPOLARIZE1(0, 0.1)); run noiseless with run, sample noisy with
    sample/estimate or the QEC helpers detector_sampler/dem.
    """

    def __init__(self, num_qubits=0):
        self.num_qubits = int(num_qubits)
        self.instructions = []
        self.detectors = []
        self.observables = []
        self.num_measurements = 0

    def append(self, name, targets=(), arg=None):
        """
        Append an instruction. targets may be an int or an iterable of ints.
        """
        name = name.upper()
        if isinstance(targets, int):
            targets = (targets,)
        targets = tuple(int(t) for t in targets)
        if targets:
            self.num_qubits = max(self.num_qubits, max(targets) + 1)
        if name in ("M", "MR"):
            self.num_measurements += len(targets)
        self.instructions.append((name, targets, arg))

        return self

    def noise(self, channel, *targets):
        """
        Append a custom Channel instance on targets.
        """
        return self.append(type(channel).__name__, targets, channel)

    def _resolve(self, recs):
        flat = []
        for r in recs:
            if hasattr(r, "__iter__"):
                flat.extend(int(x) for x in r)
            else:
                flat.append(int(r))
        out = [r if r >= 0 else self.num_measurements + r for r in flat]

        return tuple(out)

    def detector(self, *recs):
        """
        Declare a detector: measurement records whose noiseless parity is fixed.

        Indices may be negative (relative to measurements so far), matching
        stim's rec[-1] convention.
        """
        self.detectors.append(self._resolve(recs))

        return self

    def observable(self, index, *recs):
        """
        Declare logical observable index over a set of measurement records.
        """
        self.observables.append((int(index), self._resolve(recs)))

        return self

    @property
    def is_pauli(self):
        """
        Whether every noise instruction is a Pauli channel.
        """
        for name, _targets, arg in self.instructions:
            if name in CLIFFORD_OPS:
                continue
            if not make_channel(name, arg).is_pauli:
                return False

        return True

    def run(self, seed=None):
        """
        Apply the (noiseless) circuit to a fresh Simulator and return it.
        """
        sim = Simulator(self.num_qubits, seed)
        for name, targets, _arg in self.instructions:
            if name in CLIFFORD_OPS:
                getattr(sim, name)(*targets)
            else:
                raise NotImplementedError(f"{name!r} is noise; use a sampler, not run")

        return sim

    def sample(self, shots, seed=None):
        """
        Measurement records over shots trajectories (Pauli noise only).
        """
        from .noise import Sampler

        return Sampler(self).sample(shots, seed)

    def estimate(self, observable, shots=10000, stratify=None, seed=None):
        """
        Estimate <observable> over reweighted trajectories, unbiased for any channel.
        stratify=None auto-picks: flat importance sampling for Pauli noise,
        stratified by fault count for general noise (lower variance);
        True/False forces the choice.
        """
        from .noise import Sampler

        if stratify is None:
            stratify = not self.is_pauli

        return Sampler(self).expect(observable, shots, seed=seed, stratify=stratify)

    def detector_sampler(self):
        from .qec import DetectorSampler

        return DetectorSampler(self)

    def dem(self):
        from .qec import DetectorErrorModel

        return DetectorErrorModel(self)

    def __len__(self):
        return len(self.instructions)

    def __iter__(self):
        return iter(self.instructions)

    def __repr__(self):
        return f"Circuit(num_qubits={self.num_qubits}, {len(self)} instructions)"


def _gate_method(name):
    def method(self, *targets):
        return self.append(name, targets)

    method.__name__ = name
    method.__doc__ = f"Append a {name} instruction on the given target qubits."

    return method


def _noise_method(name):
    def method(self, targets, arg=None):
        return self.append(name, targets, arg)

    method.__name__ = name
    method.__doc__ = f"Append the {name} noise channel on targets with arg."

    return method


for _name in CLIFFORD_OPS:
    setattr(Circuit, _name, _gate_method(_name))
for _name in NOISE_FACTORIES:
    setattr(Circuit, _name, _noise_method(_name))
