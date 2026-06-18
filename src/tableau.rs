use pyo3::prelude::*;
use rayon::prelude::*;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static COUNTER: AtomicU64 = AtomicU64::new(0);

// splitmix64: Someone has to check this. Its whole
// ass AI generated, and Ive not even looked at it
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
        self.s = self.s.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.s;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    #[inline]
    fn next_bool(&mut self) -> bool {
        self.next_u64() >> 63 == 1
    }
    #[inline]
    fn next_f64(&mut self) -> f64 {
        // 53-bit mantissa in [0, 1)
        (self.next_u64() >> 11) as f64 / ((1u64 << 53) as f64)
    }
}

// Shots per parallel frame chunk. FIXED (not core-derived) so frame_sample's
// output depends only on (seed, this constant) -- reproducible no matter how many
// cores run it. Small enough that #chunks >> #cores for typical runs (good load
// balance), big enough that per-chunk setup amortizes; per-chunk frame buffers
// (n * ceil(1024/64) u64 each) stay L2-resident.
const FRAME_CHUNK: usize = 1024;

// Shots per parallel chunk for the per-shot tableau sampler (sample_batch). Each
// shot is ~1000x heavier than a frame shot (full tableau), so use a smaller chunk
// for finer work-stealing granularity; one tableau alloc per chunk amortizes away.
const BATCH_CHUNK: usize = 256;

// Shots per parallel chunk for the importance estimator (estimate). Per-shot full
// tableau + a final observable expectation -- heavy, so a small chunk for balance.
const EST_CHUNK: usize = 256;

// Per-chunk noise seed: decorrelate (base, chunk) through the splitmix finalizer
// so disjoint shot-chunks draw independent streams.
fn chunk_seed(base: u64, chunk: u64) -> u64 {
    let mut z = base ^ chunk.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

// One shot-chunk of the Pauli-frame engine: replay the instruction stream over
// `chunk_shots` shots (bit-packed, 64/word), writing records into `out` (length
// chunk_shots*num_meas, shot-major). Pure frame logic over its own buffers, so
// disjoint chunks run in parallel; `ref_bits` (noiseless reference) is read-only.
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
    let sw = (chunk_shots + 63) / 64;
    let mut fx = vec![0u64; n * sw];
    let mut fz = vec![0u64; n * sw];
    let mut noise = Rng::new(seed);
    let mut meas_planes: Vec<Vec<u64>> = Vec::with_capacity(num_meas);
    let mut mi = 0usize;

    for &(kind, x, y, z) in instrs {
        match kind {
            0 => {
                let (fa, fb) = ((y as usize) * sw, (z as usize) * sw);
                match x {
                    0 => {
                        for k in 0..sw {
                            let t = fx[fa + k];
                            fx[fa + k] = fz[fa + k];
                            fz[fa + k] = t;
                        }
                    }
                    1 | 2 => {
                        for k in 0..sw {
                            fz[fa + k] ^= fx[fa + k];
                        }
                    }
                    3 | 4 | 5 => {} // X/Y/Z: identity on the (sign-free) frame
                    6 => {
                        for k in 0..sw {
                            let fxa = fx[fa + k];
                            let fzb = fz[fb + k];
                            fx[fb + k] ^= fxa;
                            fz[fa + k] ^= fzb;
                        }
                    }
                    7 => {
                        for k in 0..sw {
                            let fxa = fx[fa + k];
                            let fxb = fx[fb + k];
                            fz[fa + k] ^= fxb;
                            fz[fb + k] ^= fxa;
                        }
                    }
                    8 => {
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
                // rare-error noise: see frame_sample's serial original for the math
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

                    let (word, bit) = (s >> 6, 1u64 << (s & 63));
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
        let (word, bit) = (s >> 6, s & 63);
        let base = s * num_meas;
        for (m, plane) in meas_planes.iter().enumerate() {
            out[base + m] = ((plane[word] >> bit) & 1) as u8;
        }
    }
}

// One shot-chunk of the per-shot tableau Monte-Carlo sampler (sample_batch's path,
// used when a measurement is random so the frame method can't apply). Each chunk
// owns a tableau (reset in place per shot) + its own coin/noise RNGs, so disjoint
// chunks run in parallel; records written shot-major into `out`. Shots here are
// fully independent -- no shared reference run -- so this scales near-linearly.
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
                    let thr = noise.next_f64() * total;
                    let mut acc = 0.0;
                    let mut pick = table.len() - 1;
                    for (i, (w, _)) in table.iter().enumerate() {
                        acc += w.abs();
                        if thr <= acc {
                            pick = i;
                            break;
                        }
                    }
                    for &(op, a, b) in &table[pick].1 {
                        t.apply_gate(op, a as usize, b as usize);
                    }
                }
                _ => {}
            }
        }
    }
}

// One shot-chunk of the quasiprobability importance estimator (Sampler.expect /
// Circuit.estimate). Per shot: run the circuit, sampling ONE branch per noise
// location ~ |weight|/gamma and multiplying the trajectory weight by
// sign(weight)*gamma; then evaluate <observable> on the final stabilizer state.
// Returns the partial sum of weight*<O> over the chunk (caller divides by shots).
// Branch op opcode 9 = reset; 0..8 = the usual gates. Unbiased for ANY channel.
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
                    let thr = noise.next_f64() * gamma;
                    let mut a = 0.0;
                    let mut pick = table.len() - 1;
                    for (i, (w, _)) in table.iter().enumerate() {
                        a += w.abs();
                        if thr <= a {
                            pick = i;
                            break;
                        }
                    }
                    let (w, ops) = &table[pick];
                    weight *= if *w >= 0.0 { gamma } else { -gamma };
                    for &(op, qa, qb) in ops {
                        if op == 9 {
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

// g = power of i when (x1,z1) * (x2,z2).
// Encoding I=(0,0) X=(1,0) Z=(0,1) Y=(1,1); e ∈ {-1,0,+1}:
//   P1=I -> 0
//   P1=X -> z2*(2*x2-1)   = +1 if P2=Y, -1 if P2=Z, else 0
//   P1=Z -> x2*(1-2*z2)   = +1 if P2=X, -1 if P2=Y, else 0
//   P1=Y -> z2 - x2       = +1 if P2=Z, -1 if P2=X, else 0
// Kept as the scalar reference that `word_g` (below) implements bit-parallel.
#[allow(dead_code)]
#[inline]
fn g(x1: bool, z1: bool, x2: bool, z2: bool) -> i32 {
    match (x1, z1) {
        (false, false) => 0,                                   // I
        (true, false) => (z2 as i32) * (2 * (x2 as i32) - 1),  // X
        (false, true) => (x2 as i32) * (1 - 2 * (z2 as i32)),  // Z
        (true, true) => (z2 as i32) - (x2 as i32),             // Y
    }
}

// word_g: Σ of g over the 64 Pauli lanes packed in one word, where lane k holds
// P1 = (xi,zi)[k] (first operand) and P2 = (xh,zh)[k] (second). This is the
// bit-parallel form of the per-qubit g() loop: each lane contributes +1/-1/0 and
// we popcount the two masks. Encoding P=(x,z): I=00 X=10 Z=01 Y=11.
//   +1 lanes: (X,Y) (Z,X) (Y,Z)        -1 lanes: (X,Z) (Z,Y) (Y,X)
// At every lane (x1,z1) is exactly one of I/X/Z/Y, so the three +terms (and the
// three -terms) live on disjoint lanes -> OR-then-popcount counts each once, and
// a +term and -term never share a lane. Lanes past nq are all-zero => I => 0, so
// the unused tail of the last word is harmless and needs no masking.
#[inline]
fn word_g(xi: u64, zi: u64, xh: u64, zh: u64) -> i32 {
    let plus = (xi & !zi & xh & zh) | (!xi & zi & xh & !zh) | (xi & zi & !xh & zh);
    let minus = (xi & !zi & !xh & zh) | (!xi & zi & xh & zh) | (xi & zi & xh & !zh);
    plus.count_ones() as i32 - minus.count_ones() as i32
}

// NOTE: in the tableu we will start with |00> in all instances because that makes dealing with ZZ easy.

// CNOT-Hadamard-Phase tableau (Aaronson-Gottesman)
//   0..N    destabilizers
//   N..2N   stabilizers
//   2N      scratch (for measurement stuff)
#[pyclass]
#[derive(Clone)]
pub struct RowTableau {
    nq: usize,
    // ceil(n/64): u64 words packed per row
    w: usize,
    // row r qubit j ->
    // word (j>>6) [from j//64] and
    //  bit (j&63) [from j% 64]
    xs: Vec<u64>,
    zs: Vec<u64>,
    // per-row phase: 0 => +, 1 => -
    signs: Vec<u8>,
    // measurement outcomes, in call order
    record: Vec<bool>,
    rng: Rng,
}

/*
Each row is actually
- X[stuff]
- Z[stuff]
- r[stuff]

but in fact gets packed to a single row as [x1...xn, z1...zn, r1...rn].
An example for |00> but with Vec<u8> packing would be

       x         z         r   Pauli
row 0  00000001  00000000  +   X₀      ← destab
row 1  00000010  00000000  +   X₁      ← destab
row 2  00000000  00000001  +   Z₀      ← stab  ┐ stabilized by +Z₀, +Z₁
row 3  00000000  00000010  +   Z₁      ← stab  ┘ ⇒ |00⟩
row 4  00000000  00000000  +   I

But the plus and minus here would be stored as bits.
*/
impl RowTableau {
    #[inline]
    // I will not apologise for doing unhinged things
    fn get_x(&self, i: usize, j: usize) -> bool {
        // == 1 is to get a bool out
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

#[pymethods]
impl RowTableau {
    #[new]
    #[pyo3(signature = (n, seed=None))]
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

    #[getter]
    fn n(&self) -> usize {
        self.nq
    }

    // H: swap x<->z; sign ^= x & z
    fn h(&mut self, a: usize) {
        let wa = a >> 6;
        let sh = a & 63;
        let m = 1u64 << sh;
        for i in 0..2 * self.nq {
            let b = i * self.w + wa;
            let xb = (self.xs[b] >> sh) & 1;
            let zb = (self.zs[b] >> sh) & 1;
            self.signs[i] ^= (xb & zb) as u8;
            self.xs[b] = (self.xs[b] & !m) | (zb << sh);
            self.zs[b] = (self.zs[b] & !m) | (xb << sh);
        }
    }

    // S: z ^= x; sign ^= x & z
    fn s(&mut self, a: usize) {
        let wa = a >> 6;
        let sh = a & 63;
        for i in 0..2 * self.nq {
            let b = i * self.w + wa;
            let xb = (self.xs[b] >> sh) & 1;
            let zb = (self.zs[b] >> sh) & 1;
            self.signs[i] ^= (xb & zb) as u8;
            self.zs[b] ^= xb << sh;
        }
    }

    // S-dagger: z ^= x; sign ^= x & !z
    fn s_dag(&mut self, a: usize) {
        let wa = a >> 6;
        let sh = a & 63;
        for i in 0..2 * self.nq {
            let b = i * self.w + wa;
            let xb = (self.xs[b] >> sh) & 1;
            let zb = (self.zs[b] >> sh) & 1;
            self.signs[i] ^= (xb & (zb ^ 1)) as u8;
            self.zs[b] ^= xb << sh;
        }
    }

    // X: sign ^= z
    fn x(&mut self, a: usize) {
        let wa = a >> 6;
        let sh = a & 63;
        for i in 0..2 * self.nq {
            let zb = (self.zs[i * self.w + wa] >> sh) & 1;
            self.signs[i] ^= zb as u8;
        }
    }

    // Z: sign ^= x
    fn z(&mut self, a: usize) {
        let wa = a >> 6;
        let sh = a & 63;
        for i in 0..2 * self.nq {
            let xb = (self.xs[i * self.w + wa] >> sh) & 1;
            self.signs[i] ^= xb as u8;
        }
    }

    // Y: sign ^= x ^ z
    fn y(&mut self, a: usize) {
        let wa = a >> 6;
        let sh = a & 63;
        for i in 0..2 * self.nq {
            let b = i * self.w + wa;
            let xb = (self.xs[b] >> sh) & 1;
            let zb = (self.zs[b] >> sh) & 1;
            self.signs[i] ^= (xb ^ zb) as u8;
        }
    }

    // CNOT a->b: x_b ^= x_a, z_a ^= z_b; sign ^= x_a & z_b & (x_b ^ z_a ^ 1)
    fn cx(&mut self, a: usize, b: usize) {
        let wa = a >> 6;
        let sa = a & 63;
        let wb = b >> 6;
        let sb = b & 63;
        for i in 0..2 * self.nq {
            let ia = i * self.w + wa;
            let ib = i * self.w + wb;
            let xa = (self.xs[ia] >> sa) & 1;
            let za = (self.zs[ia] >> sa) & 1;
            let xtb = (self.xs[ib] >> sb) & 1;
            let ztb = (self.zs[ib] >> sb) & 1;
            self.signs[i] ^= (xa & ztb & (xtb ^ za ^ 1)) as u8;
            self.xs[ib] ^= xa << sb;
            self.zs[ia] ^= ztb << sa;
        }
    }

    // CZ (symmetric): za ^= xb; zb ^= xa; sign ^= xa & xb & (za ^ zb).
    // Direct single pass over rows. Composing H_b·CX(a,b)·H_b gives this sign
    // term (the za,zb in it are the originals, read before the z-updates).
    fn cz(&mut self, a: usize, b: usize) {
        let wa = a >> 6;
        let sa = a & 63;
        let wb = b >> 6;
        let sb = b & 63;
        for i in 0..2 * self.nq {
            let ia = i * self.w + wa;
            let ib = i * self.w + wb;
            let xa = (self.xs[ia] >> sa) & 1;
            let za = (self.zs[ia] >> sa) & 1;
            let xb = (self.xs[ib] >> sb) & 1;
            let zb = (self.zs[ib] >> sb) & 1;
            self.signs[i] ^= (xa & xb & (za ^ zb)) as u8;
            self.zs[ia] ^= xb << sa;
            self.zs[ib] ^= xa << sb;
        }
    }

    fn swap(&mut self, a: usize, b: usize) {
        self.cx(a, b);
        self.cx(b, a);
        self.cx(a, b);
    }

    #[pyo3(signature = (a, force=None))]
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

    #[getter]
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

    #[pyo3(signature = (px, pz, force=None))]
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

    fn copy(&self) -> RowTableau {
        self.clone()
    }

    fn __repr__(&self) -> String {
        format!("RowTableau(n={})", self.nq)
    }
}

// ---------------------------------------------------------------------------
// ColTableau: column-major (qubit-major) bit planes for word-parallel gates,
// transposed to the row-major engine (the `RowTableau` above, reused as `inner`)
// for measurement. `layout` says which side is authoritative; we transpose
// lazily, only when the op kind switches. A gate touches O(rows/64) words per
// plane -- signs included -- instead of O(rows) scalar row touches: no cache
// cliff, auto-vectorizable. Measurement delegates to the proven row-major path,
// so its lead is preserved verbatim. Transpose is the naive O(rows*nq) form for
// now (amortized: one per measurement round); 64x64 block transpose is the
// later optimization.
// ---------------------------------------------------------------------------

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
    // make the row-major engine authoritative (measurement reads it).
    fn to_row(&mut self) {
        if self.layout == Layout::Row {
            return;
        }
        let (w, rw) = (self.w, self.rw);
        for v in self.inner.xs.iter_mut() {
            *v = 0;
        }
        for v in self.inner.zs.iter_mut() {
            *v = 0;
        }
        for j in 0..self.nq {
            let cbase = j * rw;
            let jw = j >> 6;
            let jbit = 1u64 << (j & 63);
            for r in 0..self.rows {
                let cw = cbase + (r >> 6);
                let rb = r & 63;
                if (self.xc[cw] >> rb) & 1 == 1 {
                    self.inner.xs[r * w + jw] |= jbit;
                }
                if (self.zc[cw] >> rb) & 1 == 1 {
                    self.inner.zs[r * w + jw] |= jbit;
                }
            }
        }
        for r in 0..self.rows {
            self.inner.signs[r] = ((self.signc[r >> 6] >> (r & 63)) & 1) as u8;
        }
        self.layout = Layout::Row;
    }

    // make the column-major planes authoritative (gates touch them).
    fn to_col(&mut self) {
        if self.layout == Layout::Col {
            return;
        }
        let (w, rw) = (self.w, self.rw);
        for v in self.xc.iter_mut() {
            *v = 0;
        }
        for v in self.zc.iter_mut() {
            *v = 0;
        }
        for v in self.signc.iter_mut() {
            *v = 0;
        }
        for r in 0..self.rows {
            let rbase = r * w;
            let rword = r >> 6;
            let rbit = 1u64 << (r & 63);
            for j in 0..self.nq {
                let rwd = rbase + (j >> 6);
                let jb = j & 63;
                if (self.inner.xs[rwd] >> jb) & 1 == 1 {
                    self.xc[j * rw + rword] |= rbit;
                }
                if (self.inner.zs[rwd] >> jb) & 1 == 1 {
                    self.zc[j * rw + rword] |= rbit;
                }
            }
            if self.inner.signs[r] != 0 {
                self.signc[rword] |= rbit;
            }
        }
        self.layout = Layout::Col;
    }

    // The one place col-major gate logic lives. Raw whole-plane op by opcode
    // (0=H 1=S 2=S_DAG 3=X 4=Y 5=Z 6=CX 7=CZ 8=SWAP); b unused for 1-qubit.
    // Caller must already be in Col layout (gates/run/apply_gate ensure it).
    // #[inline] so the dispatch folds back into run()'s hot loop (single source,
    // no call overhead per gate).
    #[inline]
    fn gate(&mut self, op: u8, a: usize, b: usize) {
        let rw = self.rw;
        let base = a * rw;
        match op {
            // H: swap x<->z; sign ^= x & z
            0 => {
                for k in 0..rw {
                    let xa = self.xc[base + k];
                    let za = self.zc[base + k];
                    self.signc[k] ^= xa & za;
                    self.xc[base + k] = za;
                    self.zc[base + k] = xa;
                }
            }
            // S: z ^= x; sign ^= x & z (z read before update)
            1 => {
                for k in 0..rw {
                    let xa = self.xc[base + k];
                    let za = self.zc[base + k];
                    self.signc[k] ^= xa & za;
                    self.zc[base + k] = za ^ xa;
                }
            }
            // S-dagger: z ^= x; sign ^= x & !z
            2 => {
                for k in 0..rw {
                    let xa = self.xc[base + k];
                    let za = self.zc[base + k];
                    self.signc[k] ^= xa & !za;
                    self.zc[base + k] = za ^ xa;
                }
            }
            // X: sign ^= z
            3 => {
                for k in 0..rw {
                    self.signc[k] ^= self.zc[base + k];
                }
            }
            // Y: sign ^= x ^ z
            4 => {
                for k in 0..rw {
                    self.signc[k] ^= self.xc[base + k] ^ self.zc[base + k];
                }
            }
            // Z: sign ^= x
            5 => {
                for k in 0..rw {
                    self.signc[k] ^= self.xc[base + k];
                }
            }
            // CNOT a->b: x_b ^= x_a; z_a ^= z_b; sign ^= x_a & z_b & (x_b ^ z_a ^ 1)
            6 => {
                let rb = b * rw;
                for k in 0..rw {
                    let xa = self.xc[base + k];
                    let za = self.zc[base + k];
                    let xb = self.xc[rb + k];
                    let zb = self.zc[rb + k];
                    self.signc[k] ^= xa & zb & (xb ^ za ^ !0u64);
                    self.xc[rb + k] = xb ^ xa;
                    self.zc[base + k] = za ^ zb;
                }
            }
            // CZ (symmetric): z_a ^= x_b; z_b ^= x_a; sign ^= x_a & x_b & (z_a ^ z_b)
            7 => {
                let rb = b * rw;
                for k in 0..rw {
                    let xa = self.xc[base + k];
                    let za = self.zc[base + k];
                    let xb = self.xc[rb + k];
                    let zb = self.zc[rb + k];
                    self.signc[k] ^= xa & xb & (za ^ zb);
                    self.zc[base + k] = za ^ xb;
                    self.zc[rb + k] = zb ^ xa;
                }
            }
            8 => {
                self.gate(6, a, b);
                self.gate(6, b, a);
                self.gate(6, a, b);
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
        ColTableau {
            nq: n,
            rows,
            w: (n + 63) / 64,
            rw,
            xc: vec![0u64; n * rw],
            zc: vec![0u64; n * rw],
            signc: vec![0u64; rw],
            // inner carries the |0...0> init; first gate transposes it to col
            layout: Layout::Row,
            inner: RowTableau::new(n, seed),
        }
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

    // Apply a compiled (opcode, a, b) gate stream in one call: one to_col for the
    // whole batch -> no per-gate Python dispatch. Gate bodies are INLINED here
    // (not via gate()) so this hot batched loop stays fast -- gate() is too big to
    // inline, and calling it per op costs ~1.7x at large n. The pymethods and
    // apply_gate still share gate() for DRY; only this hot loop duplicates it.
    fn run(&mut self, ops: Vec<(u8, u32, u32)>) {
        self.to_col();
        let rw = self.rw;
        for (op, a, b) in ops {
            let base = (a as usize) * rw;
            match op {
                0 => {
                    for k in 0..rw {
                        let xa = self.xc[base + k];
                        let za = self.zc[base + k];
                        self.signc[k] ^= xa & za;
                        self.xc[base + k] = za;
                        self.zc[base + k] = xa;
                    }
                }
                1 => {
                    for k in 0..rw {
                        let xa = self.xc[base + k];
                        let za = self.zc[base + k];
                        self.signc[k] ^= xa & za;
                        self.zc[base + k] = za ^ xa;
                    }
                }
                2 => {
                    for k in 0..rw {
                        let xa = self.xc[base + k];
                        let za = self.zc[base + k];
                        self.signc[k] ^= xa & !za;
                        self.zc[base + k] = za ^ xa;
                    }
                }
                3 => {
                    for k in 0..rw {
                        self.signc[k] ^= self.zc[base + k];
                    }
                }
                4 => {
                    for k in 0..rw {
                        self.signc[k] ^= self.xc[base + k] ^ self.zc[base + k];
                    }
                }
                5 => {
                    for k in 0..rw {
                        self.signc[k] ^= self.xc[base + k];
                    }
                }
                6 => {
                    let rb = (b as usize) * rw;
                    for k in 0..rw {
                        let xa = self.xc[base + k];
                        let za = self.zc[base + k];
                        let xb = self.xc[rb + k];
                        let zb = self.zc[rb + k];
                        self.signc[k] ^= xa & zb & (xb ^ za ^ !0u64);
                        self.xc[rb + k] = xb ^ xa;
                        self.zc[base + k] = za ^ zb;
                    }
                }
                7 => {
                    let rb = (b as usize) * rw;
                    for k in 0..rw {
                        let xa = self.xc[base + k];
                        let za = self.zc[base + k];
                        let xb = self.xc[rb + k];
                        let zb = self.zc[rb + k];
                        self.signc[k] ^= xa & xb & (za ^ zb);
                        self.zc[base + k] = za ^ xb;
                        self.zc[rb + k] = zb ^ xa;
                    }
                }
                8 => self.swap(a as usize, b as usize),
                _ => {}
            }
        }
    }

    // Batched Pauli-noise trajectory sampler (the fast path for Circuit.sample).
    // instrs: (kind, x, y, z) with
    //   kind 0 = gate(opcode=x, a=y, b=z)
    //   kind 1 = measure(sub=x: 0=M 1=MR 2=R, qubit=y) -- M/MR push a record bit
    //   kind 2 = noise(branch_table=x); pick one branch ~ |weight|, apply its ops
    // branches[i] = [(weight, [(opcode,a,b), ...]), ...] (precompiled in Python).
    // One reused tableau, reset in place per shot; no per-gate Python dispatch.
    // Returns (flat shots*num_meas bytes, num_meas). Non-Pauli / unknown ops never
    // reach here (Python compiler falls back to its loop), so this stays Pauli-only.
    fn sample_batch(
        &self,
        instrs: Vec<(u8, u32, u32, u32)>,
        branches: Vec<Vec<(f64, Vec<(u8, u32, u32)>)>>,
        shots: usize,
        seed: u64,
    ) -> (Vec<u8>, usize) {
        // Parallel over fixed-size shot chunks (BATCH_CHUNK), like frame_sample:
        // each chunk owns a tableau + deterministic per-chunk coin/noise RNGs, so
        // results are reproducible regardless of core count. No shared reference
        // run here (shots are fully independent) -> near-linear scaling. Returns a
        // flat shots*num_meas byte buffer (Python views it as a uint8 array).
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

    // Noiseless reference run for the frame sampler: returns the deterministic
    // measurement bits, or None if ANY measurement is random (caller then uses the
    // per-shot sample_batch -- a genuine coin the frame method can't model). This
    // is CIRCUIT-ONLY (seed-independent: a deterministic outcome doesn't flip the
    // coin), so CompiledSampler computes it ONCE and reuses it across sample()
    // calls -- amortizing this serial pass over a whole LER sweep.
    fn frame_reference(&self, instrs: Vec<(u8, u32, u32, u32)>) -> Option<Vec<bool>> {
        // Run on the COLUMN-MAJOR engine: gate replay is ~20x faster than the old
        // row-major RowTableau path (the cache cliff we fixed for interactive
        // gates). Only the measurements transpose to the row engine (`inner`).
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

    // Parallel Pauli-frame engine over `shots`, given a precomputed `ref_bits`
    // (from frame_reference). Propagates bit-packed frames (64 shots/word,
    // sign-free) + rare-error noise, recording ref_bit XOR frame_x[q]. Parallel
    // over fixed-size shot chunks: rayon adapts to the core count; the chunk size
    // is fixed (FRAME_CHUNK) so the result is reproducible regardless of cores.
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

    // Quasiprobability importance estimator for <observable> under general noise.
    // instrs: 0=gate(op,a,b), 2=noise(table=x). branches[i] = [(SIGNED weight,
    // [(op,a,b)..]) ..] (op 9 = reset). Parallel over fixed-size shot chunks (rayon;
    // reproducible regardless of core count). Unbiased for ANY channel -- this is
    // the differentiating coherent/amplitude path, off the Python/GIL loop.
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
