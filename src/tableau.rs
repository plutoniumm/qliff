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
    #[inline]
    fn next_f64(&mut self) -> f64 {
        // 53-bit mantissa in [0, 1)
        (self.next_u64() >> 11) as f64 / ((1u64 << 53) as f64)
    }
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
    // Returns shots x record-length 0/1. Non-Pauli / unknown ops never reach here
    // (Python compiler falls back to its loop), so this stays Pauli-only.
    fn sample_batch(
        &mut self,
        instrs: Vec<(u8, u32, u32, u32)>,
        branches: Vec<Vec<(f64, Vec<(u8, u32, u32)>)>>,
        shots: usize,
        seed: u64,
    ) -> Vec<Vec<i64>> {
        // i64 (not u8) so PyO3 yields list[list[int]], not list[bytes].
        // measurement coin and noise draws on independent streams
        self.inner.rng = Rng::new(seed);
        let mut noise = Rng::new(seed.wrapping_add(0x9E37_79B9_7F4A_7C15));
        let mut out = Vec::with_capacity(shots);

        for _ in 0..shots {
            self.reset_to_zero();
            self.inner.clear_record();
            let mut rec = Vec::new();

            for &(kind, x, y, z) in &instrs {
                match kind {
                    0 => self.apply_gate(x as u8, y as usize, z as usize),
                    1 => match x {
                        0 => rec.push(self.measure(y as usize, None) as i64),
                        1 => rec.push(self.mr(y as usize) as i64),
                        _ => self.reset(y as usize),
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
                            self.apply_gate(op, a as usize, b as usize);
                        }
                    }
                    _ => {}
                }
            }
            out.push(rec);
        }
        out
    }

    // Pauli-frame batch sampler -- the fast path when every measurement is
    // DETERMINISTIC in the noiseless reference. Returns None (caller falls back
    // to sample_batch) if any measurement is random: a genuine per-shot coin the
    // frame method doesn't model. Otherwise: run the reference once (fixes the
    // outcomes), then propagate bit-packed Pauli frames over `shots` shots (64
    // shots / u64 word, sign-free), sampling noise as frame-bit flips; a
    // measurement records ref_bit XOR frame_x[q] for all shots at once. The
    // per-shot tableau re-run is gone -> the Wall-2 fix.
    fn frame_sample(
        &self,
        instrs: Vec<(u8, u32, u32, u32)>,
        branches: Vec<Vec<(f64, Vec<(u8, u32, u32)>)>>,
        shots: usize,
        seed: u64,
    ) -> Option<Vec<Vec<i64>>> {
        let n = self.nq;

        // --- reference run (noiseless): record ref bits, bail if any is random ---
        let mut refsim = RowTableau::new(n, Some(seed));
        let mut ref_bits: Vec<bool> = Vec::new();
        for &(kind, x, y, z) in &instrs {
            match kind {
                0 => {
                    let (a, b) = (y as usize, z as usize);
                    match x {
                        0 => refsim.h(a),
                        1 => refsim.s(a),
                        2 => refsim.s_dag(a),
                        3 => refsim.x(a),
                        4 => refsim.y(a),
                        5 => refsim.z(a),
                        6 => refsim.cx(a, b),
                        7 => refsim.cz(a, b),
                        8 => refsim.swap(a, b),
                        _ => {}
                    }
                }
                1 => {
                    let a = y as usize;
                    if x == 2 {
                        refsim.reset(a); // R: no record, randomness discarded
                    } else {
                        let (bit, random) = refsim.do_measure(a, None);
                        if random {
                            return None; // fall back to sample_batch
                        }
                        ref_bits.push(bit);
                        if x == 1 && bit {
                            refsim.x(a); // MR: reset to |0>
                        }
                    }
                }
                _ => {} // kind 2 = noise: skipped in the reference
            }
        }

        // --- frame engine: bit-packed over shots (64 shots per u64 word) ---
        let sw = (shots + 63) / 64;
        let mut fx = vec![0u64; n * sw];
        let mut fz = vec![0u64; n * sw];
        let mut noise = Rng::new(seed.wrapping_add(0x9E37_79B9_7F4A_7C15));
        let mut meas_planes: Vec<Vec<u64>> = Vec::new();
        let mut mi = 0usize;

        for &(kind, x, y, z) in &instrs {
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
                    let table = &branches[x as usize];
                    let total: f64 = table.iter().map(|(w, _)| w.abs()).sum();
                    for s in 0..shots {
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
                        let (word, bit) = (s >> 6, 1u64 << (s & 63));
                        for &(op, qa, _qb) in &table[pick].1 {
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
                    }
                }
                _ => {}
            }
        }

        // transpose measurement planes (num_meas x shots) -> shots x num_meas
        let mut out = Vec::with_capacity(shots);
        for s in 0..shots {
            let (word, bit) = (s >> 6, s & 63);
            let mut rec = Vec::with_capacity(meas_planes.len());
            for plane in &meas_planes {
                rec.push(((plane[word] >> bit) & 1) as i64);
            }
            out.push(rec);
        }

        Some(out)
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
        self.inner.expectation(px, pz)
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
