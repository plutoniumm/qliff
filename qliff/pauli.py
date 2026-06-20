from __future__ import annotations

from typing import Self

from ._types import Bits, Signed

_PAIR = {
    "I": (0, 0),
    "X": (1, 0),
    "Z": (0, 1),
    "Y": (1, 1),
}
_CHAR = "IXZY"  # index x|(z<<1) = x + 2z: I=0, X=1, Z=2, Y=3
_PHASE = {
    0: "+",
    1: "+i",
    2: "-",
    3: "-i",
}


def g(x1: int, z1: int, x2: int, z2: int) -> int:
    """
    Exponent e of i^e from (x1,z1)*(x2,z2)
    e in {-1,0,+1}

    I = (0, 0) -> 0
    X = (1, 0) -> z2*(2*x2-1)
    Z = (0, 1) -> x2*(1-2*z2)
    Y = (1,1) -> z2-x2
    """
    if not x1 and not z1:
        val = 0  # I
    elif x1 and z1:
        val = z2 - x2  # Y
    elif x1:
        val = z2 * (2 * x2 - 1)  # X
    else:
        val = x2 * (1 - 2 * z2)  # Z

    return val


def parse_signed(s: str) -> Signed:
    sign, i = 0, 0
    if s and s[0] in "+-":
        sign = 1 if s[0] == "-" else 0
        i = 1

    x, z = [], []
    for ch in s[i:]:
        a, b = _PAIR["I" if ch == "_" else ch]
        x.append(a)
        z.append(b)

    return (sign, x, z)


def to_str(sign: int, x: Bits, z: Bits) -> str:
    # fmt: off
    body = "".join(
        _CHAR[x[j] | (z[j] << 1)]
            for j in range(len(x))
    )
    # fmt: on

    return ("-" if sign else "+") + body


def _compose(dst: Signed, src: Signed, n: int) -> Signed:
    # dst * src, tracking the exact sign.
    sd, xd, zd = dst
    ss, xs, zs = src

    gsum = sum(g(xs[j], zs[j], xd[j], zd[j]) for j in range(n))
    sign = sd ^ ss ^ (1 if gsum % 4 == 2 else 0)
    x = [xd[j] ^ xs[j] for j in range(n)]
    z = [zd[j] ^ zs[j] for j in range(n)]

    return [sign, x, z]


def canonicalize(paulis: list[Signed], n: int) -> list[str]:
    """
    Canonical signed-Pauli generators of <paulis>, by Gaussian elimination
    over the 2n-bit symplectic rows (x-block then z-block) with exact sign carry.
    """
    rows = [[int(s), list(map(int, x)), list(map(int, z))] for (s, x, z) in paulis]
    m = len(rows)

    def bit(row: Signed, c: int) -> int:
        return row[1][c] if c < n else row[2][c - n]

    pr = 0

    for c in range(2 * n):
        sel = next((r for r in range(pr, m) if bit(rows[r], c)), None)
        if sel is None:
            continue

        rows[pr], rows[sel] = rows[sel], rows[pr]
        piv = rows[pr]

        for r in range(m):
            if r != pr and bit(rows[r], c):
                rows[r] = _compose(rows[r], piv, n)

        pr += 1
        if pr == m:
            break

    return [to_str(s, x, z) for s, x, z in rows[:pr]]


class PauliString:
    """
    n-qubit Pauli i**phase * tensor(I/X/Y/Z).
    phase 0..3: 0->+1, 1->+i, 2->-1, 3->-i. Hermitian (valid observable) =
    even phase.
    """

    __slots__ = ("x", "z", "phase")

    def __init__(self, x: Bits, z: Bits, phase: int = 0):
        self.x = [int(v) & 1 for v in x]  # & 1: coerce to a 0/1 bit
        self.z = [int(v) & 1 for v in z]

        if len(self.x) != len(self.z):
            raise ValueError("x and z must have equal length")

        self.phase = int(phase) % 4

    @classmethod
    def parse(cls, s: str) -> Self:
        # Parse '+XYZ', '-Y', '+iXZ', 'X_Z' (_ = identity).
        phase, i = 0, 0
        if s[:2] in ("+i", "-i"):
            phase = 1 if s[0] == "+" else 3
            i = 2
        elif s and s[0] in "+-":
            phase = 0 if s[0] == "+" else 2
            i = 1

        x, z = [], []
        for ch in s[i:]:
            a, b = _PAIR["I" if ch == "_" else ch]
            x.append(a)
            z.append(b)

        return cls(x, z, phase)

    @classmethod
    def identity(cls, n: int) -> Self:
        return cls([0] * n, [0] * n, 0)

    @classmethod
    def from_sparse(cls, n: int, ops: dict[int, str], phase: int = 0) -> Self:
        # Unlisted qubits are I
        x, z = [0] * n, [0] * n
        for q, p in ops.items():
            x[q], z[q] = _PAIR[p]

        return cls(x, z, phase)

    @property
    def n(self) -> int:
        return len(self.x)

    def tuple(self) -> Signed:
        # Raises for non-Hermitian phases (+-i)
        if self.phase % 2:
            raise ValueError("non-Hermitian Pauli (phase +-i) has no real sign")

        return (self.phase // 2, list(self.x), list(self.z))

    def commutes_with(self, other: PauliString) -> bool:
        # commute iff symplectic product XOR_j (x_j & oz_j) ^ (z_j & ox_j) == 0
        s = 0
        for j in range(self.n):
            s ^= (self.x[j] & other.z[j]) ^ (self.z[j] & other.x[j])

        return s & 1 == 0

    def __mul__(self, other: PauliString) -> PauliString:
        if self.n != other.n:
            raise ValueError("size mismatch")

        n = self.n
        gsum = sum(g(self.x[j], self.z[j], other.x[j], other.z[j]) for j in range(n))
        phase = (self.phase + other.phase + gsum) % 4
        x = [self.x[j] ^ other.x[j] for j in range(n)]
        z = [self.z[j] ^ other.z[j] for j in range(n)]

        return PauliString(x, z, phase)

    def __eq__(self, other: object) -> bool:
        equal = (
            isinstance(other, PauliString)
            and self.phase == other.phase
            and self.x == other.x
            and self.z == other.z
        )

        return equal

    def __hash__(self) -> int:
        return hash((self.phase, tuple(self.x), tuple(self.z)))

    def __len__(self) -> int:
        return self.n

    def __repr__(self) -> str:
        body = "".join(_CHAR[self.x[j] | (self.z[j] << 1)] for j in range(self.n))

        return _PHASE[self.phase] + body
