use pyo3::prelude::*;
use rayon::prelude::*;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static COUNTER: AtomicU64 = AtomicU64::new(0);

// splitmix64 finalizer: the xorshift-multiply avalanche (the >>30/>>27/>>31 folds
// mix the high bits down so every input bit reaches every output bit). shared by
// the Rng stream advance and the per-chunk seed derivation (chunk_seed).
#[inline]
fn splitmix_finalize(z: u64) -> u64 {
    let z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    let z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

// splitmix64 (canonical constants): fast, seedable; fine for measurement coins
// and noise sampling (not crypto).
#[derive(Clone)]
struct Rng {
    s: u64,
}

impl Rng {
    fn new(seed: u64) -> Self {
        Rng { s: seed }
    }
    #[inline]
    fn next_u64(&mut self) -> u64 {
        // advance by the golden-ratio odd constant, then run the splitmix finalizer.
        self.s = self.s.wrapping_add(0x9E37_79B9_7F4A_7C15);
        splitmix_finalize(self.s)
    }
    #[inline]
    fn next_bool(&mut self) -> bool {
        self.next_u64() >> 63 == 1 // high bit
    }
    #[inline]
    fn next_f64(&mut self) -> f64 {
        // top 53 bits / 2^53 -> uniform in [0, 1)
        (self.next_u64() >> 11) as f64 / ((1u64 << 53) as f64)
    }
}

// shots per parallel frame chunk. fixed (not core-derived) so the sample
// output depends only on (seed, this constant) -- reproducible across cores.
const FRAME_CHUNK: usize = 1024;

// shots per chunk for the per-shot tableau sampler. each shot is a full tableau
// (~1000x heavier than a frame shot), so smaller than FRAME_CHUNK for finer
// work-stealing; one tableau alloc per chunk amortizes away.
const BATCH_CHUNK: usize = 256;

// shots per chunk for the importance estimator. each shot is a full tableau + a
// final observable expectation -- heavy, so a small chunk for balance.
const EST_CHUNK: usize = 256;

// Gate opcode ABI. These integer values are the wire protocol shared with Python
// (co-owned by qliff/simulator.py GATE_OPCODE and qliff/noise/sampler.py), so the
// numbers MUST NOT change -- only the names are ours. OP_RESET (9) is reset, used
// only inside quasiprobability branch op streams (estimate_chunk).
const OP_H: u8 = 0;
const OP_S: u8 = 1;
const OP_S_DAG: u8 = 2;
const OP_X: u8 = 3;
const OP_Y: u8 = 4;
const OP_Z: u8 = 5;
const OP_CX: u8 = 6;
const OP_CZ: u8 = 7;
const OP_SWAP: u8 = 8;
const OP_RESET: u8 = 9;

// Per-chunk noise seed: decorrelate (base, chunk) through the splitmix finalizer
// so disjoint shot-chunks draw independent streams.
fn chunk_seed(base: u64, chunk: u64) -> u64 {
    splitmix_finalize(base ^ chunk.wrapping_mul(0x9E37_79B9_7F4A_7C15))
}

// one shot-chunk of the Pauli-frame engine: replay instrs over `chunk_shots`
// shots (bit-packed, 64/word), writing records shot-major into `out`. own buffers
// -> disjoint chunks run in parallel; `ref_bits` (noiseless reference) is read-only.
fn frame_chunk(
    instrs: &[(u8, u32, u32, u32)],
    branches: &[Vec<(f64, Vec<(u8, u32, u32)>)>],
    ref_bits: &[bool],
    n: usize,
    num_meas: usize,
    chunk_shots: usize,
    seed: u64,
    out: &mut [u8],
) {
    let sw = (chunk_shots + 63) / 64; // ceil(chunk_shots/64): words/qubit, 1 bit per shot
    let mut fx = vec![0u64; n * sw];
    let mut fz = vec![0u64; n * sw];
    let mut noise = Rng::new(seed);
    let mut meas_planes: Vec<Vec<u64>> = Vec::with_capacity(num_meas);
    let mut mi = 0usize;

    for &(kind, x, y, z) in instrs {
        match kind {
            0 => {
                let (fa, fb) = ((y as usize) * sw, (z as usize) * sw);
                // x is the gate opcode (see OP_* consts); narrow to u8 to match them.
                match x as u8 {
                    OP_H => {
                        for k in 0..sw {
                            let t = fx[fa + k];
                            fx[fa + k] = fz[fa + k];
                            fz[fa + k] = t;
                        }
                    }
                    OP_S | OP_S_DAG => {
                        for k in 0..sw {
                            fz[fa + k] ^= fx[fa + k];
                        }
                    }
                    OP_X | OP_Y | OP_Z => {} // X/Y/Z: identity on the (sign-free) frame
                    OP_CX => {
                        for k in 0..sw {
                            let fxa = fx[fa + k];
                            let fzb = fz[fb + k];
                            fx[fb + k] ^= fxa;
                            fz[fa + k] ^= fzb;
                        }
                    }
                    OP_CZ => {
                        for k in 0..sw {
                            let fxa = fx[fa + k];
                            let fxb = fx[fb + k];
                            fz[fa + k] ^= fxb;
                            fz[fb + k] ^= fxa;
                        }
                    }
                    OP_SWAP => {
                        for k in 0..sw {
                            fx.swap(fa + k, fb + k);
                            fz.swap(fa + k, fb + k);
                        }
                    }
                    _ => {}
                }
            }
            1 => {
                let fa = (y as usize) * sw;
                if x == 2 {
                    for k in 0..sw {
                        fx[fa + k] = 0;
                        fz[fa + k] = 0;
                    }
                } else {
                    let mask = if ref_bits[mi] { !0u64 } else { 0u64 };
                    mi += 1;
                    let mut plane = vec![0u64; sw];
                    for k in 0..sw {
                        plane[k] = fx[fa + k] ^ mask;
                    }
                    meas_planes.push(plane);
                    if x == 1 {
                        for k in 0..sw {
                            fx[fa + k] = 0;
                            fz[fa + k] = 0;
                        }
                    }
                }
            }
            2 => {
                // rare-error noise via geometric skips. with per-shot fault prob
                // f = fault_weight/total, gaps between faulty shots are geometric,
                // so skip = ln(1-U)/ln(1-f) jumps straight to the next faulty shot
                // (cheap when faults are rare); then pick a branch ~ |weight|.
                let table = &branches[x as usize];
                let total: f64 = table.iter().map(|(w, _)| w.abs()).sum();
                let fault_weight: f64 = table
                    .iter()
                    .filter(|(_, ops)| !ops.is_empty())
                    .map(|(w, _)| w.abs())
                    .sum();
                if fault_weight <= 0.0 {
                    continue;
                }

                let ln1m = (1.0 - fault_weight / total).ln();
                let mut s = 0usize;
                loop {
                    let skip = if ln1m.is_finite() {
                        ((1.0 - noise.next_f64()).ln() / ln1m) as usize
                    } else {
                        0
                    };
                    s = s.saturating_add(skip);
                    if s >= chunk_shots {
                        break;
                    }

                    let thr = (1.0 - noise.next_f64()) * fault_weight;
                    let mut acc = 0.0;
                    let mut chosen = &table[0].1;
                    for (w, ops) in table.iter() {
                        if ops.is_empty() {
                            continue;
                        }
                        acc += w.abs();
                        chosen = ops;
                        if thr <= acc {
                            break;
                        }
                    }

                    let (word, bit) = (s >> 6, 1u64 << (s & 63)); // shot s -> word s/64, mask 2^(s mod 64)
                    for &(op, qa, _qb) in chosen {
                        let fq = (qa as usize) * sw + word;
                        match op {
                            3 => fx[fq] ^= bit,
                            5 => fz[fq] ^= bit,
                            4 => {
                                fx[fq] ^= bit;
                                fz[fq] ^= bit;
                            }
                            _ => {}
                        }
                    }
                    s += 1;
                }
            }
            _ => {}
        }
    }

    // transpose planes (num_meas x chunk_shots) -> shot-major bytes into `out`
    for s in 0..chunk_shots {
        let (word, bit) = (s >> 6, s & 63); // shot s -> (word s/64, bit s mod 64)
        let base = s * num_meas;
        for (m, plane) in meas_planes.iter().enumerate() {
            out[base + m] = ((plane[word] >> bit) & 1) as u8; // pull shot s's bit
        }
    }
}

// pick the branch whose cumulative |weight| first reaches `thr` (a draw already
// scaled to the same total the caller summed over). falls back to the last branch
// when `thr` lands past the accumulated sum (floating-point tail). shared by the
// two per-shot samplers (batch_chunk, estimate_chunk) -- per-shot hot code.
#[inline]
fn pick_branch(table: &[(f64, Vec<(u8, u32, u32)>)], thr: f64) -> usize {
    let mut acc = 0.0;
    let mut pick = table.len() - 1;
    for (i, (w, _)) in table.iter().enumerate() {
        acc += w.abs();
        if thr <= acc {
            pick = i;
            break;
        }
    }
    pick
}

// one shot-chunk of the per-shot tableau MC sampler (used when a measurement is
// random, so the frame method can't apply). each chunk owns a tableau (reset per
// shot) + its own coin/noise RNGs -> parallel, records written shot-major into
// `out`. shots fully independent (no shared reference) so this scales near-linearly.
fn batch_chunk(
    instrs: &[(u8, u32, u32, u32)],
    branches: &[Vec<(f64, Vec<(u8, u32, u32)>)>],
    n: usize,
    chunk_shots: usize,
    coin_seed: u64,
    noise_seed: u64,
    out: &mut [u8],
) {
    let mut t = ColTableau::new(n, Some(coin_seed));
    let mut noise = Rng::new(noise_seed);
    let mut oi = 0usize;

    for _ in 0..chunk_shots {
        t.reset_to_zero();
        t.inner.clear_record();

        for &(kind, x, y, z) in instrs {
            match kind {
                0 => t.apply_gate(x as u8, y as usize, z as usize),
                1 => match x {
                    0 => {
                        out[oi] = t.measure(y as usize, None) as u8;
                        oi += 1;
                    }
                    1 => {
                        out[oi] = t.mr(y as usize) as u8;
                        oi += 1;
                    }
                    _ => t.reset(y as usize),
                },
                2 => {
                    let table = &branches[x as usize];
                    let total: f64 = table.iter().map(|(w, _)| w.abs()).sum();
                    let pick = pick_branch(table, noise.next_f64() * total);
                    for &(op, a, b) in &table[pick].1 {
                        t.apply_gate(op, a as usize, b as usize);
                    }
                }
                _ => {}
            }
        }
    }
}

// one shot-chunk of the quasiprobability importance estimator. per shot: run the
// circuit, picking ONE branch per noise location ~ |weight|/gamma and multiplying
// the trajectory weight by sign(weight)*gamma, then evaluate <observable>. returns
// the partial sum of weight*<O> (caller divides by shots). op 9 = reset, 0..8 =
// gates. unbiased for ANY channel.
#[allow(clippy::too_many_arguments)]
fn estimate_chunk(
    instrs: &[(u8, u32, u32, u32)],
    branches: &[Vec<(f64, Vec<(u8, u32, u32)>)>],
    gammas: &[f64],
    obs_x: &[u8],
    obs_z: &[u8],
    n: usize,
    chunk_shots: usize,
    coin_seed: u64,
    noise_seed: u64,
) -> f64 {
    let mut t = ColTableau::new(n, Some(coin_seed));
    let mut noise = Rng::new(noise_seed);
    let mut acc = 0.0;

    for _ in 0..chunk_shots {
        t.reset_to_zero();
        let mut weight = 1.0f64;

        for &(kind, x, y, z) in instrs {
            match kind {
                0 => t.apply_gate(x as u8, y as usize, z as usize),
                2 => {
                    let table = &branches[x as usize];
                    let gamma = gammas[x as usize];
                    let pick = pick_branch(table, noise.next_f64() * gamma);
                    let (w, ops) = &table[pick];
                    weight *= if *w >= 0.0 { gamma } else { -gamma };
                    for &(op, qa, qb) in ops {
                        if op == OP_RESET {
                            t.reset(qa as usize);
                        } else {
                            t.apply_gate(op, qa as usize, qb as usize);
                        }
                    }
                }
                _ => {}
            }
        }

        t.to_row();
        acc += weight * (t.inner.expectation(obs_x, obs_z) as f64);
    }

    acc
}

// word_g: Sum of g over the 64 Pauli lanes in one word, lane k = P1=(xi,zi)[k],
// P2=(xh,zh)[k]. bit-parallel form of g(): each lane is +1/-1/0, popcount the two
// masks. encoding P=(x,z): I=00 X=10 Z=01 Y=11.
//   +1 lanes: (X,Y) (Z,X) (Y,Z)        -1 lanes: (X,Z) (Z,Y) (Y,X)
// the three +terms (and -terms) live on disjoint lanes -> OR-then-popcount counts
// each once. tail lanes past nq are all-zero => I => 0, so no masking needed.
#[inline]
fn word_g(xi: u64, zi: u64, xh: u64, zh: u64) -> i32 {
    let plus = (xi & !zi & xh & zh) | (!xi & zi & xh & !zh) | (xi & zi & !xh & zh);
    let minus = (xi & !zi & !xh & zh) | (!xi & zi & xh & zh) | (xi & zi & xh & !zh);
    plus.count_ones() as i32 - minus.count_ones() as i32
}

// CNOT-Hadamard-Phase tableau (Aaronson-Gottesman). 2n+1 rows:
//   0..n    destabilizers
//   n..2n   stabilizers
//   2n      scratch (measurement)
// init is always |0...0> (destab i = X_i, stab i = Z_i) -- keeps ZZ trivial.
// not a #[pyclass]: it is an internal engine reached only through ColTableau.inner
// (measurement, records, expectation), never constructed from Python.
#[derive(Clone)]
pub(crate) struct RowTableau {
    nq: usize,
    // words per row: ceil(n/64)
    w: usize,
    // bit-packed Pauli rows. qubit j of row r lives at word j>>6 (= j/64), bit
    // j&63 (= j mod 64); single-bit mask 1<<(j&63) (= 2^(j mod 64)). this packing
    // (>>6 word, &63 bit, 1<<… mask) recurs throughout the file.
    xs: Vec<u64>,
    zs: Vec<u64>,
    // per-row phase bit: 0 => +, 1 => -
    signs: Vec<u8>,
    // measurement outcomes, in call order
    record: Vec<bool>,
    rng: Rng,
}

/*
Each row is a Pauli held across the parallel xs / zs / signs arrays: an X-part,
a Z-part, and a sign. For |00> (n=2), with each X/Z byte shown bit j = qubit j:

       x         z         r   Pauli
row 0  00000001  00000000  +   X₀      ← destab
row 1  00000010  00000000  +   X₁      ← destab
row 2  00000000  00000001  +   Z₀      ← stab  ┐ stabilized by +Z₀, +Z₁
row 3  00000000  00000010  +   Z₁      ← stab  ┘ ⇒ |00⟩
row 4  00000000  00000000  +   I            ← scratch
*/
impl RowTableau {
    // read bit j of row i: word i*w + j/64, shift bit j mod 64 down, mask to bool.
    #[inline]
    fn get_x(&self, i: usize, j: usize) -> bool {
        (self.xs[i * self.w + (j >> 6)] >> (j & 63)) & 1 == 1
    }

    #[inline]
    fn get_z(&self, i: usize, j: usize) -> bool {
        (self.zs[i * self.w + (j >> 6)] >> (j & 63)) & 1 == 1
    }
    #[inline]
    fn set_z(&mut self, i: usize, j: usize, v: bool) {
        let id = i * self.w + (j >> 6);
        let m = 1u64 << (j & 63);

        if v {
            self.zs[id] |= m;
        } else {
            self.zs[id] &= !m;
        }
    }

    fn zero_row(&mut self, r: usize) {
        for k in 0..self.w {
            self.xs[r * self.w + k] = 0;
            self.zs[r * self.w + k] = 0;
        }

        self.signs[r] = 0;
    }

    fn copy_row(&mut self, dst: usize, src: usize) {
        for k in 0..self.w {
            let xv = self.xs[src * self.w + k];
            let zv = self.zs[src * self.w + k];

            self.xs[dst * self.w + k] = xv;
            self.zs[dst * self.w + k] = zv;
        }
        self.signs[dst] = self.signs[src];
    }

    // reset bits to |0...0> in place (reuse buffers; leaves rng + record alone).
    fn reset_to_zero(&mut self) {
        for v in self.xs.iter_mut() {
            *v = 0;
        }
        for v in self.zs.iter_mut() {
            *v = 0;
        }
        for s in self.signs.iter_mut() {
            *s = 0;
        }
        let (n, w) = (self.nq, self.w);
        for i in 0..n {
            self.xs[i * w + (i >> 6)] |= 1u64 << (i & 63);
            self.zs[(n + i) * w + (i >> 6)] |= 1u64 << (i & 63);
        }
    }

    fn rowsum(&mut self, h: usize, i: usize) {
        let ib = i * self.w;
        let hb = h * self.w;

        // total i-power exponent: 2*r_i + 2*r_h + Σ_j g(row_i[j], row_h[j]),
        // accumulated a word (64 lanes) at a time instead of qubit by qubit.
        let mut sum: i64 = 2 * (self.signs[h] as i64) + 2 * (self.signs[i] as i64);
        for k in 0..self.w {
            sum += word_g(self.xs[ib + k], self.zs[ib + k], self.xs[hb + k], self.zs[hb + k]) as i64;
        }

        self.signs[h] =
            if sum.rem_euclid(4) == 0 {
                 0
            } else {
                1
            };

        for k in 0..self.w {
            self.xs[hb + k] ^= self.xs[ib + k];
            self.zs[hb + k] ^= self.zs[ib + k];
        }
    }

    // returns (outcome, was_random): was_random = true if the measured qubit
    // anticommuted with a stabilizer (a genuine coin flip) vs a fixed outcome.
    fn do_measure(&mut self, a: usize, force: Option<bool>) -> (bool, bool) {
        let n = self.nq;
        let mut p = None;
        for k in n..2 * n {
            if self.get_x(k, a) {
                p = Some(k);
                break;
            }
        }
        match p {
            Some(p) => {
                for ii in 0..2 * n {
                    if ii != p && self.get_x(ii, a) {
                        self.rowsum(ii, p);
                    }
                }
                self.copy_row(p - n, p);
                self.zero_row(p);
                self.set_z(p, a, true);
                let bit = match force {
                    Some(b) => b,
                    None => self.rng.next_bool(),
                };
                self.signs[p] = bit as u8;
                (bit, true)
            }
            None => {
                let sc = 2 * n;
                self.zero_row(sc);
                for ii in 0..n {
                    if self.get_x(ii, a) {
                        self.rowsum(sc, ii + n);
                    }
                }
                (self.signs[sc] != 0, false)
            }
        }
    }

    // symplectic product of row r with Pauli (px,pz); 1 => they anticommute
    fn anticommutes(&self, r: usize, px: &[u8], pz: &[u8]) -> bool {
        let mut sp = 0u8;
        for j in 0..self.nq {
            sp ^= (px[j] & self.get_z(r, j) as u8) ^ (pz[j] & self.get_x(r, j) as u8);
        }
        sp & 1 == 1
    }

    // overwrite row r with the unsigned Pauli (px,pz)
    fn set_row_pauli(&mut self, r: usize, px: &[u8], pz: &[u8]) {
        self.zero_row(r);
        for j in 0..self.nq {
            if px[j] != 0 {
                self.xs[r * self.w + (j >> 6)] |= 1u64 << (j & 63);
            }
            if pz[j] != 0 {
                self.zs[r * self.w + (j >> 6)] |= 1u64 << (j & 63);
            }
        }
    }

    fn row_tuple(&self, i: usize) -> (bool, Vec<u8>, Vec<u8>) {
        let xs = (0..self.nq).map(|j| self.get_x(i, j) as u8).collect();
        let zs = (0..self.nq).map(|j| self.get_z(i, j) as u8).collect();
        (self.signs[i] != 0, xs, zs)
    }
}

impl RowTableau {
    fn new(n: usize, seed: Option<u64>) -> Self {
        let w = (n + 63) / 64;
        let rows = 2 * n + 1;
        // default seed: wall-clock nanos XOR a per-process counter (unique per RowTableau)
        let seed = seed.unwrap_or_else(|| {
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_nanos() as u64)
                .unwrap_or(0x1234_5678);
            let c = COUNTER.fetch_add(1, Ordering::Relaxed);
            nanos ^ c.wrapping_mul(0x9E37_79B9_7F4A_7C15)
        });
        let mut t = RowTableau {
            nq: n,
            w,
            xs: vec![0u64; rows * w],
            zs: vec![0u64; rows * w],
            signs: vec![0u8; rows],
            record: Vec::new(),
            rng: Rng::new(seed),
        };
        // |0...0>: destabilizer i = X_i, stabilizer i = Z_i
        for i in 0..n {
            t.xs[i * w + (i >> 6)] |= 1u64 << (i & 63);
            t.zs[(n + i) * w + (i >> 6)] |= 1u64 << (i & 63);
        }
        t
    }

    // X: sign ^= z. the only single-qubit gate the row engine still applies
    // directly (mr/reset flip the measured qubit; frame_reference replays MR).
    fn x(&mut self, a: usize) {
        let wa = a >> 6;
        let sh = a & 63;
        for i in 0..2 * self.nq {
            let zb = (self.zs[i * self.w + wa] >> sh) & 1;
            self.signs[i] ^= zb as u8;
        }
    }

    fn measure(&mut self, a: usize, force: Option<bool>) -> bool {
        let o = self.do_measure(a, force).0;
        self.record.push(o);
        o
    }

    // measure, then reset qubit a to |0>
    fn mr(&mut self, a: usize) -> bool {
        let o = self.do_measure(a, None).0;
        self.record.push(o);
        if o {
            self.x(a);
        }
        o
    }

    // collapse qubit a and force it to |0>
    fn reset(&mut self, a: usize) {
        if self.do_measure(a, None).0 {
            self.x(a);
        }
    }

    fn record(&self) -> Vec<bool> {
        self.record.clone()
    }

    fn clear_record(&mut self) {
        self.record.clear();
    }

    fn stabilizers(&self) -> Vec<(bool, Vec<u8>, Vec<u8>)> {
        (self.nq..2 * self.nq).map(|i| self.row_tuple(i)).collect()
    }

    fn destabilizers(&self) -> Vec<(bool, Vec<u8>, Vec<u8>)> {
        (0..self.nq).map(|i| self.row_tuple(i)).collect()
    }

    // <P> for Pauli (px,pz):
    //   P anticommutes with any stabilizer        -> 0   (P ∉ stabilizer group)
    //   else  P = ± Π stab_k over destabs k that anticommute with P
    //         rebuild that product in scratch (sx,sz,ssign); return its sign as ±1
    fn expectation(&self, px: &[u8], pz: &[u8]) -> i8 {
        let n = self.nq;
        for k in n..2 * n {
            let mut sp = 0u8;
            for j in 0..n {
                sp ^= (px[j] & self.get_z(k, j) as u8) ^ (pz[j] & self.get_x(k, j) as u8);
            }
            if sp & 1 == 1 {
                return 0;
            }
        }
        let mut sx = vec![0u64; self.w];
        let mut sz = vec![0u64; self.w];
        let mut ssign: i64 = 0;
        for k in 0..n {
            let mut sp = 0u8;
            for j in 0..n {
                sp ^= (px[j] & self.get_z(k, j) as u8) ^ (pz[j] & self.get_x(k, j) as u8);
            }
            if sp & 1 == 1 {
                let st = n + k;
                let stb = st * self.w;
                // scratch (sx,sz) <- stab_st * scratch; phase accumulated word-wise.
                let mut sum: i64 = 2 * ssign + 2 * (self.signs[st] as i64);
                for w in 0..self.w {
                    sum += word_g(self.xs[stb + w], self.zs[stb + w], sx[w], sz[w]) as i64;
                }
                ssign = if sum.rem_euclid(4) == 0 { 0 } else { 1 };
                for w in 0..self.w {
                    sx[w] ^= self.xs[stb + w];
                    sz[w] ^= self.zs[stb + w];
                }
            }
        }
        if ssign == 0 {
            1
        } else {
            -1
        }
    }

    fn measure_pauli(&mut self, px: Vec<u8>, pz: Vec<u8>, force: Option<bool>) -> (bool, bool) {
        let n = self.nq;
        let mut p = None;
        for k in n..2 * n {
            if self.anticommutes(k, &px, &pz) {
                p = Some(k);
                break;
            }
        }
        match p {
            Some(p) => {
                for ii in 0..2 * n {
                    if ii != p && self.anticommutes(ii, &px, &pz) {
                        self.rowsum(ii, p);
                    }
                }
                self.copy_row(p - n, p);
                self.set_row_pauli(p, &px, &pz);
                let bit = match force {
                    Some(b) => b,
                    None => self.rng.next_bool(),
                };
                self.signs[p] = bit as u8;
                (bit, true)
            }
            None => {
                let sc = 2 * n;
                self.zero_row(sc);
                for k in 0..n {
                    if self.anticommutes(k, &px, &pz) {
                        self.rowsum(sc, k + n);
                    }
                }
                (self.signs[sc] != 0, false)
            }
        }
    }
}

// ---------------------------------------------------------------------------
// ColTableau: column-major (qubit-major) bit planes for word-parallel gates,
// transposed to the row-major engine (`inner`, the RowTableau above) for
// measurement. `layout` says which side is authoritative; we transpose lazily,
// only when the op kind switches. a gate touches O(rows/64) words per plane
// (signs included) instead of O(rows) scalar touches -- no cache cliff,
// auto-vectorizable. measurement delegates to the proven row-major path so its
// lead is preserved. transpose is 64x64 blocked (transpose64), amortized one per
// measurement round.
// ---------------------------------------------------------------------------

// in-place transpose of a 64x64 bit matrix stored as 64 u64 rows: bit b of a[r]
// is M[r][b]; after, bit r of a[b] is M[r][b]. Hacker's Delight (6 mask/shift
// passes) -- O(64 log 64) word ops, not 64*64 bit moves. core of to_col/to_row;
// replaced the old bit-by-bit transpose (8+ seconds at n=65536).
#[inline]
fn transpose64(a: &mut [u64; 64]) {
    // LSB-column (bit b of a[r] is column b): swap a[k]'s high half with a[k+j]'s
    // low half. Hacker's Delight is MSB-column; flipping the shifted operand gives
    // the LSB form -- verified against a naive transpose.
    let mut j = 32usize; // block size, halving: 32, 16, 8, 4, 2, 1
    let mut m = 0x0000_0000_FFFF_FFFFu64; // mask selecting the low half of each 2j block
    while j != 0 {
        let mut k = 0usize;
        while k < 64 {
            let t = ((a[k] >> j) ^ a[k + j]) & m; // bits that differ between the two j-blocks
            a[k] ^= t << j;
            a[k + j] ^= t; // swap those bits -> transposes the j x j block pair
            k = (k + j + 1) & !j; // advance to the next block pair (skip the j we just did)
        }
        j >>= 1; // halve the block size
        m ^= m << j; // rebuild the mask for the smaller blocks
    }
}

// two disjoint &mut plane slices (length rw) from one col-major Vec, in (plane p,
// plane q) order; requires p != q. split_at_mut keeps the 2-qubit kernels
// bounds-check-free, so they vectorize like the 1-qubit ones.
#[inline]
fn planes_mut(v: &mut [u64], p: usize, q: usize, rw: usize) -> (&mut [u64], &mut [u64]) {
    if p < q {
        let (lo, hi) = v.split_at_mut(q * rw);
        (&mut lo[p * rw..p * rw + rw], &mut hi[..rw])
    } else {
        let (lo, hi) = v.split_at_mut(p * rw);
        (&mut hi[..rw], &mut lo[q * rw..q * rw + rw])
    }
}

// col-major gate kernels. a qubit's plane is rw contiguous words, so a gate is a
// vector sweep over length-rw slices. passing slices (not indexed access) drops
// the bounds check and lets LLVM emit NEON -- the SIMD path that pulls large-n
// gates ahead of stim. `sign` is the sign plane. #[inline]: one source for both
// gate() and run(), folded into the hot loop with no per-gate call cost.
#[inline]
fn k_h(sign: &mut [u64], x: &mut [u64], z: &mut [u64]) {
    for ((s, xa), za) in sign.iter_mut().zip(x.iter_mut()).zip(z.iter_mut()) {
        let (xv, zv) = (*xa, *za);
        *s ^= xv & zv;
        *xa = zv;
        *za = xv;
    }
}
#[inline]
fn k_s(sign: &mut [u64], x: &[u64], z: &mut [u64]) {
    for ((s, &xv), za) in sign.iter_mut().zip(x.iter()).zip(z.iter_mut()) {
        *s ^= xv & *za;
        *za ^= xv;
    }
}
#[inline]
fn k_sdag(sign: &mut [u64], x: &[u64], z: &mut [u64]) {
    for ((s, &xv), za) in sign.iter_mut().zip(x.iter()).zip(z.iter_mut()) {
        *s ^= xv & !*za;
        *za ^= xv;
    }
}
#[inline]
fn k_x(sign: &mut [u64], z: &[u64]) {
    for (s, &zv) in sign.iter_mut().zip(z.iter()) {
        *s ^= zv;
    }
}
#[inline]
fn k_y(sign: &mut [u64], x: &[u64], z: &[u64]) {
    for ((s, &xv), &zv) in sign.iter_mut().zip(x.iter()).zip(z.iter()) {
        *s ^= xv ^ zv;
    }
}
#[inline]
fn k_z(sign: &mut [u64], x: &[u64]) {
    for (s, &xv) in sign.iter_mut().zip(x.iter()) {
        *s ^= xv;
    }
}
// CX a->b: x_b ^= x_a; z_a ^= z_b; sign ^= x_a & z_b & (x_b ^ z_a ^ 1). sign uses
// the OLD x_b, z_a (read before the updates).
#[inline]
fn k_cx(sign: &mut [u64], xa: &[u64], za: &mut [u64], xb: &mut [u64], zb: &[u64]) {
    for ((((s, &xav), zav), xbv), &zbv) in sign
        .iter_mut()
        .zip(xa.iter())
        .zip(za.iter_mut())
        .zip(xb.iter_mut())
        .zip(zb.iter())
    {
        *s ^= xav & zbv & (*xbv ^ *zav ^ !0u64);
        *xbv ^= xav;
        *zav ^= zbv;
    }
}
// CZ (symmetric): z_a ^= x_b; z_b ^= x_a; sign ^= x_a & x_b & (z_a ^ z_b).
#[inline]
fn k_cz(sign: &mut [u64], xa: &[u64], za: &mut [u64], xb: &[u64], zb: &mut [u64]) {
    for ((((s, &xav), zav), &xbv), zbv) in sign
        .iter_mut()
        .zip(xa.iter())
        .zip(za.iter_mut())
        .zip(xb.iter())
        .zip(zb.iter_mut())
    {
        *s ^= xav & xbv & (*zav ^ *zbv);
        *zav ^= xbv;
        *zbv ^= xav;
    }
}

#[derive(Clone, Copy, PartialEq)]
enum Layout {
    Row,
    Col,
}

#[pyclass]
#[derive(Clone)]
pub struct ColTableau {
    nq: usize,
    // 2n+1 rows (n destab, n stab, 1 scratch)
    rows: usize,
    // ceil(n/64): words per row-major row
    w: usize,
    // ceil(rows/64): words per column plane
    rw: usize,
    // column-major planes over rows; column j -> words [j*rw .. (j+1)*rw)
    xc: Vec<u64>,
    zc: Vec<u64>,
    // sign as a bit plane over rows
    signc: Vec<u64>,
    layout: Layout,
    // row-major measurement engine; also owns the rng + record
    inner: RowTableau,
}

impl ColTableau {
    // make the row-major engine authoritative (measurement reads it). inverse of
    // to_col: transpose col-major (nq x rows) back to row-major in 64x64 blocks,
    // each inner.xs/zs word written exactly once.
    fn to_row(&mut self) {
        if self.layout == Layout::Row {
            return;
        }
        let (w, rw, rows, nq) = (self.w, self.rw, self.rows, self.nq);
        let mut j0 = 0;
        while j0 < nq {
            let cb = (nq - j0).min(64);
            let jw = j0 >> 6;
            let mut r0 = 0;
            while r0 < rows {
                let rb = (rows - r0).min(64);
                let rword = r0 >> 6;
                let mut bx = [0u64; 64];
                let mut bz = [0u64; 64];
                for bb in 0..cb {
                    bx[bb] = self.xc[(j0 + bb) * rw + rword];
                    bz[bb] = self.zc[(j0 + bb) * rw + rword];
                }
                transpose64(&mut bx);
                transpose64(&mut bz);
                for rr in 0..rb {
                    self.inner.xs[(r0 + rr) * w + jw] = bx[rr];
                    self.inner.zs[(r0 + rr) * w + jw] = bz[rr];
                }
                r0 += 64;
            }
            j0 += 64;
        }
        for r in 0..rows {
            self.inner.signs[r] = ((self.signc[r >> 6] >> (r & 63)) & 1) as u8;
        }
        self.layout = Layout::Row;
    }

    // make the col-major planes authoritative (gates touch them). transpose the
    // row-major (rows x nq) matrix into col-major in 64x64 blocks via transpose64:
    // each output word written exactly once (no pre-zero), word-parallel.
    fn to_col(&mut self) {
        if self.layout == Layout::Col {
            return;
        }
        let (w, rw, rows, nq) = (self.w, self.rw, self.rows, self.nq);
        let mut r0 = 0;
        while r0 < rows {
            let rb = (rows - r0).min(64);
            let rword = r0 >> 6;
            let mut j0 = 0;
            while j0 < nq {
                let cb = (nq - j0).min(64);
                let jw = j0 >> 6;
                let mut bx = [0u64; 64];
                let mut bz = [0u64; 64];
                for rr in 0..rb {
                    bx[rr] = self.inner.xs[(r0 + rr) * w + jw];
                    bz[rr] = self.inner.zs[(r0 + rr) * w + jw];
                }
                transpose64(&mut bx);
                transpose64(&mut bz);
                for bb in 0..cb {
                    self.xc[(j0 + bb) * rw + rword] = bx[bb];
                    self.zc[(j0 + bb) * rw + rword] = bz[bb];
                }
                j0 += 64;
            }
            r0 += 64;
        }
        // sign is a 1-bit-per-row plane: pack inner.signs into signc (O(rows)).
        for v in self.signc.iter_mut() {
            *v = 0;
        }
        for r in 0..rows {
            if self.inner.signs[r] != 0 {
                self.signc[r >> 6] |= 1u64 << (r & 63);
            }
        }
        self.layout = Layout::Col;
    }

    // the one place col-major gate logic lives. whole-plane op by opcode (OP_*
    // consts: 0=H 1=S 2=S_DAG 3=X 4=Y 5=Z 6=CX 7=CZ 8=SWAP); b unused for 1-qubit.
    // caller must already be Col layout. #[inline] folds the dispatch into run()'s
    // hot loop.
    #[inline]
    fn gate(&mut self, op: u8, a: usize, b: usize) {
        let rw = self.rw;
        let base = a * rw;
        match op {
            OP_H => k_h(
                &mut self.signc[..rw],
                &mut self.xc[base..base + rw],
                &mut self.zc[base..base + rw],
            ),
            OP_S => k_s(
                &mut self.signc[..rw],
                &self.xc[base..base + rw],
                &mut self.zc[base..base + rw],
            ),
            OP_S_DAG => k_sdag(
                &mut self.signc[..rw],
                &self.xc[base..base + rw],
                &mut self.zc[base..base + rw],
            ),
            OP_X => k_x(&mut self.signc[..rw], &self.zc[base..base + rw]),
            OP_Y => k_y(
                &mut self.signc[..rw],
                &self.xc[base..base + rw],
                &self.zc[base..base + rw],
            ),
            OP_Z => k_z(&mut self.signc[..rw], &self.xc[base..base + rw]),
            OP_CX => {
                let (xa, xb) = planes_mut(&mut self.xc, a, b, rw);
                let (za, zb) = planes_mut(&mut self.zc, a, b, rw);
                k_cx(&mut self.signc[..rw], xa, za, xb, zb);
            }
            OP_CZ => {
                let (xa, xb) = planes_mut(&mut self.xc, a, b, rw);
                let (za, zb) = planes_mut(&mut self.zc, a, b, rw);
                k_cz(&mut self.signc[..rw], xa, za, xb, zb);
            }
            OP_SWAP => {
                self.gate(OP_CX, a, b);
                self.gate(OP_CX, b, a);
                self.gate(OP_CX, a, b);
            }
            _ => {}
        }
    }

    // ensure Col layout, then apply one gate (for the interleaved sample loop).
    fn apply_gate(&mut self, op: u8, a: usize, b: usize) {
        self.to_col();
        self.gate(op, a, b);
    }

    // reset to |0...0> in place; col planes go stale (rebuilt lazily on to_col).
    fn reset_to_zero(&mut self) {
        self.inner.reset_to_zero();
        self.layout = Layout::Row;
    }
}

#[pymethods]
impl ColTableau {
    #[new]
    #[pyo3(signature = (n, seed=None))]
    fn new(n: usize, seed: Option<u64>) -> Self {
        let rows = 2 * n + 1;
        let rw = (rows + 63) / 64;
        let mut t = ColTableau {
            nq: n,
            rows,
            w: (n + 63) / 64,
            rw,
            xc: vec![0u64; n * rw],
            zc: vec![0u64; n * rw],
            signc: vec![0u64; rw],
            // col-major IS authoritative from the start: build |0...0> directly here
            // (O(n)) so a pure-gate run never pays the row->col transpose. inner is
            // |0...0> too (rebuilt from the planes on the first measurement).
            layout: Layout::Col,
            inner: RowTableau::new(n, seed),
        };
        // |0...0>: destab j = X_j -> xc plane j, bit at row j;
        //          stab  j = Z_j -> zc plane j, bit at row n+j.
        for j in 0..n {
            t.xc[j * rw + (j >> 6)] |= 1u64 << (j & 63);
            let s = n + j;
            t.zc[j * rw + (s >> 6)] |= 1u64 << (s & 63);
        }
        t
    }

    #[getter]
    fn n(&self) -> usize {
        self.nq
    }

    // 1- and 2-qubit gates: ensure Col layout, then the shared `gate` core.
    fn h(&mut self, a: usize) {
        self.to_col();
        self.gate(0, a, 0);
    }

    fn s(&mut self, a: usize) {
        self.to_col();
        self.gate(1, a, 0);
    }

    fn s_dag(&mut self, a: usize) {
        self.to_col();
        self.gate(2, a, 0);
    }

    fn x(&mut self, a: usize) {
        self.to_col();
        self.gate(3, a, 0);
    }

    fn y(&mut self, a: usize) {
        self.to_col();
        self.gate(4, a, 0);
    }

    fn z(&mut self, a: usize) {
        self.to_col();
        self.gate(5, a, 0);
    }

    fn cx(&mut self, a: usize, b: usize) {
        self.to_col();
        self.gate(6, a, b);
    }

    fn cz(&mut self, a: usize, b: usize) {
        self.to_col();
        self.gate(7, a, b);
    }

    fn swap(&mut self, a: usize, b: usize) {
        self.to_col();
        self.gate(8, a, b);
    }

    // apply a compiled (op, a, b) stream in one call: one to_col for the whole
    // batch, no per-gate Python dispatch. replays through the shared #[inline]
    // gate() core -- it folds back into this hot loop with identical codegen to an
    // inlined match, so there is a single source for the col-major gate math.
    fn run(&mut self, ops: Vec<(u8, u32, u32)>) {
        self.to_col();
        for (op, a, b) in ops {
            self.gate(op, a as usize, b as usize);
        }
    }

    // batched Pauli-noise trajectory sampler (fast path for Circuit.sample).
    // instrs: (kind, x, y, z) with
    //   kind 0 = gate(op=x, a=y, b=z)
    //   kind 1 = measure(sub=x: 0=M 1=MR 2=R, qubit=y) -- M/MR push a record bit
    //   kind 2 = noise(table=x): pick one branch ~ |weight|, apply its ops
    // branches[i] = [(weight, [(op,a,b)..])..] (precompiled in Python). one reused
    // tableau, reset per shot. returns (flat shots*num_meas bytes, num_meas).
    // non-Pauli ops never reach here (Python falls back), so this stays Pauli-only.
    fn sample_batch(
        &self,
        instrs: Vec<(u8, u32, u32, u32)>,
        branches: Vec<Vec<(f64, Vec<(u8, u32, u32)>)>>,
        shots: usize,
        seed: u64,
    ) -> (Vec<u8>, usize) {
        // parallel over fixed-size shot chunks (BATCH_CHUNK): each owns a tableau +
        // deterministic per-chunk coin/noise RNGs -> reproducible regardless of core
        // count. no shared reference (shots independent) -> near-linear. flat
        // shots*num_meas byte buffer out (Python views it as a uint8 array).
        let num_meas = instrs.iter().filter(|&&(k, x, _, _)| k == 1 && x != 2).count();
        if num_meas == 0 || shots == 0 {
            return (vec![0u8; shots * num_meas], num_meas);
        }

        let n = self.nq;
        let noise_base = seed.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut out = vec![0u8; shots * num_meas];
        out.par_chunks_mut(BATCH_CHUNK * num_meas)
            .enumerate()
            .for_each(|(c, slice)| {
                batch_chunk(
                    &instrs,
                    &branches,
                    n,
                    slice.len() / num_meas,
                    chunk_seed(seed, c as u64),
                    chunk_seed(noise_base, c as u64),
                    slice,
                );
            });

        (out, num_meas)
    }

    // noiseless reference run for the frame sampler: the deterministic measurement
    // bits, or None if ANY measurement is random (caller falls back to sample_batch
    // -- a genuine coin the frame method can't model). CIRCUIT-ONLY (seed-
    // independent), so CompiledSampler computes it once and reuses it across
    // sample() calls -- amortizing this serial pass over a whole LER sweep.
    fn frame_reference(&self, instrs: Vec<(u8, u32, u32, u32)>) -> Option<Vec<bool>> {
        // run on the col-major engine: gate replay is ~20x faster than the old
        // row-major path (the cache cliff). only the measurements transpose to the
        // row engine (`inner`).
        let mut refsim = ColTableau::new(self.nq, Some(0));
        let mut ref_bits: Vec<bool> = Vec::new();
        for &(kind, x, y, z) in &instrs {
            match kind {
                0 => refsim.apply_gate(x as u8, y as usize, z as usize),
                1 => {
                    let a = y as usize;
                    if x == 2 {
                        refsim.reset(a); // R: no record, randomness discarded
                    } else {
                        refsim.to_row();
                        let (bit, random) = refsim.inner.do_measure(a, None);
                        if random {
                            return None; // fall back to sample_batch
                        }
                        ref_bits.push(bit);
                        if x == 1 && bit {
                            refsim.inner.x(a); // MR: reset to |0>
                        }
                    }
                }
                _ => {} // kind 2 = noise: skipped in the reference
            }
        }

        Some(ref_bits)
    }

    // parallel Pauli-frame engine over `shots`, given precomputed `ref_bits` (from
    // frame_reference). propagates bit-packed frames (64 shots/word, sign-free) +
    // rare-error noise, recording ref_bit XOR frame_x[q]. fixed chunk size
    // (FRAME_CHUNK) -> reproducible regardless of cores.
    fn frame_run(
        &self,
        instrs: Vec<(u8, u32, u32, u32)>,
        branches: Vec<Vec<(f64, Vec<(u8, u32, u32)>)>>,
        ref_bits: Vec<bool>,
        shots: usize,
        seed: u64,
    ) -> (Vec<u8>, usize) {
        let n = self.nq;
        let num_meas = ref_bits.len();
        if num_meas == 0 || shots == 0 {
            return (vec![0u8; shots * num_meas], num_meas);
        }

        let noise_base = seed.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut out = vec![0u8; shots * num_meas];
        out.par_chunks_mut(FRAME_CHUNK * num_meas)
            .enumerate()
            .for_each(|(c, slice)| {
                frame_chunk(
                    &instrs,
                    &branches,
                    &ref_bits,
                    n,
                    num_meas,
                    slice.len() / num_meas,
                    chunk_seed(noise_base, c as u64),
                    slice,
                );
            });

        (out, num_meas)
    }

    // quasiprobability importance estimator for <observable> under general noise.
    // instrs: 0=gate(op,a,b), 2=noise(table=x). branches[i] = [(SIGNED weight,
    // [(op,a,b)..])..] (op 9 = reset). parallel over fixed chunks, reproducible
    // regardless of cores. unbiased for ANY channel -- the differentiating
    // coherent/amplitude path, off the Python/GIL loop.
    fn estimate(
        &self,
        instrs: Vec<(u8, u32, u32, u32)>,
        branches: Vec<Vec<(f64, Vec<(u8, u32, u32)>)>>,
        obs_x: Vec<u8>,
        obs_z: Vec<u8>,
        shots: usize,
        seed: u64,
    ) -> f64 {
        if shots == 0 {
            return 0.0;
        }

        let n = self.nq;
        let gammas: Vec<f64> = branches
            .iter()
            .map(|t| t.iter().map(|(w, _)| w.abs()).sum())
            .collect();
        let noise_base = seed.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let nchunks = shots.div_ceil(EST_CHUNK);
        let total: f64 = (0..nchunks)
            .into_par_iter()
            .map(|c| {
                let lo = c * EST_CHUNK;
                let cs = EST_CHUNK.min(shots - lo);
                estimate_chunk(
                    &instrs,
                    &branches,
                    &gammas,
                    &obs_x,
                    &obs_z,
                    n,
                    cs,
                    chunk_seed(seed, c as u64),
                    chunk_seed(noise_base, c as u64),
                )
            })
            .sum();

        total / shots as f64
    }

    #[pyo3(signature = (a, force=None))]
    fn measure(&mut self, a: usize, force: Option<bool>) -> bool {
        self.to_row();
        self.inner.measure(a, force)
    }

    fn mr(&mut self, a: usize) -> bool {
        self.to_row();
        self.inner.mr(a)
    }

    fn reset(&mut self, a: usize) {
        self.to_row();
        self.inner.reset(a);
    }

    #[getter]
    fn record(&self) -> Vec<bool> {
        self.inner.record()
    }

    fn clear_record(&mut self) {
        self.inner.clear_record();
    }

    fn stabilizers(&mut self) -> Vec<(bool, Vec<u8>, Vec<u8>)> {
        self.to_row();
        self.inner.stabilizers()
    }

    fn destabilizers(&mut self) -> Vec<(bool, Vec<u8>, Vec<u8>)> {
        self.to_row();
        self.inner.destabilizers()
    }

    fn expectation(&mut self, px: Vec<u8>, pz: Vec<u8>) -> i8 {
        self.to_row();
        self.inner.expectation(&px, &pz)
    }

    #[pyo3(signature = (px, pz, force=None))]
    fn measure_pauli(&mut self, px: Vec<u8>, pz: Vec<u8>, force: Option<bool>) -> (bool, bool) {
        self.to_row();
        self.inner.measure_pauli(px, pz, force)
    }

    fn copy(&self) -> ColTableau {
        self.clone()
    }

    fn __repr__(&self) -> String {
        format!("ColTableau(n={})", self.nq)
    }
}

#[cfg(test)]
mod tests {
    use super::word_g;

    // Scalar reference for the phase g = power of i when (x1,z1) * (x2,z2).
    // Encoding I=(0,0) X=(1,0) Z=(0,1) Y=(1,1); result in {-1, 0, +1}:
    //   P1=I -> 0
    //   P1=X -> z2*(2*x2-1)   = +1 if P2=Y, -1 if P2=Z, else 0
    //   P1=Z -> x2*(1-2*z2)   = +1 if P2=X, -1 if P2=Y, else 0
    //   P1=Y -> z2 - x2       = +1 if P2=Z, -1 if P2=X, else 0
    // this is the former dead scalar helper, now kept only as the correctness
    // oracle for the bit-parallel word_g used in the hot path.
    fn g(x1: bool, z1: bool, x2: bool, z2: bool) -> i32 {
        match (x1, z1) {
            (false, false) => 0,                                  // I
            (true, false) => (z2 as i32) * (2 * (x2 as i32) - 1), // X
            (false, true) => (x2 as i32) * (1 - 2 * (z2 as i32)), // Z
            (true, true) => (z2 as i32) - (x2 as i32),            // Y
        }
    }

    // word_g on single-bit inputs sums g over one active lane (the other 63 lanes
    // are identity -> 0), so it must equal the scalar g on every Pauli pair.
    #[test]
    fn word_g_matches_scalar() {
        for a in 0..4u64 {
            for b in 0..4u64 {
                let (x1, z1) = (a & 1, (a >> 1) & 1);
                let (x2, z2) = (b & 1, (b >> 1) & 1);
                let expected = g(x1 == 1, z1 == 1, x2 == 1, z2 == 1);
                let got = word_g(x1, z1, x2, z2);
                assert_eq!(got, expected, "word_g disagrees at a={a} b={b}");
            }
        }
    }
}
