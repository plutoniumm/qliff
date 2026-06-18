use pyo3::prelude::*;
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
}

// g = power of i when (x1,z1) * (x2,z2).
// Encoding I=(0,0) X=(1,0) Z=(0,1) Y=(1,1); e ∈ {-1,0,+1}:
//   P1=I -> 0
//   P1=X -> z2*(2*x2-1)   = +1 if P2=Y, -1 if P2=Z, else 0
//   P1=Z -> x2*(1-2*z2)   = +1 if P2=X, -1 if P2=Y, else 0
//   P1=Y -> z2 - x2       = +1 if P2=Z, -1 if P2=X, else 0
#[inline]
fn g(x1: bool, z1: bool, x2: bool, z2: bool) -> i32 {
    match (x1, z1) {
        (false, false) => 0,                                   // I
        (true, false) => (z2 as i32) * (2 * (x2 as i32) - 1),  // X
        (false, true) => (x2 as i32) * (1 - 2 * (z2 as i32)),  // Z
        (true, true) => (z2 as i32) - (x2 as i32),             // Y
    }
}

// NOTE: in the tableu we will start with |00> in all instances because that makes dealing with ZZ easy.

// CNOT-Hadamard-Phase tableau (Aaronson-Gottesman)
//   0..N    destabilizers
//   N..2N   stabilizers
//   2N      scratch (for measurement stuff)
#[pyclass]
#[derive(Clone)]
pub struct Tableau {
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

but in fact gets packed to a single row as [x1...xn, z1...zn, r1...rn]. An example for |00> but with Vec<u8> packing would be

       x         z         r   Pauli
row 0  00000001  00000000  +   X₀      ← destab
row 1  00000010  00000000  +   X₁      ← destab
row 2  00000000  00000001  +   Z₀      ← stab  ┐ stabilized by +Z₀, +Z₁
row 3  00000000  00000010  +   Z₁      ← stab  ┘ ⇒ |00⟩
row 4  00000000  00000000  +   I

But the plus and minus here would be stored as bits.
*/
impl Tableau {
    #[inline]
    // I will not apologise for doing unhinged things
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

    /*
    OLD SHIT COMMENT
    // rowsum(h,i): row_h <- row_i . row_h  (Pauli-group product)
    //   e = 2*r_i + 2*r_h + Σ_j g(row_i[j], row_h[j])    // total phase is i^e
    //   r_h <- (e mod 4 == 2) ? 1 : 0                     // e is always 0 or 2 here
    //   x_h ^= x_i ;  z_h ^= z_i
    */

    // row h <- row i * row h
    fn rowsum(&mut self, h: usize, i: usize) {
        let mut sum: i64 = 2 * (self.signs[h] as i64) + 2 * (self.signs[i] as i64);
        for j in 0..self.nq {
            sum += g(
                self.get_x(i, j),
                self.get_z(i, j),
                self.get_x(h, j),
                self.get_z(h, j)
            ) as i64;
        }

        self.signs[h] =
            if sum.rem_euclid(4) == 0 {
                 0
            } else {
                1
            };

        for k in 0..self.w {
            let xv = self.xs[i * self.w + k];
            let zv = self.zs[i * self.w + k];
            self.xs[h * self.w + k] ^= xv;
            self.zs[h * self.w + k] ^= zv;
        }
    }

    // measure Z_a  (force pins the random coin):
    //   ∃ stab row p in N..2N with x_{p,a}=1  (Z_a anticommutes -> random):
    //     rowsum(row, p) for every other row hitting a   // leave p the lone anticommuter
    //     destab_p <- stab_p ;  stab_p <- (-1)^coin Z_a ;  return coin
    //   else  (Z_a commutes with all -> deterministic):
    //     scratch <- Π stab_k over destabs k that hit a ;  return sign(scratch)
    fn do_measure(&mut self, a: usize, force: Option<bool>) -> bool {
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
                bit
            }
            None => {
                let sc = 2 * n;
                self.zero_row(sc);
                for ii in 0..n {
                    if self.get_x(ii, a) {
                        self.rowsum(sc, ii + n);
                    }
                }
                self.signs[sc] != 0
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
impl Tableau {
    #[new]
    #[pyo3(signature = (n, seed=None))]
    fn new(n: usize, seed: Option<u64>) -> Self {
        let w = (n + 63) / 64;
        let rows = 2 * n + 1;
        // default seed: wall-clock nanos XOR a per-process counter (unique per Tableau)
        let seed = seed.unwrap_or_else(|| {
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_nanos() as u64)
                .unwrap_or(0x1234_5678);
            let c = COUNTER.fetch_add(1, Ordering::Relaxed);
            nanos ^ c.wrapping_mul(0x9E37_79B9_7F4A_7C15)
        });
        let mut t = Tableau {
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

    // CZ = H on b, CX(a,b), H on b
    fn cz(&mut self, a: usize, b: usize) {
        self.h(b);
        self.cx(a, b);
        self.h(b);
    }

    // SWAP = CX(a,b), CX(b,a), CX(a,b)
    fn swap(&mut self, a: usize, b: usize) {
        self.cx(a, b);
        self.cx(b, a);
        self.cx(a, b);
    }

    // measure qubit a (force pins the coin); appends the outcome to the record
    #[pyo3(signature = (a, force=None))]
    fn measure(&mut self, a: usize, force: Option<bool>) -> bool {
        let o = self.do_measure(a, force);
        self.record.push(o);
        o
    }

    // measure, then reset qubit a to |0>
    fn mr(&mut self, a: usize) -> bool {
        let o = self.do_measure(a, None);
        self.record.push(o);
        if o {
            self.x(a);
        }
        o
    }

    // collapse qubit a and force it to |0>
    fn reset(&mut self, a: usize) {
        if self.do_measure(a, None) {
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
    fn expectation(&self, px: Vec<u8>, pz: Vec<u8>) -> i8 {
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
                let mut sum: i64 = 2 * ssign + 2 * (self.signs[st] as i64);
                for j in 0..n {
                    let x2 = (sx[j >> 6] >> (j & 63)) & 1 == 1;
                    let z2 = (sz[j >> 6] >> (j & 63)) & 1 == 1;
                    sum += g(self.get_x(st, j), self.get_z(st, j), x2, z2) as i64;
                }
                ssign = if sum.rem_euclid(4) == 0 { 0 } else { 1 };
                for w in 0..self.w {
                    sx[w] ^= self.xs[st * self.w + w];
                    sz[w] ^= self.zs[st * self.w + w];
                }
            }
        }
        if ssign == 0 {
            1
        } else {
            -1
        }
    }

    // measure an arbitrary Pauli (px,pz) like do_measure; returns (outcome, was_random)
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

    fn copy(&self) -> Tableau {
        self.clone()
    }

    fn __repr__(&self) -> String {
        format!("Tableau(n={})", self.nq)
    }
}
