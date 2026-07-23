// Memory-layout arithmetic for the ColTableau, in TypeScript, mirroring
// src/tableau.rs. The CHP tableau is 2n+1 Pauli rows over n qubits of bits; the
// whole page turns on WHERE those bits live in memory, so every count here is the
// same closed form the Rust core uses -- a reader can check the page against the
// source. Also holds the splitmix64 chunk-seed derivation (chunk_seed in
// tableau.rs) so the reproducible-chunking figure shows the ACTUAL per-chunk seeds.

// Rows of the tableau: n destabilizers + n stabilizers + 1 measurement scratch.
export function rows(n: number): number {
  return 2 * n + 1;
}

// Words per COLUMN plane (col-major, `rw` in tableau.rs): ceil(rows/64). A qubit's
// x/z/sign plane is this many contiguous u64 words, so a 1-qubit gate is a sweep
// over rw whole words per plane -- O(rows/64) word ops, the cache-friendly path.
export function colWords(n: number): number {
  return Math.ceil(rows(n) / 64);
}

// Words per row-major ROW (`w` in tableau.rs): ceil(n/64). Used when tiling the
// (rows x nq) matrix into 64x64 blocks for a transpose.
export function rowWords(n: number): number {
  return Math.ceil(n / 64);
}

// A row-major 1-qubit gate touches ONE (strided) scalar in every row: 2n+1 memory
// touches, stride = w words apart. O(rows), and the stride is what fell out of
// cache at large n -- the cliff (Wall 1) the column layout removed.
export function rowTouches(n: number): number {
  return rows(n);
}

// 64x64 bit-blocks a full to_col / to_row transpose walks: ceil(rows/64) *
// ceil(nq/64). transpose64 handles each block in 6 mask/shift passes, so the whole
// transpose is blocks * 6 word-parallel passes, amortized one per measurement round.
export function transposeBlocks(n: number): number {
  return colWords(n) * rowWords(n);
}

// How many strided row-touches one col-major plane-sweep replaces: rows / rw ~ 64.
export function reduction(n: number): number {
  return rowTouches(n) / colWords(n);
}

// --------------------------------------------------------------------------
// Measured col-major gate throughput
// --------------------------------------------------------------------------

// Measured with qliff's own ColTableau.run on the committed build (single core,
// Apple silicon, 2026-07), H sweeps on a fresh tableau, marshalling excluded.
// Absolute ns are machine-relative; the SHAPE is the headline: ns/plane-word is
// FLAT (~13-14 ns) from n=4096 up, while the plane grows 16x -- no cache cliff.
export interface Meas {
  n: number;
  rw: number; // words per plane at this n
  nsGate: number; // nanoseconds for one 1-qubit gate (touches 3*rw words)
  nsWord: number; // nsGate / (3*rw): time per plane-word
}

export const MEASURED: Meas[] = [
  {
    n: 256,
    rw: 9,
    nsGate: 1126,
    nsWord: 41.7,
  },
  {
    n: 1024,
    rw: 33,
    nsGate: 1711,
    nsWord: 17.3,
  },
  {
    n: 4096,
    rw: 129,
    nsGate: 4830,
    nsWord: 12.5,
  },
  {
    n: 16384,
    rw: 513,
    nsGate: 20991,
    nsWord: 13.6,
  },
  {
    n: 65536,
    rw: 2049,
    nsGate: 85906,
    nsWord: 14.0,
  },
];

// --------------------------------------------------------------------------
// splitmix64 chunk seeding (chunk_seed / splitmix_finalize in tableau.rs)
// --------------------------------------------------------------------------

const M64 = (1n << 64n) - 1n;
const GOLDEN = 0x9e37_79b9_7f4a_7c15n;

// splitmix64 finalizer: the same avalanche the Rng advance and chunk_seed use.
function splitmixFinalize(z0: bigint): bigint {
  let z = z0 & M64;
  z = ((z ^ (z >> 30n)) * 0xbf58_476d_1ce4_e5b9n) & M64;
  z = ((z ^ (z >> 27n)) * 0x94d0_49bb_1331_11ebn) & M64;

  return (z ^ (z >> 31n)) & M64;
}

// Per-chunk seed: chunk_seed(base, c) = finalize(base ^ (c * golden)). The seed is
// pinned to the CHUNK INDEX, never to the core that happens to run it, which is why
// the sampler is byte-identical regardless of how many cores rayon uses.
export function chunkSeed(base: bigint, chunk: bigint): bigint {
  return splitmixFinalize((base & M64) ^ ((chunk * GOLDEN) & M64));
}

// Last 6 hex digits of a u64, for a compact seed readout.
export function shortHex(v: bigint): string {
  return (v & M64).toString(16).padStart(16, "0").slice(-6);
}

// The frame sampler's fixed shot-chunk (FRAME_CHUNK in tableau.rs).
export const FRAME_CHUNK = 1024;

export interface Chunk {
  index: number;
  shots: number; // shots in this chunk (last one may be short)
  seed: bigint; // derived from the chunk INDEX -- invariant to core count
  core: number; // which worker runs it under a given schedule (varies)
}

// Split `shots` into FRAME_CHUNK blocks, derive each block's seed from its index,
// and assign blocks to `cores` workers round-robin (a stand-in for rayon's
// work-stealing). The seed column depends only on (seed, index); the core column
// is the only thing the cores control moves.
export function planChunks(shots: number, seed: number, cores: number): Chunk[] {
  const noiseBase = (BigInt(seed) + GOLDEN) & M64;
  const nchunks = Math.max(1, Math.ceil(shots / FRAME_CHUNK));
  const out: Chunk[] = [];

  for (let c = 0; c < nchunks; c += 1) {
    const lo = c * FRAME_CHUNK;

    out.push({
      index: c,
      shots: Math.min(FRAME_CHUNK, shots - lo),
      seed: chunkSeed(noiseBase, BigInt(c)),
      core: c % cores,
    });
  }

  return out;
}
