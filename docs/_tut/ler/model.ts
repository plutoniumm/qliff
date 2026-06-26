// Faithful TS reimplementation of the LER / fidelity maths that qliff computes
// in `qliff/qec/threshold.py` and `qliff/qec/codes.py`. Everything here mirrors
// the real pipeline -- sample, decode, compare -- so the interactive demos are
// honest, not hand-waved. Two model families live here:
//
//   1. The repetition code under bit-flip + majority vote. Its logical error
//      rate has a closed form (a binomial tail), and a seeded Monte-Carlo of it
//      reproduces qliff's binomial standard error sqrt(LER(1-LER)/N). This is
//      what powers the sampling-statistics demos.
//
//   2. A phenomenological surface-code threshold model LER(p,d) ~ (p/p_th)^ceil(d/2),
//      labelled clearly as a model wherever it is shown. It exists only to make
//      the threshold-crossing emerge cleanly from a formula the reader controls.

import { mulberry32 } from "$lib/rng";

// ---------------------------------------------------------------------------
// Fidelity / LER definitions (codes.py: logical_fidelity)
// ---------------------------------------------------------------------------

// One shot is a logical error iff the decoder's predicted observable flips
// disagree with the TRUE flips in ANY column (np.any(pred != obs, axis=1)).
export function shotIsError(predicted: boolean[], observed: boolean[]): boolean {
  for (let i = 0; i < predicted.length; i += 1) {
    if (predicted[i] !== observed[i]) {
      return true;
    }
  }

  return false;
}

// logical_fidelity = 1 - mean(shot is error). LER is its complement.
export function fidelityFromShots(predicted: boolean[][], observed: boolean[][]): number {
  if (predicted.length === 0) {
    return 1;
  }
  let wrong = 0;
  for (let s = 0; s < predicted.length; s += 1) {
    if (shotIsError(predicted[s], observed[s])) {
      wrong += 1;
    }
  }

  return 1 - wrong / predicted.length;
}

// ---------------------------------------------------------------------------
// Repetition code: exact (analytic) logical error rate
// ---------------------------------------------------------------------------

// log of n-choose-k via log-gamma, so binomial tails stay stable for large d.
function logChoose(n: number, k: number): number {
  return logGamma(n + 1) - logGamma(k + 1) - logGamma(n - k + 1);
}

// Lanczos approximation to ln Gamma(x).
function logGamma(x: number): number {
  const g = [
    676.5203681218851, -1259.1392167224028, 771.32342877765313,
    -176.61502916214059, 12.507343278686905, -0.13857109526572012,
    9.9843695780195716e-6, 1.5056327351493116e-7,
  ];
  if (x < 0.5) {
    return Math.log(Math.PI / Math.sin(Math.PI * x)) - logGamma(1 - x);
  }
  const z = x - 1;
  let a = 0.99999999999980993;
  const t = z + 7.5;
  for (let i = 0; i < g.length; i += 1) {
    a += g[i] / (z + i + 1);
  }

  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(a);
}

// Majority vote over `d` independent bit-flips at rate p fails when STRICTLY
// more than d/2 of them flip: LER = sum_{k > d/2} C(d,k) p^k (1-p)^(d-k).
// (For even d a d/2 tie is resolvable, so the strict inequality is the honest
// boundary for an odd-distance repetition code, which is the usual choice.)
export function repCodeLER(p: number, d: number): number {
  if (p <= 0) {
    return 0;
  }
  if (p >= 1) {
    return 1;
  }
  const lp = Math.log(p);
  const lq = Math.log(1 - p);
  const half = d / 2;
  let ler = 0;
  for (let k = 0; k <= d; k += 1) {
    if (k > half) {
      ler += Math.exp(logChoose(d, k) + k * lp + (d - k) * lq);
    }
  }

  return ler;
}

// ---------------------------------------------------------------------------
// Repetition code: ONE Monte-Carlo experiment (seeded, reproducible)
// ---------------------------------------------------------------------------

export interface MCResult {
  ler: number; // sampled logical error rate = wrong / N
  stderr: number; // binomial standard error sqrt(LER(1-LER)/N)
  errors: number; // number of logical errors seen
  shots: number;
}

// Run N independent repetition-code shots: flip each of d data bits with prob p,
// the decoder (majority vote) is "wrong" iff > d/2 flipped. We track only the
// verdict per shot, exactly as qliff compares predicted vs true observable.
export function repCodeMonteCarlo(p: number, d: number, shots: number, seed: number): MCResult {
  const rng = mulberry32(seed);
  let errors = 0;
  const half = d / 2;
  for (let s = 0; s < shots; s += 1) {
    let flips = 0;
    for (let q = 0; q < d; q += 1) {
      if (rng() < p) {
        flips += 1;
      }
    }
    if (flips > half) {
      errors += 1;
    }
  }
  const ler = shots > 0 ? errors / shots : 0;
  const stderr = shots > 0 ? Math.sqrt((ler * (1 - ler)) / shots) : 0;

  return { ler, stderr, errors, shots };
}

// A running trace of the estimate as shots accumulate, for the "watch it
// converge" animation. Returns the LER estimate after every `stride` shots.
export function repCodeTrace(
  p: number,
  d: number,
  shots: number,
  seed: number,
  stride: number,
): { n: number; ler: number; stderr: number }[] {
  const rng = mulberry32(seed);
  const half = d / 2;
  const out: { n: number; ler: number; stderr: number }[] = [];
  let errors = 0;
  for (let s = 1; s <= shots; s += 1) {
    let flips = 0;
    for (let q = 0; q < d; q += 1) {
      if (rng() < p) {
        flips += 1;
      }
    }
    if (flips > half) {
      errors += 1;
    }
    if (s % stride === 0 || s === shots) {
      const ler = errors / s;
      out.push({ n: s, ler, stderr: Math.sqrt((ler * (1 - ler)) / s) });
    }
  }

  return out;
}

// ---------------------------------------------------------------------------
// Weighted (coherent / non-Pauli) estimator -- threshold.py:_weighted_error_rate
// ---------------------------------------------------------------------------

export interface WeightedResult {
  ler: number; // clamp(mean(w * error), 0, 1)
  stderr: number; // std(w * error) / sqrt(N)
  shots: number;
}

// Importance-weighted LER. Coherent noise is sampled from a quasiprobability
// whose negativity is gamma >= 1: shots carry a signed weight of magnitude ~gamma
// that averages to the true probability but inflates the variance. We model that
// honestly: each shot draws a sign (+/-) from the quasiprobability and a weight
// magnitude `gamma`, plus an "error" indicator at the underlying rate. The point
// the demo makes -- bigger gamma blows up std(w*error) -- is the real effect.
export function weightedMonteCarlo(
  trueLER: number,
  gamma: number,
  shots: number,
  seed: number,
): WeightedResult {
  const rng = mulberry32(seed);
  // For negativity gamma the quasiprobability splits as gamma = p_plus + p_minus
  // with p_plus - p_minus = 1, so p_minus = (gamma - 1) / 2. A shot's signed
  // weight is +gamma (prob p_plus/gamma) or -gamma (prob p_minus/gamma); these
  // average to 1, leaving mean(w * error) an unbiased estimate of trueLER.
  const pMinus = (gamma - 1) / 2 / gamma;
  const contribs = new Float64Array(shots);
  for (let s = 0; s < shots; s += 1) {
    const sign = rng() < pMinus ? -1 : 1;
    const w = sign * gamma;
    const err = rng() < trueLER ? 1 : 0;
    contribs[s] = w * err;
  }
  let mean = 0;
  for (let s = 0; s < shots; s += 1) {
    mean += contribs[s];
  }
  mean = shots > 0 ? mean / shots : 0;
  let varSum = 0;
  for (let s = 0; s < shots; s += 1) {
    const dlt = contribs[s] - mean;
    varSum += dlt * dlt;
  }
  const std = shots > 0 ? Math.sqrt(varSum / shots) : 0;
  const stderr = shots > 0 ? std / Math.sqrt(shots) : 0;

  return { ler: Math.min(1, Math.max(0, mean)), stderr, shots };
}

// ---------------------------------------------------------------------------
// Phenomenological surface-code threshold model (clearly a MODEL)
// ---------------------------------------------------------------------------

// LER(p, d) ~ A * (p / p_th)^ceil(d/2), saturating toward a high-p plateau so the
// curves cross at p_th and don't run off to infinity. Below p_th larger d
// suppresses the LER like a power law; above p_th it amplifies it. This is the
// standard sub-threshold scaling, written so the crossing emerges from the
// formula as the reader moves the sliders -- not a fit to any real data.
export function surfaceModelLER(p: number, d: number, pTh: number, a: number): number {
  if (p <= 0) {
    return 0;
  }
  const exponent = Math.ceil(d / 2);
  const raw = a * Math.pow(p / pTh, exponent);
  // Soft saturation toward 0.5 (a maximally-scrambled logical qubit) so curves
  // bend over above threshold instead of exceeding 1.
  const plateau = 0.5;

  return (plateau * raw) / (plateau + raw);
}

// Sweep the model across a log-spaced p-range for one distance.
export function surfaceModelCurve(
  d: number,
  pTh: number,
  a: number,
  pMin: number,
  pMax: number,
  points: number,
): { p: number; ler: number }[] {
  const out: { p: number; ler: number }[] = [];
  const lo = Math.log(pMin);
  const hi = Math.log(pMax);
  for (let i = 0; i < points; i += 1) {
    const p = Math.exp(lo + ((hi - lo) * i) / (points - 1));
    out.push({ p, ler: surfaceModelLER(p, d, pTh, a) });
  }

  return out;
}

// Analytic repetition-code LER curve across a p-range (linear or log spaced).
export function repCodeCurve(
  d: number,
  pMin: number,
  pMax: number,
  points: number,
  logSpaced = false,
): { p: number; ler: number }[] {
  const out: { p: number; ler: number }[] = [];
  for (let i = 0; i < points; i += 1) {
    const f = i / (points - 1);
    const p = logSpaced
      ? Math.exp(Math.log(pMin) + (Math.log(pMax) - Math.log(pMin)) * f)
      : pMin + (pMax - pMin) * f;
    out.push({ p, ler: repCodeLER(p, d) });
  }

  return out;
}
