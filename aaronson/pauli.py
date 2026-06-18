_PAIR = {
    "I": (0, 0),
    "X": (1, 0),
    "Z": (0, 1),
    "Y": (1, 1),
}
_CHAR = "IXZY"  # index by x | (z << 1)
_PHASE = {
    0: "+",
    1: "+i",
    2: "-",
    3: "-i",
}


def g(x1, z1, x2, z2):
    """
    Exponent e of i^e from multiplying single-qubit Paulis (x1,z1)*(x2,z2).
    I=(0,0) X=(1,0) Z=(0,1) Y=(1,1);  e in {-1,0,+1}:
      I->0   X->z2*(2*x2-1)   Z->x2*(1-2*z2)   Y->z2-x2
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


def parse_signed(s):
    """
    '+XYZI' / '-X_' -> (sign, x, z) with x, z lists of 0/1, sign in {0,1}.
    """
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


def to_str(sign, x, z):
    """
    (sign, x, z) -> signed-Pauli string such as '+XYZ'.
    """
    body = "".join(_CHAR[x[j] | (z[j] << 1)] for j in range(len(x)))

    return ("-" if sign else "+") + body


def _compose(dst, src, n):
    """
    dst <- dst * src for signed (sign, x, z) triples, with exact sign.
    """
    sd, xd, zd = dst
    ss, xs, zs = src
    gsum = sum(g(xs[j], zs[j], xd[j], zd[j]) for j in range(n))
    sign = sd ^ ss ^ (1 if gsum % 4 == 2 else 0)
    x = [xd[j] ^ xs[j] for j in range(n)]
    z = [zd[j] ^ zs[j] for j in range(n)]

    return [sign, x, z]


def canonicalize(paulis, n):
    """
    Canonical signed-Pauli generators of <paulis>, by Gaussian elimination
    over the 2n-bit symplectic rows (x-block then z-block) with exact sign carry.
    """
    rows = [[int(s), list(map(int, x)), list(map(int, z))] for (s, x, z) in paulis]
    m = len(rows)

    def bit(row, c):
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
    An n-qubit Pauli i**phase * (tensor of I/X/Y/Z).

    phase is in 0..3 (0 -> +1, 1 -> +i, 2 -> -1, 3 -> -i). Hermitian Paulis
    (valid observables) have even phase.
    """

    __slots__ = ("x", "z", "phase")

    def __init__(self, x, z, phase=0):
        self.x = [int(v) & 1 for v in x]
        self.z = [int(v) & 1 for v in z]
        if len(self.x) != len(self.z):
            raise ValueError("x and z must have equal length")
        self.phase = int(phase) % 4

    @classmethod
    def parse(cls, s):
        """
        Parse '+XYZ', '-Y', '+iXZ', 'X_Z' (_ = identity).
        """
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
    def identity(cls, n):
        """
        The n-qubit identity Pauli.
        """
        return cls([0] * n, [0] * n, 0)

    @classmethod
    def from_sparse(cls, n, ops, phase=0):
        """
        Build from {qubit: 'X'|'Y'|'Z'}; unlisted qubits are identity.
        """
        x, z = [0] * n, [0] * n
        for q, p in ops.items():
            x[q], z[q] = _PAIR[p]

        return cls(x, z, phase)

    @property
    def n(self):
        return len(self.x)

    def tuple(self):
        """
        (sign, x, z) with sign in {0,1}; raises for non-Hermitian phases.
        """
        if self.phase % 2:
            raise ValueError("non-Hermitian Pauli (phase +-i) has no real sign")

        return (self.phase // 2, list(self.x), list(self.z))

    def commutes_with(self, other):
        # commute iff symplectic product XOR_j (x_j & oz_j) ^ (z_j & ox_j) == 0
        s = 0
        for j in range(self.n):
            s ^= (self.x[j] & other.z[j]) ^ (self.z[j] & other.x[j])

        return s & 1 == 0

    def __mul__(self, other):
        if self.n != other.n:
            raise ValueError("size mismatch")
        n = self.n
        gsum = sum(g(self.x[j], self.z[j], other.x[j], other.z[j]) for j in range(n))
        phase = (self.phase + other.phase + gsum) % 4
        x = [self.x[j] ^ other.x[j] for j in range(n)]
        z = [self.z[j] ^ other.z[j] for j in range(n)]

        return PauliString(x, z, phase)

    def __eq__(self, other):
        equal = (
            isinstance(other, PauliString)
            and self.phase == other.phase
            and self.x == other.x
            and self.z == other.z
        )

        return equal

    def __hash__(self):
        return hash((self.phase, tuple(self.x), tuple(self.z)))

    def __len__(self):
        return self.n

    def __repr__(self):
        body = "".join(_CHAR[self.x[j] | (self.z[j] << 1)] for j in range(self.n))

        return _PHASE[self.phase] + body
