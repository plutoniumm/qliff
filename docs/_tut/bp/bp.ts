// Genuine log-domain sum-product belief propagation + ordered-statistics
// decoding, run entirely in the browser on a small parity-check matrix H.
//
// This mirrors what qliff's BpOsdDecoder (qliff/qec/decoder.py) hands to the
// `ldpc` library: it decodes the DEM check matrix H of shape
// (detectors x mechanisms). Variable nodes are error mechanisms (possible
// faults); check nodes are detectors. An edge connects mechanism m to detector
// d iff H[d, m] = 1. Each variable carries a prior log-likelihood ratio
//     LLR = log((1 - p) / p)
// (large positive => the mechanism is probably NOT firing). bp_method is
// "product_sum" (= sum-product). We expose the full per-iteration trace so the
// Svelte layer can scrub through convergence as a pure function of the inputs.

// ----------------------------------------------------------------------------
// Types
// ----------------------------------------------------------------------------

export interface Code {
  // H[d][m] in {0,1}: detector d is flipped by mechanism m.
  H: number[][];
  nChecks: number; // detectors
  nVars: number; // mechanisms
  // priors[m] = channel probability p_m of mechanism m firing.
  priors: number[];
  // For each variable, the checks it touches (column support of H).
  varNeighbours: number[][];
  // For each check, the variables it touches (row support of H).
  checkNeighbours: number[][];
}

// One BP iteration's worth of state, enough to draw the graph at that step.
export interface BpFrame {
  iter: number;
  // varToCheck[m][c] = message mechanism m sends to detector c (log domain).
  varToCheck: Map<string, number>;
  // checkToVar[c][m] = message detector c sends to mechanism m (log domain).
  checkToVar: Map<string, number>;
  // posterior[m] = running posterior LLR for mechanism m.
  posterior: number[];
  // hard[m] = current hard decision (1 = "this mechanism fired").
  hard: number[];
  // residual syndrome of the current hard decision vs. the target syndrome.
  residual: number[];
  // true once the hard decision reproduces the syndrome (BP "converged").
  satisfied: boolean;
}

export interface BpResult {
  frames: BpFrame[]; // index 0 = priors only, then one per iteration
  converged: boolean; // did the hard decision ever satisfy the syndrome?
  convergedAt: number; // iteration index of first satisfaction, or -1
  finalPosterior: number[];
  finalHard: number[];
}

export interface OsdResult {
  // Columns sorted most-reliable-first (by |posterior LLR|).
  order: number[];
  // The full-rank pivot set OSD solves exactly (a subset of `order`).
  pivots: number[];
  // The order-0 solution: solve pivots, free vars = 0.
  osd0: number[];
  // The final OSD solution after the small combination search.
  solution: number[];
  // weight (number of firing mechanisms) of osd0 vs. final solution.
  osd0Weight: number;
  solutionWeight: number;
  // residual syndrome of the final solution (should be all zero).
  residual: number[];
}

// ----------------------------------------------------------------------------
// Building a Code from a dense H
// ----------------------------------------------------------------------------

export function makeCode(H: number[][], priors: number[]): Code {
  const nChecks = H.length;
  const nVars = H[0]?.length ?? 0;
  const varNeighbours: number[][] = Array.from({ length: nVars }, () => []);
  const checkNeighbours: number[][] = Array.from({ length: nChecks }, () => []);

  for (let c = 0; c < nChecks; c += 1) {
    for (let m = 0; m < nVars; m += 1) {
      if (H[c][m]) {
        checkNeighbours[c].push(m);
        varNeighbours[m].push(c);
      }
    }
  }

  return { H, nChecks, nVars, priors, varNeighbours, checkNeighbours };
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

// Prior log-likelihood ratio of a mechanism with firing probability p.
// LLR = log((1 - p) / p): positive => probably not firing.
export function llrFromP(p: number): number {
  const clamped = Math.min(Math.max(p, 1e-9), 1 - 1e-9);

  return Math.log((1 - clamped) / clamped);
}

// Inverse: posterior probability that a mechanism fired, from its LLR.
export function pFromLlr(llr: number): number {
  return 1 / (1 + Math.exp(llr));
}

function key(a: number, b: number): string {
  return `${a},${b}`;
}

// Syndrome (mod-2 detector pattern) produced by an error/mechanism vector.
export function syndromeOf(code: Code, error: number[]): number[] {
  const s = new Array<number>(code.nChecks).fill(0);
  for (let c = 0; c < code.nChecks; c += 1) {
    let acc = 0;
    for (const m of code.checkNeighbours[c]) {
      acc ^= error[m] & 1;
    }
    s[c] = acc;
  }

  return s;
}

function hammingWeight(v: number[]): number {
  let w = 0;
  for (const x of v) {
    w += x & 1;
  }

  return w;
}

// ----------------------------------------------------------------------------
// Sum-product BP, log domain
// ----------------------------------------------------------------------------

// tanh(x/2) clamped so atanh stays finite. The product over neighbours of
// tanh(m_in/2) can hit +-1; we keep it strictly inside the open interval.
function tanhHalf(x: number): number {
  const t = Math.tanh(x / 2);

  return Math.min(Math.max(t, -1 + 1e-12), 1 - 1e-12);
}

// Run sum-product BP for `maxIter` iterations on the given syndrome. The check
// node update uses the exact tanh product rule:
//     tanh(m_out / 2) = product over other neighbours of tanh(m_in / 2),
// with a sign flip for every lit detector (syndrome bit = 1), so the messages
// push the beliefs toward an error pattern that reproduces the syndrome. Stops
// early once the hard decision satisfies all checks (but records every frame up
// to the first satisfaction so the UI can replay it).
export function runBp(code: Code, syndrome: number[], maxIter: number): BpResult {
  const { nChecks, nVars, varNeighbours, checkNeighbours } = code;
  const prior = code.priors.map(llrFromP);

  // Messages, keyed by (var,check) / (check,var).
  const varToCheck = new Map<string, number>();
  const checkToVar = new Map<string, number>();

  // Init: variable->check messages start at the prior LLR; check->var at 0.
  for (let m = 0; m < nVars; m += 1) {
    for (const c of varNeighbours[m]) {
      varToCheck.set(key(m, c), prior[m]);
      checkToVar.set(key(c, m), 0);
    }
  }

  const frames: BpFrame[] = [];

  // Frame 0: priors only, no messages have flowed yet.
  const post0 = prior.slice();
  const hard0 = post0.map((l) => (l < 0 ? 1 : 0));
  const res0 = xorSyndrome(syndromeOf(code, hard0), syndrome);
  frames.push({
    iter: 0,
    varToCheck: new Map(varToCheck),
    checkToVar: new Map(checkToVar),
    posterior: post0,
    hard: hard0,
    residual: res0,
    satisfied: hammingWeight(res0) === 0,
  });

  let converged = frames[0].satisfied;
  let convergedAt = converged ? 0 : -1;

  for (let it = 1; it <= maxIter; it += 1) {
    // --- check -> variable update (tanh rule, excluding the target var) ---
    for (let c = 0; c < nChecks; c += 1) {
      const neigh = checkNeighbours[c];
      const sign = syndrome[c] ? -1 : 1; // lit detector flips the product
      for (const m of neigh) {
        let prod = sign;
        for (const m2 of neigh) {
          if (m2 !== m) {
            prod *= tanhHalf(varToCheck.get(key(m2, c)) as number);
          }
        }
        const clamped = Math.min(Math.max(prod, -1 + 1e-12), 1 - 1e-12);
        checkToVar.set(key(c, m), 2 * Math.atanh(clamped));
      }
    }

    // --- variable -> check update (prior + sum of OTHER checks) ---
    for (let m = 0; m < nVars; m += 1) {
      const neigh = varNeighbours[m];
      let total = prior[m];
      for (const c of neigh) {
        total += checkToVar.get(key(c, m)) as number;
      }
      for (const c of neigh) {
        varToCheck.set(key(m, c), total - (checkToVar.get(key(c, m)) as number));
      }
    }

    // --- posterior + hard decision ---
    const posterior = new Array<number>(nVars);
    const hard = new Array<number>(nVars);
    for (let m = 0; m < nVars; m += 1) {
      let total = prior[m];
      for (const c of varNeighbours[m]) {
        total += checkToVar.get(key(c, m)) as number;
      }
      posterior[m] = total;
      hard[m] = total < 0 ? 1 : 0; // posterior LLR < 0 => mechanism fired
    }

    const residual = xorSyndrome(syndromeOf(code, hard), syndrome);
    const satisfied = hammingWeight(residual) === 0;

    frames.push({
      iter: it,
      varToCheck: new Map(varToCheck),
      checkToVar: new Map(checkToVar),
      posterior,
      hard,
      residual,
      satisfied,
    });

    if (satisfied && convergedAt === -1) {
      converged = true;
      convergedAt = it;
    }
  }

  const last = frames[frames.length - 1];

  return {
    frames,
    converged,
    convergedAt,
    finalPosterior: last.posterior,
    finalHard: last.hard,
  };
}

function xorSyndrome(a: number[], b: number[]): number[] {
  return a.map((x, i) => (x ^ b[i]) & 1);
}

// ----------------------------------------------------------------------------
// Ordered-statistics decoding (OSD)
// ----------------------------------------------------------------------------

// "BP proposes, OSD disposes." Take BP's soft output, order columns of H by
// reliability (|posterior LLR|, most reliable first), Gauss-eliminate to pull
// out a most-reliable full-rank set of pivot columns, solve that subsystem
// exactly so the syndrome is matched, then (order > 0) search small flips of
// the least-reliable free columns for a lower-weight consistent solution.
// osdOrder mirrors qliff's osd_order=7 (we cap the search for the tiny demo).
export function runOsd(
  code: Code,
  syndrome: number[],
  posterior: number[],
  osdOrder = 7,
): OsdResult {
  const { nChecks, nVars } = code;

  // Reliability = |posterior LLR|; sort columns most-reliable first.
  const order = Array.from({ length: nVars }, (_, m) => m).sort(
    (a, b) => Math.abs(posterior[b]) - Math.abs(posterior[a]),
  );

  // Build an augmented matrix [H | s] with columns visited in reliability order
  // and run GF(2) Gaussian elimination to find independent pivot columns.
  const rows: number[][] = [];
  for (let r = 0; r < nChecks; r += 1) {
    const row = new Array<number>(nVars + 1).fill(0);
    for (let m = 0; m < nVars; m += 1) {
      row[m] = code.H[r][m] & 1;
    }
    row[nVars] = syndrome[r] & 1;
    rows.push(row);
  }

  const pivots: number[] = [];
  const pivotRowOf: number[] = []; // parallel to pivots: which row owns it
  let activeRow = 0;
  for (const col of order) {
    if (activeRow >= nChecks) {
      break;
    }
    // find a row at or below activeRow with a 1 in this column
    let sel = -1;
    for (let r = activeRow; r < nChecks; r += 1) {
      if (rows[r][col]) {
        sel = r;
        break;
      }
    }
    if (sel === -1) {
      continue; // column dependent on already-chosen pivots; it's a free var
    }
    // swap into place
    const tmp = rows[activeRow];
    rows[activeRow] = rows[sel];
    rows[sel] = tmp;
    // eliminate this column from every other row
    for (let r = 0; r < nChecks; r += 1) {
      if (r !== activeRow && rows[r][col]) {
        for (let k = 0; k <= nVars; k += 1) {
          rows[r][k] ^= rows[activeRow][k];
        }
      }
    }
    pivots.push(col);
    pivotRowOf.push(activeRow);
    activeRow += 1;
  }

  const freeVars = order.filter((m) => !pivots.includes(m));

  // Solve the reduced system for a given assignment of the free variables.
  // With H in reduced row-echelon form over the pivots, each pivot value is the
  // RHS minus the free-column contributions in its row.
  const solveFor = (freeAssign: Map<number, number>): number[] => {
    const x = new Array<number>(nVars).fill(0);
    for (const [v, val] of freeAssign) {
      x[v] = val;
    }
    for (let i = 0; i < pivots.length; i += 1) {
      const r = pivotRowOf[i];
      let val = rows[r][nVars];
      for (const f of freeVars) {
        if (rows[r][f]) {
          val ^= x[f];
        }
      }
      x[pivots[i]] = val & 1;
    }

    return x;
  };

  // Order 0: all free vars = 0.
  const osd0 = solveFor(new Map());
  const osd0Weight = hammingWeight(osd0);

  // Higher orders: flip up to `osdOrder` of the LEAST-reliable free columns and
  // keep the lowest-weight consistent solution found (this is the spirit of
  // ldpc's "combination sweep" / osd_cs). Free vars are already in reliability
  // order, so the least reliable sit at the tail.
  let best = osd0;
  let bestWeight = osd0Weight;
  const searchFree = freeVars.slice(-Math.min(freeVars.length, 12)); // cap demo cost
  const k = Math.min(osdOrder, searchFree.length);

  // Enumerate non-empty subsets of size 1..k of searchFree.
  const combos = subsetsUpTo(searchFree, k);
  for (const subset of combos) {
    const assign = new Map<number, number>();
    for (const v of subset) {
      assign.set(v, 1);
    }
    const cand = solveFor(assign);
    const w = hammingWeight(cand);
    if (w < bestWeight) {
      best = cand;
      bestWeight = w;
    }
  }

  const residual = xorSyndrome(syndromeOf(code, best), syndrome);

  return {
    order,
    pivots,
    osd0,
    solution: best,
    osd0Weight,
    solutionWeight: bestWeight,
    residual,
  };
}

// All non-empty subsets of `items` with size in [1, k]. Sizes are small here
// (k <= 7 over <= 12 items) so this stays cheap.
function subsetsUpTo(items: number[], k: number): number[][] {
  const out: number[][] = [];
  const n = items.length;

  const rec = (start: number, chosen: number[]): void => {
    if (chosen.length > 0) {
      out.push(chosen.slice());
    }
    if (chosen.length === k) {
      return;
    }
    for (let i = start; i < n; i += 1) {
      chosen.push(items[i]);
      rec(i + 1, chosen);
      chosen.pop();
    }
  };

  rec(0, []);

  return out;
}

// ----------------------------------------------------------------------------
// Example codes used by the explainer
// ----------------------------------------------------------------------------

// A length-n repetition code: checks compare adjacent bits. H is
// (n-1) x n with H[c] touching bits c and c+1. Each bit is one mechanism; each
// check is one detector. This is graphlike (<= 2 vars per check) and is the
// gentle first example: BP behaves like a tidy chain of gossiping neighbours.
export function repetitionCode(n: number, p: number): Code {
  const H: number[][] = [];
  for (let c = 0; c < n - 1; c += 1) {
    const row = new Array<number>(n).fill(0);
    row[c] = 1;
    row[c + 1] = 1;
    H.push(row);
  }

  return makeCode(H, new Array<number>(n).fill(p));
}

// A small DENSE / degenerate code engineered so BP gets stuck. The first
// detector touches all four mechanisms; detectors 1 and 2 each pair two of
// them. With a uniform prior and the syndrome [1,1,0] (= "detector 0 and
// detector 1 are lit"), mechanism 0 alone is the weight-1 answer -- but the
// symmetric short cycle makes the sum-product beliefs OSCILLATE: the hard
// decision flips between {0,1} and {} on every iteration and never commits.
// This is the classic degeneracy / trapping-set failure that motivates OSD,
// and the kind of non-graphlike structure where qliff reaches for BP+OSD over
// MWPM.
//
// H is 3 detectors x 4 mechanisms.
export function degenerateCode(p: number): Code {
  const H = [
    [1, 1, 1, 1],
    [1, 1, 0, 0],
    [0, 0, 1, 1],
  ];

  return makeCode(H, new Array<number>(4).fill(p));
}

// The syndrome that traps BP on `degenerateCode`: detector 0 and detector 1
// lit. Its lowest-weight explanation is mechanism 0 alone.
export const STUCK_SYNDROME = [1, 1, 0];
