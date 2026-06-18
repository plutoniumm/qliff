def expectation(sim, pauli):
    """
    <P> in {-1, 0, +1} for Hermitian P (see Simulator.peek).
    """
    return sim.peek(pauli)


def fidelity(a, b):
    """
    Fidelity |<a|b>|^2 of two pure stabilizer states; exact, always a power of
    two. Measures each stabilizer of a on a copy of b: deterministic -1 -> 0,
    random outcome -> halve.
    """
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
