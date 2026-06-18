from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Self

from ._types import Instruction, Targets
from .noise.channel import NOISE_FACTORIES, Channel, make_channel
from .pauli import PauliString
from .simulator import CLIFFORD_OPS, GATE_OPCODE, GATES_1, GATES_2, MEAS, Simulator


class Circuit:
    # Non-eager (like Simulator), but replayable for noise sampling

    def __init__(self, num_qubits: int = 0):
        self.num_qubits = int(num_qubits)
        self.instructions: list[Instruction] = []
        self.detectors: list[Targets] = []
        self.observables: list[tuple[int, Targets]] = []
        self.num_measurements = 0

    def append(
        self,
        name: str,
        targets: int | Iterable[int] = (),
        arg: object = None,
    ) -> Self:
        # Append an instruction. targets may be an int or an iterable of ints.
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

    def noise(self, channel: Channel, *targets: int) -> Self:
        return self.append(type(channel).__name__, targets, channel)

    def _resolve(self, recs: tuple) -> Targets:
        flat = []
        for r in recs:
            if hasattr(r, "__iter__"):
                flat.extend(int(x) for x in r)
            else:
                flat.append(int(r))

        out = [r if r >= 0 else self.num_measurements + r for r in flat]

        return tuple(out)

    def detector(self, *recs: int) -> Self:
        """
        Declare a detector: measurement records whose noiseless parity is fixed.
        Indices may be negative (relative to measurements so far), per stim's
        rec[-1].
        """
        self.detectors.append(self._resolve(recs))

        return self

    def observable(self, index: int, *recs: int) -> Self:
        # Declare logical observable index over a set of measurement records.
        self.observables.append((int(index), self._resolve(recs)))

        return self

    # --- basis measurements / composite gates (sugar; expand to primitives, so
    # run/sample/DEM handle them with no extra machinery) ---

    def SX(self, *q: int) -> Self:
        # sqrt-X = H S H
        for x in q:
            self.append("H", x).append("S", x).append("H", x)

        return self

    def SX_DAG(self, *q: int) -> Self:
        for x in q:
            self.append("H", x).append("S_DAG", x).append("H", x)

        return self

    def MX(self, *q: int) -> Self:
        # measure in X basis (H; M; H) -- one record per qubit
        for x in q:
            self.append("H", x).append("M", x).append("H", x)

        return self

    def MY(self, *q: int) -> Self:
        # measure in Y basis (S_DAG; H; M; H; S)
        for x in q:
            self.append("S_DAG", x).append("H", x).append("M", x)
            self.append("H", x).append("S", x)

        return self

    @property
    def is_pauli(self) -> bool:
        for name, _targets, arg in self.instructions:
            if name in CLIFFORD_OPS:
                continue

            if not make_channel(name, arg).is_pauli:
                return False

        return True

    def run(self, seed: int | None = None) -> Simulator:
        sim = Simulator(self.num_qubits, seed)
        batch: list[tuple[int, int, int]] = []

        for name, targets, _arg in self.instructions:
            if name in GATES_1:
                op = GATE_OPCODE[name]
                batch.extend((op, q, 0) for q in targets)
            elif name in GATES_2:
                op = GATE_OPCODE[name]
                batch.extend(
                    (op, targets[k], targets[k + 1]) for k in range(0, len(targets), 2)
                )
            elif name in MEAS:
                if batch:
                    sim.run_ops(batch)
                    batch = []
                getattr(sim, name)(*targets)
            else:
                raise NotImplementedError(f"{name!r} is noise; use a sampler, not run")

        if batch:
            sim.run_ops(batch)

        return sim

    def sample(self, shots: int, seed: int | None = None) -> list[list[int]]:
        from .noise import Sampler

        return Sampler(self).sample(shots, seed)

    def compile_sampler(self):
        # Reusable sampler: compile once, sample(shots) many times (amortizes the
        # compile across repeated draws, e.g. logical-error-rate sweeps).
        from .noise import CompiledSampler

        return CompiledSampler(self)

    def estimate(
        self,
        observable: PauliString | str,
        shots: int = 10000,
        stratify: bool | None = None,
        seed: int | None = None,
    ) -> float:
        from .noise import Sampler

        if stratify is None:
            stratify = not self.is_pauli

        return Sampler(self).expect(observable, shots, seed=seed, stratify=stratify)

    def detector_sampler(self):
        # DetectorSampler bound to this circuit (deferred import: qec needs Circuit)
        from .qec import DetectorSampler

        return DetectorSampler(self)

    def dem(self):
        # first-order DetectorErrorModel for this circuit
        from .qec import DetectorErrorModel

        return DetectorErrorModel(self)

    def __len__(self) -> int:
        return len(self.instructions)

    def __iter__(self) -> Iterator[Instruction]:
        return iter(self.instructions)

    def __repr__(self) -> str:
        return f"Circuit(num_qubits={self.num_qubits}, {len(self)} instructions)"


def _gate_method(name: str) -> Callable:
    def method(self, *targets: int) -> Circuit:
        return self.append(name, targets)

    method.__name__ = name
    method.__doc__ = f"Append a {name} instruction on the given target qubits."

    return method


def _noise_method(name: str) -> Callable:
    def method(self, targets: int | Iterable[int], arg: object = None) -> Circuit:
        return self.append(name, targets, arg)

    method.__name__ = name
    method.__doc__ = f"Append the {name} noise channel on targets with arg."

    return method


for _name in CLIFFORD_OPS:
    setattr(Circuit, _name, _gate_method(_name))
for _name in NOISE_FACTORIES:
    setattr(Circuit, _name, _noise_method(_name))
