// Wire schema shared with the qliff server. Mirror of qliff/server/schema.py --
// keep the two in lockstep. Plain types (no runtime validation); the server is
// the validating side (pydantic).

export type TileKind = "square" | "tri" | "hex";
export type Pauli = "X" | "Z";
export type CodeFamily =
  | "repetition"
  | "rotated_surface"
  | "unrotated_surface"
  | "toric";
export type DecoderName = "mwpm" | "bposd" | "mld" | "tn" | "coherent";
export type Boundary = "open" | "periodic";
// Surface-code stabiliser-pattern knobs (rotated + unrotated families), following
// the EVEN-X / EVEN-Z analysis: `pattern` (plain CSS vs the Hadamard-conjugated
// XZZX code), `start` (the X/Z colouring; "X" is the global-Hadamard dual), and
// `edge` (which alternating boundary-edge set / logical orientation; rotated only).
export type SurfacePattern = "css" | "xzzx";
export type SurfaceStart = "Z" | "X";
export type SurfaceEdge = "even" | "odd";

// Per-channel argument shape: a single strength, a coherent angle, or a 3-vector
// of Pauli probabilities (PAULI_CHANNEL_1).
export type ChannelArg = "p" | "theta" | "vec3";

// ---- builder geometry ----------------------------------------------------

// One placed polygon. rotation is degrees; for triangles 0 = up, 180 = down.
export interface Tile {
  id: string;
  kind: TileKind;
  row: number;
  col: number;
  rotation: number; // default 0
}

// ---- resolved lattice ----------------------------------------------------

export interface Stabilizer {
  type: Pauli;
  data: number[];
}

export interface Observable {
  type: Pauli;
  data: number[];
}

// A code laid out in space. `tiles` is raw builder geometry; the server resolves
// it, or num_data/stabilizers/observables are supplied directly.
export interface LatticeSpec {
  tiles: Tile[];
  num_data?: number | null;
  stabilizers: Stabilizer[];
  observables: Observable[];
  boundary: Boundary; // default "open"
}

export interface Template {
  family: CodeFamily;
  distance: number; // >= 2
  // Surface-family stabiliser pattern (defaults css/Z/even); `edge` is rotated-only.
  pattern?: SurfacePattern;
  start?: SurfaceStart;
  edge?: SurfaceEdge;
}

// ---- noise + run request -------------------------------------------------

// Noise op name (matches the Circuit op) at strength p, or swept over p_sweep.
// Exactly one of p / p_sweep. `theta` carries the coherent angle for RZ/RX;
// `vec3` carries the (px,py,pz) probabilities for PAULI_CHANNEL_1.
export interface NoiseModel {
  channel: string; // default "DEPOLARIZE1"
  p?: number | null;
  p_sweep?: number[] | null;
  theta?: number | null;
  vec3?: [number, number, number] | null;
}

// A LER run. Exactly one of template / spec is set.
export interface RunRequest {
  template?: Template | null;
  spec?: LatticeSpec | null;
  rounds?: number | null;
  noise: NoiseModel;
  shots: number; // default 10000
  decoder: DecoderName; // default "mwpm"
  seed?: number | null;
}

// ---- responses -----------------------------------------------------------

export interface CompileResponse {
  ok: boolean;
  num_qubits: number;
  num_data: number;
  num_stabilizers: number;
  num_detectors: number;
  num_observables: number;
  warnings: string[];
}

export interface LerPoint {
  p: number;
  ler: number;
  stderr: number;
  shots: number;
}

export interface RunResponse {
  decoder: string;
  points: LerPoint[];
  num_qubits: number;
  num_detectors: number;
  elapsed: number;
}

// One run event. The server's WebSocket sends point/done/error frames; the
// client adds a synthetic "fallback" event (when it degrades to REST) and a
// `transport` flag on errors that came from a dead socket rather than the server.
export interface RunEvent {
  type: "point" | "done" | "error" | "fallback";
  point?: LerPoint | null;
  message?: string | null;
  transport?: boolean;
}

export interface TemplateInfo {
  family: CodeFamily;
  label: string;
  min_distance: number;
  decoders: DecoderName[];
  // Stabiliser-pattern options per axis; one entry on an axis => no selector for it.
  patterns: SurfacePattern[];
  starts: SurfaceStart[];
  edges: SurfaceEdge[];
}

// GET /api/decoders entry. `pauli_only` decoders work off a detector-error model
// and can only honestly decode Pauli noise.
export interface DecoderInfo {
  name: DecoderName;
  label: string;
  pauli_only: boolean;
  note: string;
}

// GET /api/channels entry. `is_pauli` false marks coherent / amplitude-damping
// channels that a DEM decoder can't honestly handle. `arg` selects the input UI.
export interface ChannelInfo {
  name: string;
  label: string;
  is_pauli: boolean;
  arg: ChannelArg;
  note: string;
}
