// Bloch-sphere kinematics for a single qubit, in the SAME conventions as qliff's
// gates. A pure state |psi> maps to a unit vector r = (rx, ry, rz); a mixed state
// (after amplitude damping) maps to r with |r| < 1. We track the FULL r so the
// damping section can shrink and offset it. Bloch poles: +z = |0>, -z = |1>,
// +x = |+>, +y = |+i>.

export type Vec3 = [number, number, number];

// Single-qubit Cliffords as proper rotations of the Bloch vector. Each is the
// 3x3 SO(3) matrix the gate induces on r (the adjoint action of the unitary).
// X: rotate pi about x. Z: rotate pi about z. H: swap x<->z, negate y (rotate pi
// about (x+z)/sqrt2). S = RZ(pi/2): rotate +pi/2 about z.
export type GateName = "X" | "Z" | "H" | "S";

function applyMat(m: number[][], v: Vec3): Vec3 {
  return [
    m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
    m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
    m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
  ];
}

const GATE_MAT: Record<GateName, number[][]> = {
  X: [
    [1, 0, 0],
    [0, -1, 0],
    [0, 0, -1],
  ],
  Z: [
    [-1, 0, 0],
    [0, -1, 0],
    [0, 0, 1],
  ],
  H: [
    [0, 0, 1],
    [0, -1, 0],
    [1, 0, 0],
  ],
  S: [
    [0, -1, 0],
    [1, 0, 0],
    [0, 0, 1],
  ],
};

export function applyGate(g: GateName, v: Vec3): Vec3 {
  return applyMat(GATE_MAT[g], v);
}

// RZ(theta) = exp(-i theta Z / 2): rotate the Bloch vector by +theta about the
// z-axis (counter-clockwise looking down from +z). This is the CONTINUOUS coherent
// rotation -- the heart of the page.
export function applyRz(theta: number, v: Vec3): Vec3 {
  const c = Math.cos(theta);
  const s = Math.sin(theta);

  return [c * v[0] - s * v[1], s * v[0] + c * v[1], v[2]];
}

// Amplitude damping as the affine Bloch map (Kraus channel with energy-loss prob p):
//   rx, ry -> sqrt(1-p) * (rx, ry)        (transverse shrink)
//   rz     -> p + (1-p) * rz              (pull toward +z = |0>)
// At p = 1 every state collapses to the north pole |0>.
export function applyDamping(p: number, v: Vec3): Vec3 {
  const root = Math.sqrt(Math.max(0, 1 - p));

  return [root * v[0], root * v[1], p + (1 - p) * v[2]];
}

export function norm(v: Vec3): number {
  return Math.hypot(v[0], v[1], v[2]);
}
