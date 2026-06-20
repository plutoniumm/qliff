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
export type DecoderName = "mwpm" | "bposd";
export type Boundary = "open" | "periodic";

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
}

// ---- noise + run request -------------------------------------------------

// Noise op name (matches the Circuit op) at strength p, or swept over p_sweep.
// Exactly one of p / p_sweep.
export interface NoiseModel {
  channel: string; // default "DEPOLARIZE1"
  p?: number | null;
  p_sweep?: number[] | null;
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

// One WebSocket frame during a streaming run.
export interface RunEvent {
  type: "point" | "done" | "error";
  point?: LerPoint | null;
  message?: string | null;
}

export interface TemplateInfo {
  family: CodeFamily;
  label: string;
  min_distance: number;
  decoders: DecoderName[];
}
