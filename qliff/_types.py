Bits = list[int]  # per-qubit 0/1 vector
Signed = tuple[int, Bits, Bits]  # (sign in {0, 1}, x bits, z bits)
Targets = tuple[int, ...]  # qubit indices an op acts on
Op = tuple[str, Targets]  # (gate name, target qubits)
Branch = tuple[float, list[Op]]  # (weight, ops) -- one stabilizer-channel branch
Instruction = tuple[str, Targets, object]  # (name, targets, arg) in a Circuit
