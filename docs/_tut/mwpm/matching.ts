// In-browser MWPM logic for a 1D repetition code, mirroring how qliff's
// MwpmDecoder (qliff/qec/decoder.py) decodes a DetectorErrorModel:
//
//   * data qubits sit in a line; a Z-check sits between each neighbouring pair.
//   * an X error on a data qubit flips the parity of its (≤2) adjacent checks.
//   * a check FIRES (becomes a "defect") iff the noise changed its deterministic
//     value -- i.e. the parity of errors it touches is odd. This is the
//     detection event: measured parity XOR noiseless value.
//   * a *chain* of errors only lights its two endpoints -- interior checks see
//     two flips and cancel. So the syndrome is a sparse SET of lit defects.
//   * each error mechanism flipping ≤2 checks is a graph EDGE; one flipping a
//     single check (a boundary qubit) connects that check to a virtual BOUNDARY
//     node. (qliff: graphlike_edges keeps len(dets) <= 2.)
//   * edge weight w = log((1-p)/p) (dem.weights()). Minimising total matched
//     weight == maximising the product of error probabilities == the MOST LIKELY
//     error under independent noise.
//   * the matched edges tell us which qubits to flip back (the correction). A
//     LOGICAL error happens when correction XOR real-error wraps the line --
//     here the rep-code logical = global parity of the data, read as whether the
//     combined chain crosses the left boundary an odd number of times.
//
// d data qubits  ->  d-1 internal checks (between neighbours) on indices
// 0..d-2, plus two virtual boundaries (left, right). We label internal check i
// as the gap between data[i] and data[i+1].

export const LEFT = -1; // virtual boundary node id (left of qubit 0)
export const RIGHT = -2; // virtual boundary node id (right of qubit d-1)

export interface RepCode {
  d: number; // number of data qubits
  p: number; // physical error probability per qubit
}

// Edge cost between two graph nodes = log((1-p)/p) * (number of qubits the chain
// flips). A defect at check i and check j (i<j) is connected by flipping qubits
// i+1..j (the data qubits strictly between the two gaps), a chain of length
// j-i. A defect at check i to the LEFT boundary flips qubits 0..i (length i+1);
// to the RIGHT boundary flips qubits i+1..d-1 (length d-1-i).
export function edgeWeight(p: number): number {
  const pc = Math.min(Math.max(p, 1e-9), 0.5 - 1e-9);

  return Math.log((1 - pc) / pc);
}

// Number of data qubits the shortest chain between two graph nodes flips.
export function chainLength(a: number, b: number, d: number): number {
  // boundary <-> boundary never appears in a real matching; guard anyway.
  if (a === LEFT && b === RIGHT) {
    return d;
  }
  if (a === LEFT || b === LEFT) {
    const c = a === LEFT ? b : a;

    return c + 1; // gap c is between qubit c and c+1; left chain flips 0..c

  }
  if (a === RIGHT || b === RIGHT) {
    const c = a === RIGHT ? b : a;

    return d - 1 - c; // right chain flips c+1..d-1
  }

  return Math.abs(a - b);
}

// The exact set of data qubits flipped by the chain joining two graph nodes.
export function chainQubits(a: number, b: number, d: number): number[] {
  const out: number[] = [];
  if ((a === LEFT && b === RIGHT) || (a === RIGHT && b === LEFT)) {
    for (let q = 0; q < d; q += 1) {
      out.push(q);
    }

    return out;
  }
  if (a === LEFT || b === LEFT) {
    const c = a === LEFT ? b : a;
    for (let q = 0; q <= c; q += 1) {
      out.push(q);
    }

    return out;
  }
  if (a === RIGHT || b === RIGHT) {
    const c = a === RIGHT ? b : a;
    for (let q = c + 1; q < d; q += 1) {
      out.push(q);
    }

    return out;
  }
  const lo = Math.min(a, b);
  const hi = Math.max(a, b);
  for (let q = lo + 1; q <= hi; q += 1) {
    out.push(q);
  }

  return out;
}

// Syndrome: which internal checks fire given a boolean error per data qubit.
// Check i (between qubit i and i+1) fires iff errors[i] XOR errors[i+1]. With
// open boundaries the "checks" beyond the ends are the virtual boundary nodes
// and never fire on their own; an odd parity at an end is absorbed by matching a
// defect to that boundary.
export function syndrome(errors: boolean[]): number[] {
  const d = errors.length;
  const defects: number[] = [];
  for (let i = 0; i < d - 1; i += 1) {
    if (errors[i] !== errors[i + 1]) {
      defects.push(i);
    }
  }

  return defects;
}

export interface MatchResult {
  pairs: [number, number][]; // each pair of graph nodes (defect ids or LEFT/RIGHT)
  weight: number; // total matched weight (in units of w = log((1-p)/p))
  totalChain: number; // total data qubits flipped by the correction
  correction: boolean[]; // per-qubit correction
}

// Pairing cost in *weight* units between two graph nodes.
function pairWeight(a: number, b: number, d: number, w: number): number {
  return chainLength(a, b, d) * w;
}

// Enumerate every perfect matching of the defect set (each defect paired with
// another defect, the LEFT boundary, or the RIGHT boundary) and return the
// minimum-weight one. Boundaries are unlimited-capacity, so we model them by
// giving each defect the *option* of going to its nearer boundary on its own.
//
// Concretely: we recursively take the first unmatched defect and either (a) pair
// it with the boundary (left or right -- pick the cheaper, which is always the
// nearer end for a single defect-to-boundary chain), or (b) pair it with any
// later unmatched defect. This covers all perfect matchings on the graph where
// boundary nodes may be used any number of times. d <= ~12 keeps this trivial
// for teaching.
export function minWeightMatching(defects: number[], d: number, p: number): MatchResult {
  const w = edgeWeight(p);

  function solve(remaining: number[]): { pairs: [number, number][]; weight: number } {
    if (remaining.length === 0) {
      return { pairs: [], weight: 0 };
    }
    const [first, ...rest] = remaining;

    // option (a): match `first` to its cheaper boundary.
    const toLeft = pairWeight(first, LEFT, d, w);
    const toRight = pairWeight(first, RIGHT, d, w);
    const bnode = toLeft <= toRight ? LEFT : RIGHT;
    const bcost = Math.min(toLeft, toRight);
    const sub = solve(rest);
    let best: { pairs: [number, number][]; weight: number } = {
      pairs: [[first, bnode], ...sub.pairs],
      weight: bcost + sub.weight,
    };

    // option (b): match `first` to each later defect.
    for (let k = 0; k < rest.length; k += 1) {
      const partner = rest[k];
      const next = [...rest.slice(0, k), ...rest.slice(k + 1)];
      const subk = solve(next);
      const cand: { pairs: [number, number][]; weight: number } = {
        pairs: [[first, partner], ...subk.pairs],
        weight: pairWeight(first, partner, d, w) + subk.weight,
      };
      if (cand.weight < best.weight) {
        best = cand;
      }
    }

    return best;
  }

  const { pairs, weight } = solve(defects);

  return finishMatch(pairs, weight, d, w);
}

// Turn a list of matched pairs into a full correction + chain summary.
export function finishMatch(
  pairs: [number, number][],
  weight: number,
  d: number,
  w: number,
): MatchResult {
  const correction = new Array<boolean>(d).fill(false);
  let totalChain = 0;
  for (const [a, b] of pairs) {
    const qs = chainQubits(a, b, d);
    totalChain += qs.length;
    for (const q of qs) {
      // Applying a chain flips its qubits; overlapping chains XOR (cancel).
      correction[q] = !correction[q];
    }
  }

  return { pairs, weight, totalChain, correction };
}

// Cost (in weight units) of an ARBITRARY user-supplied matching, for the
// "beat the optimum" interaction. Pairs may include boundary nodes.
export function matchingWeight(pairs: [number, number][], d: number, p: number): number {
  const w = edgeWeight(p);
  let total = 0;
  for (const [a, b] of pairs) {
    total += pairWeight(a, b, d, w);
  }

  return total;
}

// Did the correction succeed? The rep-code logical operator is the global parity
// of the data register (equivalently: does the combined error+correction chain
// cross the LEFT boundary an odd number of times?). The decode is a logical
// FAILURE iff residual = error XOR correction is a non-trivial logical, i.e. it
// connects the two boundaries -- detected as: the residual leaves NO defects
// (it's a valid stabiliser/logical) AND it flips the logical observable.
//
// For the rep code the logical observable = parity of a single chosen qubit's
// readout vs a reference; the standard choice is "does the residual chain span
// the whole line" == parity of (number of residual flips on the left half is
// odd in a way that crosses). The clean, exact test: residual must have empty
// syndrome (correction matched the syndrome), and then it's logical iff the
// residual flips an odd number of qubits "to the left of a cut", which for the
// rep code is simply: residual qubit 0 differs from the all-same ground => use
// the boundary-crossing parity.
//
// Concretely and robustly: count how many matched chains cross the LEFT
// boundary in the *combined* error+correction picture. We compute residual and
// test whether it equals a logical operator (the all-ones chain spanning the
// line is the logical X of the rep code) up to stabilisers. Easiest exact test:
// residual has empty syndrome, and parity of residual over the *left-anchored*
// observable (qubit 0..k) is odd.
export function logicalFailed(errors: boolean[], correction: boolean[]): boolean {
  const d = errors.length;
  const residual: boolean[] = errors.map((e, i) => e !== correction[i]);
  // Must be a valid (closed) operator: empty syndrome.
  for (let i = 0; i < d - 1; i += 1) {
    if (residual[i] !== residual[i + 1]) {
      // not closed -- shouldn't happen for a matched correction, treat as fail.
      return true;
    }
  }
  // residual is now all-equal: either all-false (identity) or all-true (logical
  // X spanning the line). all-true == logical error.
  return residual[0] === true;
}

// Brute-force-free helper: list of defect node positions (gap index 0..d-2)
// mapped to an on-screen x in [0,1] for the matching graph. (Defect i sits at
// the gap between data qubit i and i+1.)
export function gapX(i: number, d: number): number {
  // data qubit q at x=(q+0.5)/d centre; gap i between q=i and q=i+1.
  return (i + 1) / d;
}

export function qubitX(q: number, d: number): number {
  return (q + 0.5) / d;
}
