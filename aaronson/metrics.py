def expectation(sim, pauli):
    """
    <P> in {-1, 0, +1} for Hermitian P (see Simulator.peek_observable).
    """
    return sim.peek_observable(pauli)


def state_fidelity(a, b):
    """
    Fidelity |<a|b>|^2 of two pure stabilizer states (exact; a power of two).
    Measure each stabilizer generator of a on a copy of b: deterministic
    -1 -> 0, random outcome -> halve.
    """
    if a.num_qubits != b.num_qubits:
        raise ValueError("states must have the same qubit count")
    work = b.copy()
    fidelity = 1.0
    for gen in a.stabilizers():
        value, random = work.measure_pauli(gen, force=1)
        if random:
            fidelity *= 0.5
        elif value != 1:
            return 0.0

    return fidelity
