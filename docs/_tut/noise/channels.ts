// The stabilizer-noise engine, in TypeScript, mirroring qliff/noise/channel.py
// and qliff/qec/sampler.py EXACTLY. Every weight, every sampling decision, and
// the detection-event definition on this page are the real thing the simulator
// would compute -- just small enough to watch by hand.
//
// A CHANNEL is a list of BRANCHES. Each branch is a signed weight attached to a
// list of Clifford ops (gate + qubit). The identity / no-fault branch is always
// first. For Pauli channels the weights are a genuine probability distribution
// (>= 0, sum to 1); for non-Pauli channels they are SIGNED quasiprobabilities
// whose magnitudes sum to gamma >= 1.

// ---------------------------------------------------------------------------
// Branches
// ---------------------------------------------------------------------------

// One Clifford gate applied to one qubit. `gate` is a short label ("X", "Z",
// "S", "S†", "H", "R"=reset); `qubit` is an index into the trajectory's qubit
// line. A branch's ops fire together if that branch is selected.
export interface Op {
  gate: string;
  qubit: number;
}

// (weight, ops). `pauli` is a compact human label for the menu/tables, e.g.
// "I", "X", "XZ" (a 2-qubit pair). The simulator itself only sees (weight, ops).
export interface Branch {
  weight: number;
  ops: Op[];
  pauli: string;
}

// ---------------------------------------------------------------------------
// Channel families -- branches(qubits) mirrors channel.py one-for-one.
// ---------------------------------------------------------------------------

export type ChannelKind =
  | "DEPOLARIZE1"
  | "DEPOLARIZE2"
  | "X_ERROR"
  | "Z_ERROR"
  | "PAULI_CHANNEL_1"
  | "RZ"
  | "RX"
  | "AMPLITUDE_DAMP";

export interface Channel {
  kind: ChannelKind;
  isPauli: boolean;
  // qubits this location acts on (1 for single-qubit channels, 2 for DEPOLARIZE2).
  qubits: number[];
  // (weight, ops) branches, identity first -- a pure function of the channel's
  // parameters and its target qubits.
  branches: () => Branch[];
}

const PAULI1 = ["I", "X", "Y", "Z"] as const;

// PauliChannel(px, py, pz): {I, X@px, Y@py, Z@pz}. twoq spreads px over the 15
// non-identity 2-qubit Pauli pairs at px/15 each (py, pz dead) -- the exact
// branches() of qliff's PauliChannel.
function pauliBranches(
  px: number,
  py: number,
  pz: number,
  twoq: boolean,
  qubits: number[],
): Branch[] {
  if (twoq) {
    const [a, b] = qubits;
    const each = px / 15;
    const out: Branch[] = [{ weight: 1 - px, ops: [], pauli: "II" }];
    for (const pa of PAULI1) {
      for (const pb of PAULI1) {
        if (pa === "I" && pb === "I") {
          continue;
        }
        const ops: Op[] = [];
        if (pa !== "I") {
          ops.push({ gate: pa, qubit: a });
        }
        if (pb !== "I") {
          ops.push({ gate: pb, qubit: b });
        }
        out.push({ weight: each, ops, pauli: pa + pb });
      }
    }

    return out;
  }

  const q = qubits[0];
  const keep = 1 - (px + py + pz);

  return [
    { weight: keep, ops: [], pauli: "I" },
    { weight: px, ops: [{ gate: "X", qubit: q }], pauli: "X" },
    { weight: py, ops: [{ gate: "Y", qubit: q }], pauli: "Y" },
    { weight: pz, ops: [{ gate: "Z", qubit: q }], pauli: "Z" },
  ];
}

// Rotation exp(-i theta P / 2) as a quasiprob mix of the Cliffords diagonal in
// Z: {I, Z, S, S†}, with bd = (1 - cos - sin)/4. RX = H RZ H wraps each branch
// in H either side (identical weights) -- mirrors channel.py's Rotation.
function rotationBranches(axis: "X" | "Z", theta: number, qubits: number[]): Branch[] {
  const q = qubits[0];
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  const bd = (1 - cos - sin) / 4;
  const cores: [number, string | null, string][] = [
    [bd + cos, null, "I"],
    [bd, "Z", "Z"],
    [bd + sin, "S", "S"],
    [bd, "S†", "S†"],
  ];
  const wrap = axis === "X";

  return cores.map(([weight, core, label]) => {
    const ops: Op[] = [];
    if (wrap) {
      ops.push({ gate: "H", qubit: q });
    }
    if (core !== null) {
      ops.push({ gate: core, qubit: q });
    }
    if (wrap) {
      ops.push({ gate: "H", qubit: q });
    }

    return { weight, ops, pauli: label };
  });
}

// AmplitudeDamping(p) exactly over {I, Z, R=reset}: q_I=[(1-p)+root]/2,
// q_Z=[(1-p)-root]/2 (< 0), q_R = p, root = sqrt(1-p).
function dampingBranches(p: number, qubits: number[]): Branch[] {
  const q = qubits[0];
  const root = Math.sqrt(Math.max(0, 1 - p));
  const qi = (1 - p + root) / 2;
  const qz = (1 - p - root) / 2;

  return [
    { weight: qi, ops: [], pauli: "I" },
    { weight: qz, ops: [{ gate: "Z", qubit: q }], pauli: "Z" },
    { weight: p, ops: [{ gate: "R", qubit: q }], pauli: "R" },
  ];
}

// Factories mirroring NOISE_FACTORIES. DEPOLARIZE1 -> px=py=pz=p/3; DEPOLARIZE2
// -> px=p over 15 pairs; X_ERROR/Z_ERROR -> single Pauli at p.
export function makeChannel(
  kind: ChannelKind,
  p: number,
  qubits: number[],
): Channel {
  switch (kind) {
    case "DEPOLARIZE1":
      return {
        kind,
        isPauli: true,
        qubits,
        branches: () => pauliBranches(p / 3, p / 3, p / 3, false, qubits),
      };
    case "DEPOLARIZE2":
      return {
        kind,
        isPauli: true,
        qubits,
        branches: () => pauliBranches(p, 0, 0, true, qubits),
      };
    case "X_ERROR":
      return {
        kind,
        isPauli: true,
        qubits,
        branches: () => pauliBranches(p, 0, 0, false, qubits),
      };
    case "Z_ERROR":
      return {
        kind,
        isPauli: true,
        qubits,
        branches: () => pauliBranches(0, 0, p, false, qubits),
      };
    case "RZ":
      return {
        kind,
        isPauli: false,
        qubits,
        branches: () => rotationBranches("Z", p, qubits),
      };
    case "RX":
      return {
        kind,
        isPauli: false,
        qubits,
        branches: () => rotationBranches("X", p, qubits),
      };
    case "AMPLITUDE_DAMP":
      return {
        kind,
        isPauli: false,
        qubits,
        branches: () => dampingBranches(p, qubits),
      };
    default:
      // PAULI_CHANNEL_1 isn't exposed via a single scalar; treat p as px.
      return {
        kind,
        isPauli: true,
        qubits,
        branches: () => pauliBranches(p, 0, 0, false, qubits),
      };
  }
}

// ---------------------------------------------------------------------------
// gamma / total weight
// ---------------------------------------------------------------------------

// Total signed weight Sum(w): exactly 1 for any honest trace-preserving channel.
export function totalWeight(branches: Branch[]): number {
  return branches.reduce((s, b) => s + b.weight, 0);
}

// Negativity gamma = Sum|w|: 1 iff a true probability mixture, > 1 is the price
// of non-Cliffordness. Drives the per-location sampling factor and the variance.
export function gamma(branches: Branch[]): number {
  return branches.reduce((s, b) => s + Math.abs(b.weight), 0);
}

// ---------------------------------------------------------------------------
// Channel.sample -- the exact rule from channel.py
// ---------------------------------------------------------------------------

export interface SampleResult {
  // index of the branch that fired.
  index: number;
  branch: Branch;
  // sign(weight) * gamma -- the per-location importance factor. 1 for Pauli.
  factor: number;
  // the actual uniform draw on [0, gamma) used (for the dice-roll visual).
  threshold: number;
  // the cumulative |w| boundaries we walked, for the visual.
  cumulative: number[];
}

// Draw one branch w.p. |weight|/gamma; return (sign(weight)*gamma, ops). `rng`
// is a [0,1) generator (mulberry32). gamma = Sum|w|; threshold = rng()*gamma;
// walk branches accumulating |w| and stop at the first that covers threshold.
export function sampleChannel(branches: Branch[], rng: () => number): SampleResult {
  const g = gamma(branches);
  const threshold = rng() * g;
  let acc = 0;
  const cumulative: number[] = [];
  for (let i = 0; i < branches.length; i += 1) {
    acc += Math.abs(branches[i].weight);
    cumulative.push(acc);
    if (threshold <= acc) {
      const w = branches[i].weight;
      const factor = (w >= 0 ? 1 : -1) * g;

      return { index: i, branch: branches[i], factor, threshold, cumulative };
    }
  }
  // floating-point fallback: last branch (matches channel.py).
  const last = branches.length - 1;
  const w = branches[last].weight;

  return {
    index: last,
    branch: branches[last],
    factor: (w >= 0 ? 1 : -1) * g,
    threshold,
    cumulative,
  };
}

// ---------------------------------------------------------------------------
// A tiny circuit + the DetectorSampler trajectory, faithfully.
// ---------------------------------------------------------------------------

// One scheduled instruction: either a deterministic Clifford gate, or a noise
// LOCATION (a channel to sample one branch from per shot).
export type Instruction =
  | { type: "gate"; gate: string; qubits: number[] }
  | { type: "noise"; channel: Channel; label: string };

// A measurement is folded into the record by name; for our teaching circuits we
// just read the relevant qubits' Z value at the end (see runTrajectory).
export interface Circuit {
  numQubits: number;
  instructions: Instruction[];
  // detectors as lists of measured-qubit indices whose parity is the syndrome
  // bit; observables likewise. For the rep-code demo a detector = a Z-check =
  // parity of two neighbouring data qubits.
  detectors: number[][];
  observables: number[][];
}

// Effect of one Clifford op on a Pauli FRAME. We track each qubit's error as a
// 2-bit (x, z) Pauli frame -- enough to get measurement parities right for the
// CSS/rep-code circuits this page uses, and it makes the trajectory's effect on
// detectors exact without a full tableau. Gates we support: X, Y, Z, H, S, S†,
// R(reset). For the teaching circuits only X/Z/H/reset actually move the frame
// in a way that changes Z-basis measurement parity; S/S† leave Z-parity fixed.
interface Frame {
  // per qubit: does the accumulated error flip this qubit's Z measurement?
  // (an X or Y error flips a Z measurement; Z/I do not).
  flip: boolean[];
}

function applyOp(frame: Frame, gate: string, q: number): void {
  switch (gate) {
    case "X":
    case "Y":
      // X and Y both anticommute with Z -> toggle the Z-measurement flip.
      frame.flip[q] = !frame.flip[q];
      break;
    case "Z":
    case "S":
    case "S†":
      // commute with Z measurement -> no parity change.
      break;
    case "H":
      // For the rep-code teaching circuit H is only used to read X-checks;
      // we keep its frame action trivial here (the demo circuits are Z-basis).
      break;
    case "R":
      // reset clears the error on this qubit.
      frame.flip[q] = false;
      break;
    default:
      break;
  }
}

export interface NoiseFire {
  // which instruction index fired,
  insIndex: number;
  label: string;
  sample: SampleResult;
}

export interface TrajectoryRun {
  // detection events (post-XOR-with-reference) and observable flips.
  detectionEvents: number[];
  observableFlips: number[];
  // the signed importance weight = product of per-location factors.
  weight: number;
  // one record per noise location that fired (in circuit order).
  fires: NoiseFire[];
  // the final per-qubit Z-flip frame, for visualization.
  finalFlip: boolean[];
}

// Replay the circuit once. If `noiseless`, every location takes its identity
// branch (no fault) -- this produces the reference frame. Otherwise sample one
// branch per location and accumulate the signed weight. This is exactly the
// DetectorSampler / WeightedDetectorSampler `_record` / `_trajectory` loop.
function replay(circuit: Circuit, rng: (() => number) | null): {
  flip: boolean[];
  weight: number;
  fires: NoiseFire[];
} {
  const frame: Frame = { flip: new Array(circuit.numQubits).fill(false) };
  let weight = 1;
  const fires: NoiseFire[] = [];

  circuit.instructions.forEach((ins, i) => {
    if (ins.type === "gate") {
      for (const q of ins.qubits) {
        applyOp(frame, ins.gate, q);
      }

      return;
    }
    // noise location
    const branches = ins.channel.branches();
    if (rng === null) {
      // noiseless reference: identity branch (index 0), no ops, factor 1.
      return;
    }
    const sample = sampleChannel(branches, rng);
    weight *= sample.factor;
    for (const op of sample.branch.ops) {
      applyOp(frame, op.gate, op.qubit);
    }
    fires.push({ insIndex: i, label: ins.label, sample });
  });

  return { flip: frame.flip, weight, fires };
}

// Parity of the Z-measurement flips over a set of qubit indices.
function parity(flip: boolean[], qubits: number[]): number {
  let bit = 0;
  for (const q of qubits) {
    bit ^= flip[q] ? 1 : 0;
  }

  return bit;
}

// Run one full trajectory and turn it into detection events via the XOR-with-
// reference rule. Because our reference frame is all-false (noiseless = no
// errors), the reference parity is 0 for every detector; we keep the XOR
// explicit so the definition is visible and stays correct if a circuit ever
// starts with a deterministic flip.
export function runTrajectory(circuit: Circuit, seed: number): TrajectoryRun {
  // reference: identity branch everywhere.
  const ref = replay(circuit, null);
  const detRef = circuit.detectors.map((d) => parity(ref.flip, d));
  const obsRef = circuit.observables.map((o) => parity(ref.flip, o));

  // noisy shot.
  const rng = mulberry(seed);
  const shot = replay(circuit, rng);

  const detectionEvents = circuit.detectors.map(
    (d, j) => parity(shot.flip, d) ^ detRef[j],
  );
  const observableFlips = circuit.observables.map(
    (o, j) => parity(shot.flip, o) ^ obsRef[j],
  );

  return {
    detectionEvents,
    observableFlips,
    weight: shot.weight,
    fires: shot.fires,
    finalFlip: shot.flip,
  };
}

// ---------------------------------------------------------------------------
// Local mulberry32 (re-exported through rng usage in components). Kept here so
// channels.ts is self-contained for the sampling math; components import from
// $lib/rng for sliders etc.
// ---------------------------------------------------------------------------

function mulberry(seed: number): () => number {
  let a = seed >>> 0;

  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;

    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
