def expectation(sim, pauli):
    """
    ``<P>`` in {-1, 0, +1} for a Hermitian Pauli ``P`` on simulator ``sim``.

    ``pauli`` may be a :class:`PauliString` or a signed-Pauli string like
    ``"ZZ"`` or ``"-X"``. Does not disturb the state.
    """
    return sim.peek_observable(pauli)


def state_fidelity(a, b):
    """
    Fidelity ``|<a|b>|^2`` between the pure stabilizer states of two simulators.

    Computed as ``<b| P_a |b>`` by measuring each stabilizer generator of ``a``
    on a copy of ``b``: a deterministic -1 outcome gives fidelity 0, a random
    outcome halves it. The result is a power of two and exact.
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
