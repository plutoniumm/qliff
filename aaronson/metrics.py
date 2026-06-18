from __future__ import annotations

from .pauli import PauliString
from .simulator import Simulator


def expectation(sim: Simulator, pauli: PauliString | str) -> int:
    # <P> in {-1, 0, +1} for Hermitian P (see Simulator.peek).
    return sim.peek(pauli)


def fidelity(a: Simulator, b: Simulator) -> float:
    if a.num_qubits != b.num_qubits:
        raise ValueError("states must have the same qubit count")

    work = b.copy()
    overlap = 1.0
    for gen in a.stabilizers():
        value, random = work.measure(gen, force=1)
        if random:
            overlap *= 0.5
        elif value != 1:
            return 0.0

    return overlap
