// Quasiprobability decompositions of qliff's NON-Pauli stabilizer channels.
// These mirror qliff/noise/channel.py: every weight printed on the page
// is the real value the simulator would draw a branch from. A "branch" is a signed
// weight attached to a list of Clifford ops; for Pauli channels the weights are a
// genuine probability distribution (>= 0, sum 1), for these non-Pauli channels the
// weights are SIGNED quasiprobabilities whose absolute values sum to gamma >= 1.

export interface Branch {
  // a short Clifford label (the "core" gate of this branch) and its signed weight.
  label: string;
  weight: number;
}

// Coherent rotation RZ(theta) = exp(-i theta Z / 2), written as a quasiprobability
// mix of the Cliffords diagonal in Z: {I, Z, S, S_DAG}. With cos = cos(theta),
// sin = sin(theta), bd = (1 - cos - sin) / 4:
//   I     -> bd + cos
//   Z     -> bd
//   S     -> bd + sin
//   S_DAG -> bd
// (RX(theta) = H RZ(theta) H is the same mixture wrapped in H -- identical weights.)
export function rotationBranches(theta: number): Branch[] {
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  const bd = (1 - cos - sin) / 4;

  return [
    { label: "I", weight: bd + cos },
    { label: "Z", weight: bd },
    { label: "S", weight: bd + sin },
    { label: "S†", weight: bd },
  ];
}

// Amplitude damping AmplitudeDamping(p): energy loss with probability p, written
// exactly over {I, Z, R = reset to |0>}:
//   q_I = [(1-p) + sqrt(1-p)] / 2
//   q_Z = [(1-p) - sqrt(1-p)] / 2   (< 0 for any p in (0, 1))
//   q_R = p
export function dampingBranches(p: number): Branch[] {
  const root = Math.sqrt(Math.max(0, 1 - p));
  const qI = (1 - p + root) / 2;
  const qZ = (1 - p - root) / 2;

  return [
    { label: "I", weight: qI },
    { label: "Z", weight: qZ },
    { label: "R", weight: p },
  ];
}

// Depolarizing channel at strength p (for the coherent-vs-incoherent contrast):
// {I, X, Y, Z} with weights (1 - p, p/3, p/3, p/3). All non-negative -> gamma = 1.
export function depolarizeBranches(p: number): Branch[] {
  return [
    { label: "I", weight: 1 - p },
    { label: "X", weight: p / 3 },
    { label: "Y", weight: p / 3 },
    { label: "Z", weight: p / 3 },
  ];
}

// Total weight Sum(w): 1 for any trace-preserving channel.
export function totalWeight(branches: Branch[]): number {
  return branches.reduce((s, b) => s + b.weight, 0);
}

// Negativity gamma = Sum |w|: the L1 norm of the signed weights. gamma = 1 iff the
// channel is a true probability mixture of Cliffords; gamma > 1 is the price of the
// non-Cliffordness, and bounds the per-location sampling-variance blow-up.
export function gamma(branches: Branch[]): number {
  return branches.reduce((s, b) => s + Math.abs(b.weight), 0);
}

// Convenience: gamma of RZ(theta) as a closed scalar over a sweep.
export function rotationGamma(theta: number): number {
  return gamma(rotationBranches(theta));
}

// Convenience: gamma of AmplitudeDamping(p). The docstring's "~ 3p/4" is the small-p
// asymptote; this returns the exact value Sum|q| = q_I + |q_Z| + p.
export function dampingGamma(p: number): number {
  return gamma(dampingBranches(p));
}
