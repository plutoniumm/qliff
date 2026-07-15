// The factor-graph maximum-likelihood decoder, built on tensor.ts, for a tiny
// code the explainer can run live. This is the browser twin of
// MaxLikelihoodDecoder in qliff/qec/tn.py: one biased-COPY tensor per error
// mechanism, one parity tensor per detector (pinned to the syndrome bit), one
// parity tensor with an OPEN leg per observable; contract -> a tensor indexed by
// the observables holding the total probability weight of each logical class;
// argmax = the most likely correction.
//
// We use a repetition code because it is the smallest code with genuine
// DEGENERACY: many distinct error sets give the same syndrome AND the same
// logical effect, so summing (MLD) can disagree with picking the single
// lowest-weight error (MWPM-style). That disagreement is the whole point.

import {
  Tensor,
  biasedCopy,
  parity,
  contract,
  type ContractStep,
} from "./tensor";

// A detector error model: a list of independent error mechanisms, each with a
// prior p, the detectors it flips, and the observables it flips. Mirrors
// DetectorErrorModel.mechanisms (a list of (p, dets, obs)).
export interface Mechanism {
  p: number;
  dets: number[];
  obs: number[];
  label: string; // human tag, e.g. "qubit 2"
}

export interface Dem {
  numDetectors: number;
  numObservables: number;
  mechanisms: Mechanism[];
}

// d data qubits in a line -> (d-1) parity checks between neighbours + the two
// boundary checks; logical = parity of the whole chain. We model the standard
// repetition-code DEM: a flip on data qubit i toggles the (up to two) checks it
// touches. The logical observable is read off one boundary, so a flip on qubit i
// flips the observable iff i is to the left of the read-out cut. We put the cut
// at the far right: every qubit flips the observable -> a full chain of flips is
// a logical operator. This is the textbook repetition-code DEM and exhibits the
// degeneracy we want.
//
// `measP` (optional) adds one degree-1 MEASUREMENT-ERROR mechanism per detector:
// it lights that single detector and flips no observable, as a faulty
// stabilizer readout does in a circuit-level DEM. These extra mechanisms make a
// single syndrome explainable many ways (a measurement glitch OR a data chain),
// so a logical class genuinely contains several error patterns -- real
// intra-class degeneracy to sum over, not just two competing chains.
export function repetitionDem(dataQubits: number, p: number, measP = 0): Dem {
  const numDetectors = dataQubits - 1; // interior checks between neighbours
  const mechs: Mechanism[] = [];

  for (let i = 0; i < dataQubits; i += 1) {
    const dets: number[] = [];
    if (i - 1 >= 0) {
      dets.push(i - 1); // check to the left of qubit i
    }
    if (i < numDetectors) {
      dets.push(i); // check to the right of qubit i
    }
    // observable = parity of qubits 0..d-1; every single flip toggles it.
    mechs.push({ p, dets, obs: [0], label: `q${i}` });
  }

  if (measP > 0) {
    for (let d = 0; d < numDetectors; d += 1) {
      mechs.push({ p: measP, dets: [d], obs: [], label: `m${d}` });
    }
  }

  return { numDetectors, numObservables: 1, mechanisms: mechs };
}

// ---- factor-graph layout (what the diagram draws) -------------------------

export interface CopyNode {
  m: number; // mechanism index
  p: number;
  legs: { kind: "det" | "obs"; idx: number; leg: string }[];
  label: string;
}

export interface DetNode {
  d: number;
  legs: string[]; // legs into incident copy tensors
  mechs: number[];
}

export interface ObsNode {
  o: number;
  legs: string[]; // legs into incident copy tensors
  openLeg: string;
  mechs: number[];
}

export interface FactorGraph {
  copies: CopyNode[];
  detectors: DetNode[];
  observables: ObsNode[];
}

function detLeg(m: number, d: number): string {
  return `d_${m}_${d}`;
}
function obsLeg(m: number, o: number): string {
  return `o_${m}_${o}`;
}
function obsOut(o: number): string {
  return `obs_${o}`;
}

export function buildFactorGraph(dem: Dem): FactorGraph {
  const detMechs: number[][] = Array.from({ length: dem.numDetectors }, () => []);
  const obsMechs: number[][] = Array.from({ length: dem.numObservables }, () => []);

  dem.mechanisms.forEach((mech, m) => {
    mech.dets.forEach((d) => detMechs[d].push(m));
    mech.obs.forEach((o) => obsMechs[o].push(m));
  });

  const copies: CopyNode[] = dem.mechanisms.map((mech, m) => ({
    m,
    p: mech.p,
    label: mech.label,
    legs: [
      ...mech.dets.map((d) => ({ kind: "det" as const, idx: d, leg: detLeg(m, d) })),
      ...mech.obs.map((o) => ({ kind: "obs" as const, idx: o, leg: obsLeg(m, o) })),
    ],
  }));

  const detectors: DetNode[] = detMechs.map((mechs, d) => ({
    d,
    mechs,
    legs: mechs.map((m) => detLeg(m, d)),
  }));

  const observables: ObsNode[] = obsMechs.map((mechs, o) => ({
    o,
    mechs,
    legs: mechs.map((m) => obsLeg(m, o)),
    openLeg: obsOut(o),
  }));

  return { copies, detectors, observables };
}

// ---- assemble the tensors for one syndrome --------------------------------

export function demTensors(dem: Dem, fg: FactorGraph, syndrome: number[]): Tensor[] {
  const tensors: Tensor[] = [];

  // one biased COPY per mechanism, legs = its detector legs + observable legs.
  fg.copies.forEach((node) => {
    const legs = node.legs.map((l) => l.leg);
    if (legs.length === 0) {
      return;
    }
    tensors.push(biasedCopy(legs.length, node.p).withLegs(legs));
  });

  // one parity per observable, with the OPEN leg appended (parity target 0:
  // XOR of incident mechanisms == open-leg bit).
  fg.observables.forEach((node) => {
    const legs = [...node.legs, node.openLeg];
    tensors.push(parity(legs.length, 0).withLegs(legs));
  });

  // one parity per detector, pinned to the observed syndrome bit.
  fg.detectors.forEach((node) => {
    tensors.push(parity(node.legs.length, syndrome[node.d] & 1).withLegs(node.legs));
  });

  return tensors;
}

export interface DecodeResult {
  classWeights: number[]; // weight per logical class (length 2^numObservables)
  prediction: number[]; // argmax class as a bit vector over observables
  steps: ContractStep[];
  peakRank: number;
  openLegs: string[];
}

// Run the exact contraction (or chi-truncated if maxBond given) and read
// the per-logical-class weights off the open legs. _decode_one in tn.py.
export function decode(
  dem: Dem,
  fg: FactorGraph,
  syndrome: number[],
  maxBond?: number,
): DecodeResult {
  const tensors = demTensors(dem, fg, syndrome);
  const openLegs = fg.observables.map((o) => o.openLeg);
  const { tensor, steps, peakRank } = contract(tensors, openLegs, maxBond);
  const weights = Array.from(tensor.data);

  let best = 0;
  let bestVal = -Infinity;
  weights.forEach((w, idx) => {
    if (w > bestVal) {
      bestVal = w;
      best = idx;
    }
  });

  // unravel best index into bits over observables (MSB-first = leg order).
  const nObs = dem.numObservables;
  const prediction: number[] = [];
  for (let a = 0; a < nObs; a += 1) {
    prediction.push((best >> (nObs - 1 - a)) & 1);
  }
  const anyPositive = weights.some((w) => w > 0);

  return {
    classWeights: weights,
    prediction: anyPositive ? prediction : new Array(nObs).fill(0),
    steps,
    peakRank,
    openLegs,
  };
}

// ---- enumerate the error configurations behind one syndrome ---------------
// For the small codes this is feasible: walk all 2^numMechanisms error patterns,
// keep those consistent with the syndrome, and bucket their probabilities by
// logical class. This is literally what the contraction sums -- we expose it so
// the page can show the sum term by term and confirm the TN value.

export interface ErrorConfig {
  id: number; // the error pattern packed as a bitmask (stable identifier)
  bits: number[]; // which mechanisms fired
  prob: number; // product of p / (1-p) factors
  logical: number; // logical class (bit vector packed MSB-first)
  detsOk: boolean; // matches the syndrome
}

export function enumerateErrors(dem: Dem, syndrome: number[]): {
  configs: ErrorConfig[];
  classWeights: number[];
} {
  const nM = dem.mechanisms.length;
  const nObs = dem.numObservables;
  const classWeights = new Array<number>(1 << nObs).fill(0);
  const configs: ErrorConfig[] = [];

  for (let pattern = 0; pattern < 1 << nM; pattern += 1) {
    const bits: number[] = [];
    const detParity = new Array<number>(dem.numDetectors).fill(0);
    const obsParity = new Array<number>(nObs).fill(0);
    let prob = 1;
    for (let m = 0; m < nM; m += 1) {
      const fired = (pattern >> m) & 1;
      bits.push(fired);
      const mech = dem.mechanisms[m];
      prob *= fired ? mech.p : 1 - mech.p;
      if (fired) {
        mech.dets.forEach((d) => {
          detParity[d] ^= 1;
        });
        mech.obs.forEach((o) => {
          obsParity[o] ^= 1;
        });
      }
    }
    const detsOk = detParity.every((v, d) => v === (syndrome[d] & 1));
    let logical = 0;
    for (let a = 0; a < nObs; a += 1) {
      logical = (logical << 1) | obsParity[a];
    }
    if (detsOk) {
      classWeights[logical] += prob;
    }
    configs.push({ id: pattern, bits, prob, logical, detsOk });
  }

  return { configs, classWeights };
}

// A naive minimum-weight (MWPM-flavoured) pick: among the syndrome-consistent
// error configs, take the single MOST PROBABLE one and report ITS logical class.
// This ignores degeneracy and is where MLD can beat it.
export function minWeightPick(dem: Dem, syndrome: number[]): {
  logical: number | null;
  prob: number;
  bits: number[] | null;
} {
  const { configs } = enumerateErrors(dem, syndrome);
  let best: ErrorConfig | null = null;
  configs.forEach((cfg) => {
    if (!cfg.detsOk) {
      return;
    }
    if (best === null || cfg.prob > best.prob) {
      best = cfg;
    }
  });
  if (best === null) {
    return { logical: null, prob: 0, bits: null };
  }
  const chosen = best as ErrorConfig;

  return { logical: chosen.logical, prob: chosen.prob, bits: chosen.bits };
}
