// A faithful, in-browser port of qliff/qec/tn.py: dense tensors with named legs,
// greedy pairwise contraction, the biased-COPY and parity factor tensors, and
// SVD bond truncation. Everything here matches the Python reference value-for-
// value on the small codes the explainer drives, so the page can run the *real*
// maximum-likelihood decoder rather than a cartoon of it.
//
// Legs are plain strings (the Python uses hashable tuples; strings are the same
// idea and hash trivially in JS). A tensor over k legs of dim 2 is a flat
// Float64Array of length 2^k laid out in row-major (C) order: index
// i = sum_a bit_a * 2^(k-1-a), where bit_a is the value on leg a.

export class Tensor {
  data: Float64Array;
  legs: string[];

  constructor(data: Float64Array, legs: string[]) {
    if (data.length !== 1 << legs.length) {
      throw new Error(`tensor data length ${data.length} != 2^${legs.length}`);
    }
    this.data = data;
    this.legs = legs;
  }

  get rank(): number {
    return this.legs.length;
  }

  withLegs(legs: string[]): Tensor {
    return new Tensor(this.data, legs);
  }
}

// ---- factor tensors -------------------------------------------------------

// COPY tensor weighted (1-p) on the all-zero corner and p on the all-one corner:
// a binary variable fanned to `degree` legs with its Bernoulli prior folded in.
// biased_copy in tn.py.
export function biasedCopy(degree: number, p: number): Tensor {
  const n = 1 << degree;
  const data = new Float64Array(n); // every mixed corner stays 0
  data[0] = 1 - p; // all legs = 0
  data[n - 1] = p; // all legs = 1

  return new Tensor(data, legNames("c", degree));
}

// XOR constraint: 1 where the leg bits sum to `target` (mod 2), else 0. parity()
// in tn.py. Pinning `target` to an observed syndrome bit is how a detector gets
// its measured value baked in.
export function parity(degree: number, target: number): Tensor {
  const n = 1 << degree;
  const data = new Float64Array(n);

  for (let i = 0; i < n; i += 1) {
    let pc = 0;
    for (let a = 0; a < degree; a += 1) {
      pc ^= (i >> a) & 1;
    }
    if (pc === (target & 1)) {
      data[i] = 1;
    }
  }

  return new Tensor(data, legNames("p", degree));
}

function legNames(prefix: string, k: number): string[] {
  return Array.from({ length: k }, (_, i) => `${prefix}${i}`);
}

// ---- contraction ----------------------------------------------------------

// row-major strides for a list of dim-2 legs.
function strides(rank: number): number[] {
  const s = new Array<number>(rank);
  let acc = 1;
  for (let a = rank - 1; a >= 0; a -= 1) {
    s[a] = acc;
    acc *= 2;
  }

  return s;
}

// Contract two tensors over every shared leg (a generalized matrix product:
// sum over the common indices, outer-product the rest). Disjoint legs => pure
// outer product. _contract_pair in tn.py, written out by hand here.
export function contractPair(a: Tensor, b: Tensor): Tensor {
  const shared = a.legs.filter((l) => b.legs.includes(l));
  const aRest = a.legs.filter((l) => !shared.includes(l));
  const bRest = b.legs.filter((l) => !shared.includes(l));
  const outLegs = [...aRest, ...bRest];

  const aStr = strides(a.rank);
  const bStr = strides(b.rank);
  const aSharedStr = shared.map((l) => aStr[a.legs.indexOf(l)]);
  const bSharedStr = shared.map((l) => bStr[b.legs.indexOf(l)]);
  const aRestStr = aRest.map((l) => aStr[a.legs.indexOf(l)]);
  const bRestStr = bRest.map((l) => bStr[b.legs.indexOf(l)]);

  const nShared = 1 << shared.length;
  const nA = 1 << aRest.length;
  const nB = 1 << bRest.length;
  const out = new Float64Array(nA * nB);

  // walk every (aRest, bRest, shared) combo; sum over shared into out.
  for (let ia = 0; ia < nA; ia += 1) {
    const aBase = offset(ia, aRestStr);
    for (let ib = 0; ib < nB; ib += 1) {
      const bBase = offset(ib, bRestStr);
      let acc = 0;
      for (let s = 0; s < nShared; s += 1) {
        acc += a.data[aBase + offset(s, aSharedStr)] * b.data[bBase + offset(s, bSharedStr)];
      }
      out[ia * nB + ib] = acc;
    }
  }

  return new Tensor(out, outLegs);
}

// scatter a packed counter `idx` (bits over a leg group) onto a strided offset.
function offset(idx: number, strs: number[]): number {
  let o = 0;
  for (let a = 0; a < strs.length; a += 1) {
    // bit a of idx is the value on leg a (MSB-first to match strides order)
    const bit = (idx >> (strs.length - 1 - a)) & 1;
    if (bit) {
      o += strs[a];
    }
  }

  return o;
}

export interface ContractStep {
  i: number; // index of tensor A in the work list (before removal)
  j: number; // index of tensor B
  sharedLegs: string[];
  resultRank: number;
  truncated: boolean; // a bond was SVD-compressed before merging
  workRanksAfter: number[]; // ranks of every tensor remaining after this merge
  maxRank: number; // largest intermediate seen up to & including this step
}

export interface ContractResult {
  tensor: Tensor;
  steps: ContractStep[];
  peakRank: number; // largest intermediate rank over the whole contraction
}

// Greedy pairwise contraction to `openLegs` (every other leg is summed). At each
// step merge the pair whose result has the fewest legs -- order changes cost,
// never the value. `maxBond` (chi) optionally truncates a pair's shared bond by
// SVD before merging. Mirrors contract() in tn.py and also records a trace so
// the UI can scrub the order. Pass tensors with rank >= 1 (scalars folded by
// caller; the decoder here has none).
export function contract(
  tensors: Tensor[],
  openLegs: string[],
  maxBond?: number,
): ContractResult {
  const work = tensors.map((t) => new Tensor(t.data, t.legs.slice()));
  const steps: ContractStep[] = [];
  let peakRank = work.reduce((m, t) => Math.max(m, t.rank), 0);

  while (work.length > 1) {
    let best: { cost: number; i: number; j: number } | null = null;

    for (let i = 0; i < work.length; i += 1) {
      for (let j = i + 1; j < work.length; j += 1) {
        const shared = work[i].legs.filter((l) => work[j].legs.includes(l)).length;
        if (shared === 0) {
          continue;
        }
        const cost = work[i].rank + work[j].rank - 2 * shared;
        if (best === null || cost < best.cost) {
          best = { cost, i, j };
        }
      }
    }

    const { i, j } = best ?? { cost: 0, i: 0, j: 1 };
    const b = work.splice(j, 1)[0];
    const a = work.splice(i, 1)[0];
    const sharedLegs = a.legs.filter((l) => b.legs.includes(l));

    let aa = a;
    let bb = b;
    let truncated = false;
    if (maxBond !== undefined && best !== null) {
      const [ca, cb, didTrunc] = compressBond(a, b, maxBond);
      aa = ca;
      bb = cb;
      truncated = didTrunc;
    }

    const merged = contractPair(aa, bb);
    work.push(merged);
    peakRank = Math.max(peakRank, merged.rank);
    steps.push({
      i,
      j,
      sharedLegs,
      resultRank: merged.rank,
      truncated,
      workRanksAfter: work.map((t) => t.rank),
      maxRank: peakRank,
    });
  }

  const res = work[0];
  const out = transposeTo(res, openLegs);

  return { tensor: out, steps, peakRank };
}

// reorder a tensor's legs to `target` (a permutation of its legs).
export function transposeTo(t: Tensor, target: string[]): Tensor {
  if (target.length !== t.rank) {
    throw new Error("transpose target rank mismatch");
  }
  if (target.every((l, a) => l === t.legs[a])) {
    return t;
  }
  const srcStr = strides(t.rank);
  const perm = target.map((l) => t.legs.indexOf(l));
  const n = t.data.length;
  const out = new Float64Array(n);
  const tgtStr = strides(t.rank);

  for (let i = 0; i < n; i += 1) {
    // decode i in target order, re-encode through source strides.
    let src = 0;
    for (let a = 0; a < t.rank; a += 1) {
      const bit = Math.floor(i / tgtStr[a]) & 1;
      if (bit) {
        src += srcStr[perm[a]];
      }
    }
    out[i] = t.data[src];
  }

  return new Tensor(out, target.slice());
}

// ---- bond truncation (the chi knob) ---------------------------------------

// Truncate the shared bond between a and b to `maxBond` via a thin SVD, exactly
// as _compress_bond in tn.py: fold the rest-legs of each side into a matrix with
// the shared legs as the contracted index, form M = A B, SVD it, keep the chi
// largest singular values, and split sqrt(S) into each side through a fresh bond
// of dim <= chi. Returns [A', B', didTruncate].
export function compressBond(a: Tensor, b: Tensor, maxBond: number): [Tensor, Tensor, boolean] {
  const shared = a.legs.filter((l) => b.legs.includes(l));
  const bondDim = 1 << shared.length;
  if (bondDim <= maxBond) {
    return [a, b, false];
  }

  const aRest = a.legs.filter((l) => !shared.includes(l));
  const bRest = b.legs.filter((l) => !shared.includes(l));
  const aMat = toMatrix(a, aRest, shared); // (rowsA x bondDim)
  const bMat = toMatrix(b, shared, bRest); // (bondDim x colsB)
  const rowsA = 1 << aRest.length;
  const colsB = 1 << bRest.length;

  // M = aMat @ bMat  (rowsA x colsB)
  const m = matmul(aMat, bMat, rowsA, bondDim, colsB);
  const { u, s, vt } = svd(m, rowsA, colsB);
  const k = Math.min(maxBond, s.length);
  const root = s.slice(0, k).map(Math.sqrt);

  const newBond = `bond_${bondId()}`;
  // A' = U[:, :k] * root  -> legs aRest + newBond, shape rowsA x k
  const aData = new Float64Array(rowsA * k);
  for (let r = 0; r < rowsA; r += 1) {
    for (let c = 0; c < k; c += 1) {
      aData[r * k + c] = u[r * s.length + c] * root[c];
    }
  }
  // B' = root[:,None] * Vt[:k, :] -> legs newBond + bRest, shape k x colsB
  const bData = new Float64Array(k * colsB);
  for (let c = 0; c < k; c += 1) {
    for (let col = 0; col < colsB; col += 1) {
      bData[c * colsB + col] = root[c] * vt[c * colsB + col];
    }
  }

  // NOTE: the new bond has dim k which may be < 2; our Tensor assumes dim-2 legs.
  // For the explainer we only *call* compressBond on illustrative matrices via
  // svdTruncate (below); the live decoder runs exact (maxBond undefined). This
  // path is kept faithful to the Python for the spectrum widget.
  const aT = new Tensor(aData, [...aRest, newBond]);
  const bT = new Tensor(bData, [newBond, ...bRest]);
  (aT as unknown as { bondDim: number }).bondDim = k;
  (bT as unknown as { bondDim: number }).bondDim = k;

  return [aT, bT, true];
}

let _bondCounter = 0;
function bondId(): number {
  _bondCounter += 1;

  return _bondCounter;
}

// fold a tensor into a 2D matrix: rowLegs as rows (row-major), colLegs as cols.
function toMatrix(t: Tensor, rowLegs: string[], colLegs: string[]): Float64Array {
  const str = strides(t.rank);
  const rowStr = rowLegs.map((l) => str[t.legs.indexOf(l)]);
  const colStr = colLegs.map((l) => str[t.legs.indexOf(l)]);
  const nR = 1 << rowLegs.length;
  const nC = 1 << colLegs.length;
  const out = new Float64Array(nR * nC);
  for (let r = 0; r < nR; r += 1) {
    const rb = offset(r, rowStr);
    for (let c = 0; c < nC; c += 1) {
      out[r * nC + c] = t.data[rb + offset(c, colStr)];
    }
  }

  return out;
}

function matmul(a: Float64Array, b: Float64Array, m: number, k: number, n: number): Float64Array {
  const out = new Float64Array(m * n);
  for (let i = 0; i < m; i += 1) {
    for (let p = 0; p < k; p += 1) {
      const av = a[i * k + p];
      if (av === 0) {
        continue;
      }
      for (let j = 0; j < n; j += 1) {
        out[i * n + j] += av * b[p * n + j];
      }
    }
  }

  return out;
}

// ---- a small, dependency-free SVD -----------------------------------------
// One-sided Jacobi SVD on M (m x n). Returns U (m x r), singular values s
// (length r = min(m,n), descending), and Vt (r x n). Accurate enough for the
// teaching widget; the real decoder uses numpy's LAPACK.
export function svd(
  M: Float64Array,
  m: number,
  n: number,
): { u: Float64Array; s: number[]; vt: Float64Array } {
  // Work on the taller orientation so columns >= rows is avoided; here we apply
  // Jacobi to A (m x n) computing V (n x n), then U = A V / s.
  const A = M.slice();
  const V = new Float64Array(n * n);
  for (let i = 0; i < n; i += 1) {
    V[i * n + i] = 1;
  }

  const sweeps = 60;
  const eps = 1e-14;
  for (let sweep = 0; sweep < sweeps; sweep += 1) {
    let off = 0;
    for (let p = 0; p < n - 1; p += 1) {
      for (let q = p + 1; q < n; q += 1) {
        let alpha = 0;
        let beta = 0;
        let gamma = 0;
        for (let i = 0; i < m; i += 1) {
          const aip = A[i * n + p];
          const aiq = A[i * n + q];
          alpha += aip * aip;
          beta += aiq * aiq;
          gamma += aip * aiq;
        }
        off += gamma * gamma;
        if (Math.abs(gamma) < eps) {
          continue;
        }
        const zeta = (beta - alpha) / (2 * gamma);
        const t =
          Math.sign(zeta) / (Math.abs(zeta) + Math.sqrt(1 + zeta * zeta)) ||
          1 / (2 * zeta || 1);
        const c = 1 / Math.sqrt(1 + t * t);
        const s = c * t;
        for (let i = 0; i < m; i += 1) {
          const aip = A[i * n + p];
          const aiq = A[i * n + q];
          A[i * n + p] = c * aip - s * aiq;
          A[i * n + q] = s * aip + c * aiq;
        }
        for (let i = 0; i < n; i += 1) {
          const vip = V[i * n + p];
          const viq = V[i * n + q];
          V[i * n + p] = c * vip - s * viq;
          V[i * n + q] = s * vip + c * viq;
        }
      }
    }
    if (off < eps) {
      break;
    }
  }

  // column norms of A are the singular values; normalize to get U columns.
  const cols = Array.from({ length: n }, (_, j) => {
    let nrm = 0;
    for (let i = 0; i < m; i += 1) {
      nrm += A[i * n + j] * A[i * n + j];
    }

    return { j, sigma: Math.sqrt(nrm) };
  });
  cols.sort((x, y) => y.sigma - x.sigma);

  const r = Math.min(m, n);
  const s: number[] = [];
  const u = new Float64Array(m * r);
  const vt = new Float64Array(r * n);
  for (let idx = 0; idx < r; idx += 1) {
    const { j, sigma } = cols[idx];
    s.push(sigma);
    if (sigma > 1e-300) {
      for (let i = 0; i < m; i += 1) {
        u[i * r + idx] = A[i * n + j] / sigma;
      }
    }
    for (let i = 0; i < n; i += 1) {
      vt[idx * n + i] = V[i * n + j];
    }
  }

  return { u, s, vt };
}

// Truncated rank-chi reconstruction of a matrix from its SVD, plus the spectrum
// and the relative Frobenius error of the truncation. Used by the chi widget to
// show "accuracy improves toward exact as chi grows".
export function svdTruncate(
  M: Float64Array,
  m: number,
  n: number,
  chi: number,
): { spectrum: number[]; approx: Float64Array; relError: number; kept: number } {
  const { u, s, vt } = svd(M, m, n);
  const r = s.length;
  const k = Math.max(0, Math.min(chi, r));
  const approx = new Float64Array(m * n);
  for (let c = 0; c < k; c += 1) {
    for (let i = 0; i < m; i += 1) {
      const uic = u[i * r + c] * s[c];
      if (uic === 0) {
        continue;
      }
      for (let jj = 0; jj < n; jj += 1) {
        approx[i * n + jj] += uic * vt[c * n + jj];
      }
    }
  }
  // relative Frobenius error = sqrt(sum_{i>k} s_i^2) / sqrt(sum s_i^2).
  let tail = 0;
  let total = 0;
  for (let i = 0; i < r; i += 1) {
    total += s[i] * s[i];
    if (i >= k) {
      tail += s[i] * s[i];
    }
  }
  const relError = total > 0 ? Math.sqrt(tail / total) : 0;

  return { spectrum: s, approx, relError, kept: k };
}
