from __future__ import annotations

from typing import Self

from ._core import Tableau
from .pauli import PauliString, canonicalize, to_str

# Instruction-name classes the Simulator executes directly (vs noise channels).
GATES_1 = {"H", "S", "S_DAG", "X", "Y", "Z"}
GATES_2 = {"CX", "CNOT", "CZ", "SWAP"}
MEAS = {"M", "MR", "R"}
CLIFFORD_OPS = GATES_1 | GATES_2 | MEAS


def _flat(args: tuple) -> list[int]:
    out = []
    for a in args:
        if hasattr(a, "__iter__"):
            out.extend(int(x) for x in a)
        else:
            out.append(int(a))

    return out


class Simulator:
    """
    Clifford stabilizer simulator, stim-style uppercase API.
    Starts in |0...0>. 1Q gates take one+ targets; 2Q gates take flattened
    (control, target) pairs, e.g. CX(0, 1, 2, 3). Gates return self -> chain.
    """

    def __init__(self, num_qubits: int, seed: int | None = None):
        self._t = Tableau(num_qubits, seed)

    @property
    def num_qubits(self) -> int:
        return self._t.n

    def _apply1(self, name: str, qubits: tuple) -> Self:
        f = getattr(self._t, name)
        for q in _flat(qubits):
            f(q)

        return self

    def H(self, *q: int) -> Self:
        return self._apply1("h", q)

    def S(self, *q: int) -> Self:
        return self._apply1("s", q)

    def S_DAG(self, *q: int) -> Self:
        return self._apply1("s_dag", q)

    def X(self, *q: int) -> Self:
        return self._apply1("x", q)

    def Y(self, *q: int) -> Self:
        return self._apply1("y", q)

    def Z(self, *q: int) -> Self:
        return self._apply1("z", q)

    def _apply2(self, name: str, targets: tuple) -> Self:
        f = getattr(self._t, name)
        ts = _flat(targets)
        if len(ts) % 2:
            raise ValueError(
                f"{name.upper()} expects (control, target) pairs, got {len(ts)} targets"
            )
        for k in range(0, len(ts), 2):
            f(ts[k], ts[k + 1])

        return self

    def CX(self, *t: int) -> Self:
        return self._apply2("cx", t)

    CNOT = CX

    def CZ(self, *t: int) -> Self:
        return self._apply2("cz", t)

    def SWAP(self, *t: int) -> Self:
        return self._apply2("swap", t)

    def M(self, *q: int) -> int | list[int]:
        outs = [int(self._t.measure(x, None)) for x in _flat(q)]

        return outs[0] if len(outs) == 1 else outs

    def MR(self, *q: int) -> int | list[int]:
        outs = [int(self._t.mr(x)) for x in _flat(q)]

        return outs[0] if len(outs) == 1 else outs

    def R(self, *q: int) -> Self:
        for x in _flat(q):
            self._t.reset(x)

        return self

    reset = R

    def measure(
        self, pauli: PauliString | str, force: int | None = None
    ) -> tuple[int, bool]:
        """
        Measure Hermitian pauli (PauliString or signed str like "ZZ") in place.
        Return (value=+-1, random); random flags a coin-flip outcome. force=+-1
        pins a random outcome to that eigenspace -- the primitive behind
        syndrome extraction.
        """
        if isinstance(pauli, str):
            pauli = PauliString.parse(pauli)
        sign, x, z = pauli.tuple()

        force_bit = None if force is None else (force == -1) ^ bool(sign)
        bit, random = self._t.measure_pauli(x, z, force_bit)
        value = -1 if (bool(bit) ^ bool(sign)) else 1

        return value, random

    @property
    def record(self) -> list[int]:
        return [int(b) for b in self._t.record]

    def clear(self) -> Self:
        self._t.clear_record()

        return self

    def peek(self, pauli: PauliString | str) -> int:
        """
        <P> in {-1, 0, +1} for Hermitian P (PauliString or signed str "ZZ",
        "-X"). Non-destructive.
        """
        if isinstance(pauli, str):
            pauli = PauliString.parse(pauli)
        if pauli.phase % 2 == 1:
            raise ValueError("observable must be Hermitian (phase +1 or -1)")
        if pauli.n != self._t.n:
            raise ValueError(
                f"observable on {pauli.n} qubits, simulator has {self._t.n}"
            )

        e = self._t.expectation(pauli.x, pauli.z)

        return -e if pauli.phase == 2 else e

    def copy(self) -> Self:
        s = Simulator.__new__(Simulator)
        s._t = self._t.copy()

        return s

    def stabilizers(self) -> list[str]:
        # Raw (non-canonical) signed-Pauli generators.
        return [to_str(int(sg), x, z) for sg, x, z in self._t.stabilizers()]

    def canon(self) -> list[str]:
        # Canonical signed-Pauli generators (unique per stabilizer state).
        return canonicalize(self._t.stabilizers(), self._t.n)

    def __repr__(self) -> str:
        return f"Simulator(num_qubits={self._t.n})"
