// The physics optimisations, in TypeScript, mirroring the Rust core in
// src/tableau.rs (frame_chunk, estimate_chunk, word_g). Every number a page island
// shows is computed here from the same rules the simulator runs, so a reader can
// diff the page against the core.
//
// A Pauli FRAME is a sign-free two-bit-per-qubit operator (fx, fz) carried per
// shot. Because it drops the sign, the whole propagation is XOR: no i-phases, no
// row sums. Frames pack 64 shots into a u64 in the core; here we hold one boolean
// per shot so a small grid can be drawn cell by cell.

import { mulberry32 } from "$lib/rng";

// --------------------------------------------------------------------------
// 1. The Pauli frame sampler
// --------------------------------------------------------------------------

export interface FrameGrid {
  /** X-frame on the top data qubit, one bit per shot. */
  q0: boolean[];
  /** X-frame on the bottom data qubit, one bit per shot. */
  q1: boolean[];
  /** ancilla word after CX q0->a, CX q1->a: fx[a] = fx[q0] XOR fx[q1]. */
  synd: boolean[];
  /** recorded bit = reference (0 here) XOR fx[a]; equals synd. */
  record: boolean[];
  /** shots with at least one X fault on the two data qubits. */
  touched: number;
}

// One Z-parity check of a repetition code: two data qubits feed one ancilla via
// CX q0->a then CX q1->a, so X faults copy forward and the ancilla's X-frame is
// their XOR (frame_chunk's OP_CX rule, fx[b] ^= fx[a]). The noiseless reference
// measures 0, so the recorded bit is just fx[a]. Faults are Bernoulli(phi) per
// shot; the whole cohort rides the same instruction stream.
export function frameGrid(phi: number, shots: number, seed: number): FrameGrid {
  const rng = mulberry32(seed);
  const q0: boolean[] = [];
  const q1: boolean[] = [];
  const synd: boolean[] = [];
  const record: boolean[] = [];
  let touched = 0;

  for (let s = 0; s < shots; s += 1) {
    const a = rng() < phi;
    const b = rng() < phi;
    const parity = a !== b;

    q0.push(a);
    q1.push(b);
    synd.push(parity);
    record.push(parity); // reference bit is 0, so record = 0 XOR fx[a]

    if (a || b) {
      touched += 1;
    }
  }

  return {
    q0,
    q1,
    synd,
    record,
    touched,
  };
}

// --------------------------------------------------------------------------
// 2. Rare-error noise via geometric skips
// --------------------------------------------------------------------------

export interface SkipRun {
  /** indices of the shots that faulted. */
  faulty: number[];
  /** uniform draws spent finding them: one per skip plus the overshoot. */
  draws: number;
}

// Jump straight to the faulty shots. With per-shot fault probability phi the gaps
// between faults are geometric, so skip = floor(ln(1-U) / ln(1-phi)) lands on the
// next faulty shot without touching the ones in between (frame_chunk's kind-2
// path). phi = 0 touches nothing; phi = 1 faults every shot.
export function geometricSkips(phi: number, shots: number, seed: number): SkipRun {
  if (phi <= 0) {
    return { faulty: [], draws: 0 };
  }

  if (phi >= 1) {
    return { faulty: Array.from({ length: shots }, (_, s) => s), draws: shots };
  }

  const rng = mulberry32(seed);
  const ln1m = Math.log(1 - phi);
  const faulty: number[] = [];
  let s = 0;
  let draws = 0;

  for (;;) {
    const skip = Math.floor(Math.log(1 - rng()) / ln1m);
    draws += 1;
    s += skip;

    if (s >= shots) {
      break;
    }

    faulty.push(s);
    s += 1;
  }

  return { faulty, draws };
}

// --------------------------------------------------------------------------
// 3. The signed quasiprobability importance estimator
// --------------------------------------------------------------------------

export type Kind = "AMPLITUDE_DAMP" | "RZ";

export interface Loc {
  /** identity-branch signed weight. */
  a: number;
  /** signed fault weight; a + b = 1. */
  b: number;
  /** sum |w| over the fault branches. */
  gfault: number;
  /** per-location negativity, sum |w| over every branch, >= 1. */
  gamma: number;
  /** probability this location faults under the |.|/gamma measure. */
  phi: number;
  /** probability a fault carries a NEGATIVE sign, given it faulted. */
  pNeg: number;
}

// Amplitude damping at rate p over {I, Z, R}: q_I = (1-p+root)/2,
// q_Z = (1-p-root)/2 < 0, q_R = p, root = sqrt(1-p). R is opcode 9 (reset) in the
// core's branch stream. Z carries the only negative weight.
function dampingLoc(p: number): Loc {
  const root = Math.sqrt(Math.max(0, 1 - p));
  const qi = (1 - p + root) / 2;
  const qz = (1 - p - root) / 2;
  const qr = p;
  const gfault = Math.abs(qz) + qr;

  return finish(qi, qz + qr, gfault, Math.abs(qz) / gfault);
}

// Coherent RZ(theta) over {I, Z, S, S-dagger}, offset bd = (1-cos-sin)/4; the two
// bd branches (Z and S-dagger) and the S branch are the faults, two of them
// negative for small theta.
function rotationLoc(theta: number): Loc {
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  const bd = (1 - cos - sin) / 4;
  const fault = [bd, bd + sin, bd]; // Z, S, S-dagger
  const signed = fault.reduce((s, w) => s + w, 0);
  const gfault = fault.reduce((s, w) => s + Math.abs(w), 0);
  const neg = fault.reduce((s, w) => s + (w < 0 ? Math.abs(w) : 0), 0);

  return finish(bd + cos, signed, gfault, gfault > 0 ? neg / gfault : 0);
}

function finish(a: number, b: number, gfault: number, pNeg: number): Loc {
  const gamma = Math.abs(a) + gfault;

  return {
    a,
    b,
    gfault,
    gamma,
    phi: gamma > 0 ? gfault / gamma : 0,
    pNeg,
  };
}

export function location(kind: Kind, strength: number): Loc {
  return kind === "RZ" ? rotationLoc(strength) : dampingLoc(strength);
}

export interface Trajectory {
  /** branch label per location: "I" (identity) or a fault ("+" / "-" by sign). */
  picks: string[];
  /** product of the chosen branch signs, +1 or -1. */
  sign: number;
  /** observable value <O> in {-1, +1} on the final state (synthetic here). */
  obs: number;
}

export interface EstimateRun {
  trajectories: Trajectory[];
  /** Gamma = gamma^A, the magnitude every trajectory weight carries. */
  gamma: number;
  /** running estimate mean(sign * Gamma * obs). */
  estimate: number;
  /** its standard error, Gamma * std(sign*obs) / sqrt(N). */
  stderr: number;
  /** the value the estimator is unbiased for (the synthetic truth). */
  truth: number;
}

// Draw `n` trajectories of the flat importance estimator (estimate_chunk): at each
// of `count` locations pick one branch ~ |w|/gamma, multiply the weight by
// sign(w)*gamma, then read <O>. Every weight has magnitude Gamma = gamma^count, so
// only the sign moves. The observable is synthetic (a Bernoulli whose mean is the
// `truth`), standing in for the tableau expectation the core evaluates -- enough to
// show the estimator is unbiased and that its noise floor scales with Gamma.
export function runEstimate(
  loc: Loc,
  count: number,
  n: number,
  truth: number,
  seed: number,
): EstimateRun {
  const rng = mulberry32(seed);
  const gamma = Math.pow(loc.gamma, count);
  const trajectories: Trajectory[] = [];
  const pPlus = (truth + 1) / 2; // P(<O> = +1) so that E[<O>] = truth
  let sum = 0;
  let sumSq = 0;

  for (let i = 0; i < n; i += 1) {
    const picks: string[] = [];
    let sign = 1;

    for (let j = 0; j < count; j += 1) {
      if (rng() >= loc.phi) {
        picks.push("I");
        continue;
      }

      // faulted: this branch may carry a negative sign.
      if (rng() < loc.pNeg) {
        sign = -sign;
        picks.push("-");
      } else {
        picks.push("+");
      }
    }

    const obs = rng() < pPlus ? 1 : -1;
    const val = sign * obs; // the weight magnitude Gamma factors out of the sum

    trajectories.push({
      picks,
      sign,
      obs,
    });

    sum += val;
    sumSq += val * val;
  }

  const mean = sum / n;
  const variance = Math.max(0, sumSq / n - mean * mean);

  return {
    trajectories,
    gamma,
    estimate: gamma * mean,
    stderr: (gamma * Math.sqrt(variance)) / Math.sqrt(n),
    truth,
  };
}
