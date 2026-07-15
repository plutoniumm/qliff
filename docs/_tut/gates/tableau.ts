// A faithful, in-browser Clifford "tableau" core for the gates explainer. We
// model a SINGLE Pauli operator (one tableau row) on n qubits and conjugate it
// by gates in the Heisenberg picture:  P -> U P U^dagger.  That is how a
// stabilizer simulator updates a state -- it never touches 2^n amplitudes, only
// these (x, z, sign) bits. Every demo number on the page is produced by these
// functions so the reader can reproduce it by clicking.
//
// The bit rules below are copied verbatim from qliff's Rust core
// (src/tableau.rs, fns h/s/s_dag/x/z/y/cx/cz). The two invariants to respect:
//   1. each Pauli on a qubit is two bits (x, z) + one global sign bit,
//   2. compute the sign term from the ORIGINAL bits, THEN update x/z.

// sign: 0 = "+", 1 = "-" (a Pauli row also carries i^? phase in a full sim, but
// for products of {I,X,Y,Z} on disjoint single qubits a +/- sign is faithful and
// is what the page reasons about).
export interface Pauli {
  x: boolean[];
  z: boolean[];
  sign: 0 | 1;
}

// ----- construction --------------------------------------------------------

// The all-identity Pauli with a + sign on n qubits.
export function identity(n: number): Pauli {
  return { x: new Array(n).fill(false), z: new Array(n).fill(false), sign: 0 };
}

export function clone(p: Pauli): Pauli {
  return { x: [...p.x], z: [...p.z], sign: p.sign };
}

// A single-letter Pauli on one qubit of an n-qubit register.
export function single(n: number, q: number, letter: "I" | "X" | "Y" | "Z"): Pauli {
  const p = identity(n);
  if (letter === "X" || letter === "Y") {
    p.x[q] = true;
  }
  if (letter === "Z" || letter === "Y") {
    p.z[q] = true;
  }

  return p;
}

// ----- labelling -----------------------------------------------------------

export function pauliChar(x: boolean, z: boolean): "I" | "X" | "Y" | "Z" {
  if (!x && !z) {
    return "I";
  }
  if (x && !z) {
    return "X";
  }
  if (!x && z) {
    return "Z";
  }

  return "Y";
}

const SUB = "₀₁₂₃₄₅₆₇₈₉";
function sub(i: number): string {
  return String(i)
    .split("")
    .map((d) => SUB[Number(d)])
    .join("");
}

// "+X₀X₁", "-Z₁", "+I" (identity). Subscripts name the qubit index.
export function pauliString(p: Pauli): string {
  const factors: string[] = [];
  for (let i = 0; i < p.x.length; i += 1) {
    const c = pauliChar(p.x[i], p.z[i]);
    if (c !== "I") {
      factors.push(`${c}${sub(i)}`);
    }
  }
  const body = factors.length === 0 ? "I" : factors.join("");

  return `${p.sign === 0 ? "+" : "−"}${body}`;
}

// The ket a single-qubit Pauli stabilizes (eigenvalue +1 of that signed Pauli):
//   +Z -> |0>,  -Z -> |1>,  +X -> |+>,  -X -> |->,  +Y -> |+i>,  -Y -> |-i>.
// Returns "" for the identity / multi-qubit operators (no single-qubit label).
export function stateLabel(p: Pauli): string {
  // count non-identity factors
  let only = -1;
  let nontrivial = 0;
  for (let i = 0; i < p.x.length; i += 1) {
    if (p.x[i] || p.z[i]) {
      nontrivial += 1;
      only = i;
    }
  }
  if (nontrivial !== 1) {
    return "";
  }
  const c = pauliChar(p.x[only], p.z[only]);
  const plus = p.sign === 0;
  if (c === "Z") {
    return plus ? "|0⟩" : "|1⟩";
  }
  if (c === "X") {
    return plus ? "|+⟩" : "|−⟩";
  }
  if (c === "Y") {
    return plus ? "|+i⟩" : "|−i⟩";
  }

  return "";
}

// ----- single-qubit gates (in place) ---------------------------------------
// Order in every gate: read the original x,z; update sign from them; THEN
// update x,z, matching qliff.

// H(a): sign ^= x_a & z_a; swap x_a <-> z_a.   (X<->Z, Y->-Y)
export function applyH(p: Pauli, a: number): void {
  const xa = p.x[a];
  const za = p.z[a];
  p.sign = (p.sign ^ (xa && za ? 1 : 0)) as 0 | 1;
  p.x[a] = za;
  p.z[a] = xa;
}

// S(a): sign ^= x_a & z_a; z_a ^= x_a.   (X->Y, Z->Z)
export function applyS(p: Pauli, a: number): void {
  const xa = p.x[a];
  const za = p.z[a];
  p.sign = (p.sign ^ (xa && za ? 1 : 0)) as 0 | 1;
  p.z[a] = za !== xa;
}

// S-dagger(a): sign ^= x_a & !z_a; z_a ^= x_a.   (X->-Y, Z->Z)
export function applySdg(p: Pauli, a: number): void {
  const xa = p.x[a];
  const za = p.z[a];
  p.sign = (p.sign ^ (xa && !za ? 1 : 0)) as 0 | 1;
  p.z[a] = za !== xa;
}

// X(a): sign ^= z_a.   (anticommutes with Z, Y)
export function applyX(p: Pauli, a: number): void {
  p.sign = (p.sign ^ (p.z[a] ? 1 : 0)) as 0 | 1;
}

// Z(a): sign ^= x_a.   (anticommutes with X, Y)
export function applyZ(p: Pauli, a: number): void {
  p.sign = (p.sign ^ (p.x[a] ? 1 : 0)) as 0 | 1;
}

// Y(a): sign ^= x_a ^ z_a.   (anticommutes with X and Z)
export function applyY(p: Pauli, a: number): void {
  p.sign = (p.sign ^ (p.x[a] !== p.z[a] ? 1 : 0)) as 0 | 1;
}

// ----- two-qubit gates (in place) ------------------------------------------

// CX(control = a, target = b). qliff rule (read originals, update sign, then xz):
//   sign ^= x_a & z_b & (x_b ^ z_a ^ 1)
//   x_b  ^= x_a    // X on control copies onto target  (X forward)
//   z_a  ^= z_b    // Z on target copies back onto control (Z backward)
export function applyCX(p: Pauli, a: number, b: number): void {
  const xa = p.x[a];
  const za = p.z[a];
  const xb = p.x[b];
  const zb = p.z[b];
  // (x_b ^ z_a ^ 1) is true iff an EVEN number of {x_b, z_a} are set.
  const term = xa && zb && xb === za;
  p.sign = (p.sign ^ (term ? 1 : 0)) as 0 | 1;
  p.x[b] = xb !== xa;
  p.z[a] = za !== zb;
}

// CZ(a, b) -- symmetric. qliff rule:
//   sign ^= x_a & x_b & (z_a ^ z_b)
//   z_a ^= x_b
//   z_b ^= x_a
export function applyCZ(p: Pauli, a: number, b: number): void {
  const xa = p.x[a];
  const za = p.z[a];
  const xb = p.x[b];
  const zb = p.z[b];
  const term = xa && xb && za !== zb;
  p.sign = (p.sign ^ (term ? 1 : 0)) as 0 | 1;
  p.z[a] = za !== xb;
  p.z[b] = zb !== xa;
}

// SWAP = CX(a,b) . CX(b,a) . CX(a,b).
export function applySwap(p: Pauli, a: number, b: number): void {
  applyCX(p, a, b);
  applyCX(p, b, a);
  applyCX(p, a, b);
}

// ----- pure variants (for use inside $derived) -----------------------------
// Each returns a NEW Pauli, never mutating the input -- so reactive code can map
// inputs to outputs with no side effects (no $state written inside $effect).

type Gate1 = (p: Pauli, a: number) => void;
type Gate2 = (p: Pauli, a: number, b: number) => void;

function pure1(g: Gate1): (p: Pauli, a: number) => Pauli {
  return (p, a) => {
    const out = clone(p);
    g(out, a);

    return out;
  };
}

function pure2(g: Gate2): (p: Pauli, a: number, b: number) => Pauli {
  return (p, a, b) => {
    const out = clone(p);
    g(out, a, b);

    return out;
  };
}

export const withH = pure1(applyH);
export const withS = pure1(applyS);
export const withSdg = pure1(applySdg);
export const withX = pure1(applyX);
export const withY = pure1(applyY);
export const withZ = pure1(applyZ);
export const withCX = pure2(applyCX);
export const withCZ = pure2(applyCZ);
export const withSwap = pure2(applySwap);

// A named single-qubit gate, applied purely. Used by the gate-button rows.
export type Gate1Name = "H" | "S" | "S†" | "X" | "Y" | "Z";

export function apply1(name: Gate1Name, p: Pauli, a: number): Pauli {
  switch (name) {
    case "H":
      return withH(p, a);
    case "S":
      return withS(p, a);
    case "S†":
      return withSdg(p, a);
    case "X":
      return withX(p, a);
    case "Y":
      return withY(p, a);
    case "Z":
      return withZ(p, a);
  }
}

// ----- self-check ----------------------------------------------------------
// A handful of generator transforms verified by hand, so a future edit that
// breaks a sign rule is caught. Pure, side-effect-free, returns the failures.
// (Imported by nothing in production; safe to tree-shake. Kept for confidence.)
export function selfCheck(): string[] {
  const fails: string[] = [];
  const expect = (got: Pauli, want: string, msg: string): void => {
    if (pauliString(got) !== want) {
      fails.push(`${msg}: got ${pauliString(got)}, want ${want}`);
    }
  };

  // H: Z -> X (+), X -> Z (+), Y -> -Y.
  expect(withH(single(1, 0, "Z"), 0), "+X₀", "H:Z->X");
  expect(withH(single(1, 0, "X"), 0), "+Z₀", "H:X->Z");
  expect(withH(single(1, 0, "Y"), 0), "−Y₀", "H:Y->-Y");
  // S: X -> Y (+), Z -> Z (+).
  expect(withS(single(1, 0, "X"), 0), "+Y₀", "S:X->Y");
  expect(withS(single(1, 0, "Z"), 0), "+Z₀", "S:Z->Z");
  // S-dagger: X -> -Y.
  expect(withSdg(single(1, 0, "X"), 0), "−Y₀", "Sdg:X->-Y");

  // CX(0->1) generator transforms (all + signs):
  //   X_c -> X_c X_t,  X_t -> X_t,  Z_c -> Z_c,  Z_t -> Z_c Z_t.
  expect(withCX(single(2, 0, "X"), 0, 1), "+X₀X₁", "CX:Xc->XcXt");
  expect(withCX(single(2, 1, "X"), 0, 1), "+X₁", "CX:Xt->Xt");
  expect(withCX(single(2, 0, "Z"), 0, 1), "+Z₀", "CX:Zc->Zc");
  expect(withCX(single(2, 1, "Z"), 0, 1), "+Z₀Z₁", "CX:Zt->ZcZt");
  // Y_c -> Y_c X_t (X part forward, Z part stays):  x=(1,1),z=(1,0) sign +.
  expect(withCX(single(2, 0, "Y"), 0, 1), "+Y₀X₁", "CX:Yc->YcXt");

  // CZ(0,1) generator transforms (symmetric): X_0 -> X_0 Z_1, Z_0 -> Z_0.
  expect(withCZ(single(2, 0, "X"), 0, 1), "+X₀Z₁", "CZ:X0->X0Z1");
  expect(withCZ(single(2, 0, "Z"), 0, 1), "+Z₀", "CZ:Z0->Z0");

  return fails;
}
