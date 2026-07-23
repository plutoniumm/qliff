// The stratified self-normalised estimator, in TypeScript, mirroring
// qliff/noise/sampler.py (build_strata / stratum_masses / _poisson_binomial /
// pick_branch) and qliff/qec/sampler.py (StratifiedDetectorSampler). Every number
// the page shows is computed here from the same closed forms the simulator uses,
// so a reader can check the page against the library.
//
// One NOISE LOCATION is summarised by two weights: `a`, the identity (no-fault)
// branch's signed weight, and `b`, the summed signed weight of every fault branch.
// Trace preservation forces a + b = 1. The SAMPLER never sees those directly: it
// draws a branch with probability |w| / gamma, so it needs the absolute sums
// instead -- gfault = sum|w| over the fault branches and gamma = |a| + gfault.
// The gap between the two views is the whole story of this page.

import { mulberry32 } from "$lib/rng";

export type Kind = "AMPLITUDE_DAMP" | "RZ";

export interface Loc {
  /** identity-branch signed weight. */
  a: number;
  /** summed signed weight of the fault branches; a + b = 1. */
  b: number;
  /** sum |w| over the fault branches. */
  gfault: number;
  /** sum |w| over every branch: the per-location negativity, >= 1. */
  gamma: number;
  /** probability this location faults under the |.|/gamma sampling measure. */
  phi: number;
  /** mean branch SIGN given this location faulted: b / gfault, in [-1, 1]. */
  r: number;
}

// Amplitude damping at rate p over {I, Z, R}: q_I = (1-p+root)/2,
// q_Z = (1-p-root)/2 (negative for every 0 < p < 1), q_R = p, root = sqrt(1-p).
function dampingLoc (p: number): Loc {
  const root = Math.sqrt(Math.max(0, 1 - p));
  const qi = (1 - p + root) / 2;
  const qz = (1 - p - root) / 2;

  return finish(qi, qz + p, Math.abs(qz) + p);
}

// Coherent RZ(theta) over {I, Z, S, S-dagger} with the shared offset
// bd = (1 - cos - sin)/4; weights are [bd+cos, bd, bd+sin, bd].
function rotationLoc (theta: number): Loc {
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  const bd = (1 - cos - sin) / 4;
  const fault = [bd, bd + sin, bd];
  const signed = fault.reduce((s, w) => s + w, 0);
  const absolute = fault.reduce((s, w) => s + Math.abs(w), 0);

  return finish(bd + cos, signed, absolute);
}

// Assemble the derived quantities once, so both channels agree on the algebra.
function finish (a: number, b: number, gfault: number): Loc {
  const gamma = Math.abs(a) + gfault;

  return {
    a,
    b,
    gfault,
    gamma,
    phi: gamma > 0 ? gfault / gamma : 0,
    r: gfault > 0 ? b / gfault : 1,
  };
}

// One noise location of the requested channel at strength p (theta for RZ).
export function location (kind: Kind, p: number): Loc {
  if (kind === "RZ") {
    return rotationLoc(p);
  }

  return dampingLoc(p);
}

// Gamma = prod gamma_i over `count` identical locations: the magnitude every FLAT
// trajectory carries, faulty or not.
export function totalGamma (loc: Loc, count: number): number {
  return Math.pow(loc.gamma, count);
}

// Exact SIGNED quasiprobability mass per fault-count stratum: the coefficients of
// x^k in prod_i (a_i + b_i x). Same convolution as stratum_masses(), so the two
// implementations can be diffed line for line.
export function strataMass (loc: Loc, count: number): number[] {
  let poly = [1];

  for (let i = 0; i < count; i += 1) {
    const next = new Array(poly.length + 1).fill(0);

    for (let k = 0; k < poly.length; k += 1) {
      next[k] += poly[k] * loc.a;
      next[k + 1] += poly[k] * loc.b;
    }

    poly = next;
  }

  return poly;
}

// P(k faults) under the |.|/gamma SAMPLING measure: the Poisson-binomial of the
// per-location fault probabilities phi_i (_poisson_binomial in sampler.py).
export function samplingPk (loc: Loc, count: number): number[] {
  let probs = [1];

  for (let i = 0; i < count; i += 1) {
    const next = new Array(probs.length + 1).fill(0);

    for (let k = 0; k < probs.length; k += 1) {
      next[k] += probs[k] * (1 - loc.phi);
      next[k + 1] += probs[k] * loc.phi;
    }

    probs = next;
  }

  return probs;
}

// Mean trajectory sign inside stratum k: r^k for identical locations. This is
// exactly mass[k] / (Gamma * P(k)), the factor the self-normalised ratio divides
// by -- so it is also the page's measure of how badly a stratum's signs cancel.
export function meanSign (loc: Loc, k: number): number {
  return Math.pow(loc.r, k);
}

// Smallest number of strata that together hold `frac` of the total |mass|, so a
// bar chart can stop before the vanishing tail.
export function massCutoff (mass: number[], frac: number): number {
  const total = mass.reduce((s, m) => s + Math.abs(m), 0);
  let acc = 0;

  for (let k = 0; k < mass.length; k += 1) {
    acc += Math.abs(mass[k]);

    if (acc >= frac * total) {
      return k + 1;
    }
  }

  return mass.length;
}

// --------------------------------------------------------------------------
// Shot budgets
// --------------------------------------------------------------------------

// Shots for a `rel` relative error bar on a Pauli (binomial) logical error rate:
// N = (1 - LER) / (LER * rel^2). The same formula the LER page's cost bars use.
export function binomialShots (ler: number, rel: number): number {
  if (ler <= 0) {
    return Infinity;
  }

  return (1 - ler) / (ler * rel * rel);
}

// Flat importance sampling multiplies that budget by Gamma^2: every trajectory
// carries |w| = Gamma, so the variance of w * error is Gamma^2 times the Pauli one.
export function flatShots (ler: number, rel: number, gammaTotal: number): number {
  return binomialShots(ler, rel) * gammaTotal * gammaTotal;
}

// --------------------------------------------------------------------------
// One stratum, sampled
// --------------------------------------------------------------------------

export interface Tally {
  /** per-trajectory sign product, +1 or -1. */
  signs: number[];
  /** per-trajectory decoder verdict (true = logical error). */
  wrong: boolean[];
  plus: number;
  minus: number;
  /** sum of the signs: the self-normalising DENOMINATOR. */
  signSum: number;
  /** sum(sign * wrong) : the NUMERATOR. */
  hitSum: number;
  /** the ratio estimate of the conditional error rate F_k, or null if signs cancelled. */
  fHat: number | null;
  /** delta-method standard error of that ratio, or null. */
  stderr: number | null;
}

// Sample `n` trajectories from stratum k and self-normalise them. Each of the k
// faulty locations draws a fault branch with probability |w| / gfault, so its sign
// is -1 with probability (1 - r) / 2; the trajectory's sign is the product. The
// decoder verdict is drawn independently at rate `failRate` -- a stand-in for the
// real decoder, which keeps the ratio's behaviour (and its blow-up when the signs
// cancel) honest without shipping a decoder to the browser.
export function sampleStratum (
  r: number,
  k: number,
  n: number,
  failRate: number,
  seed: number,
): Tally {
  const rng = mulberry32(seed);
  const negative = (1 - r) / 2;
  const signs: number[] = [];
  const wrong: boolean[] = [];
  let plus = 0;
  let minus = 0;
  let signSum = 0;
  let hitSum = 0;

  for (let i = 0; i < n; i += 1) {
    let sign = 1;

    for (let f = 0; f < k; f += 1) {
      if (rng() < negative) {
        sign = -sign;
      }
    }

    const bad = rng() < failRate;
    signs.push(sign);
    wrong.push(bad);
    signSum += sign;
    hitSum += bad ? sign : 0;

    if (sign > 0) {
      plus += 1;
    } else {
      minus += 1;
    }
  }

  if (signSum === 0) {
    return {
      signs,
      wrong,
      plus,
      minus,
      signSum,
      hitSum,
      fHat: null,
      stderr: null,
    };
  }

  const fHat = hitSum / signSum;
  // threshold._stratified_error_rate's delta-method bar, per stratum:
  // sqrt(sum (wrong - F)^2) / |sum sign|.
  let spread = 0;

  for (let i = 0; i < n; i += 1) {
    const hit = wrong[i] ? 1 : 0;
    spread += (hit - fHat) * (hit - fHat);
  }

  return {
    signs,
    wrong,
    plus,
    minus,
    signSum,
    hitSum,
    fHat,
    stderr: Math.sqrt(spread) / Math.abs(signSum),
  };
}
