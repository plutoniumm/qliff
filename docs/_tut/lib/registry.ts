// The seven explainers, in pedagogical order: first the simulator foundation
// (how Clifford gates act on the stabilizer tableau -- especially CX), then three
// decoders (matching -> belief propagation -> tensor networks), then the noise
// model that feeds them (coherent channels -> the trajectory sampler), then how a
// logical error rate ties decoder + noise together.
//
// This is a multi-page app: each explainer is its own HTML entry (gates.html,
// mwpm.html, ...) that statically imports exactly one explainer component, so a
// heavy page (three.js on `coherent`) never weighs on the others. The registry is
// the single source of truth for ordering, titles and the sidebar/pager links --
// every page links to the others via `<id>.html`.

export interface Explainer {
  id: string;
  step: string;
  title: string;
  short: string;
  tagline: string;
}

export const explainers: Explainer[] = [
  {
    id: "gates",
    step: "01",
    title: "Gates in a Stabilizer Simulator",
    short: "Gates & CX",
    tagline: "Cliffords don't move amplitudes -- they conjugate Pauli operators. See why CX makes X copy forward and Z copy backward.",
  },
  {
    id: "mwpm",
    step: "02",
    title: "Minimum-Weight Perfect Matching",
    short: "MWPM",
    tagline: "Turn a syndrome into a graph, then pair up the defects as cheaply as possible.",
  },
  {
    id: "bp",
    step: "03",
    title: "Belief Propagation",
    short: "Belief propagation",
    tagline: "Let qubits and checks exchange probabilities until they agree on the likeliest error.",
  },
  {
    id: "tn",
    step: "04",
    title: "Tensor-Network Decoder",
    short: "Tensor networks",
    tagline: "Sum over every possible error at once by contracting a factor graph -- exact maximum likelihood.",
  },
  {
    id: "coherent",
    step: "05",
    title: "The Coherent-Noise Engine",
    short: "Coherent noise",
    tagline: "Rotations and damping aren't Pauli errors -- represent them as signed quasiprobabilities over Cliffords.",
  },
  {
    id: "noise",
    step: "06",
    title: "Simulating Noise",
    short: "Noise sampling",
    tagline: "How one stabilizer trajectory is drawn, and why importance weights make non-Pauli noise honest.",
  },
  {
    id: "ler",
    step: "07",
    title: "Logical Error Rate & Fidelity",
    short: "Logical error rate",
    tagline: "Sample, decode, compare -- and read the threshold off a sweep with honest error bars.",
  },
];

// Each explainer is a VitePress route under /tutorials/: `./<id>` from the
// overview, and the empty id is the overview itself (`./`). Links are relative so
// VitePress' base ("/qliff/" in prod, "/" in dev) resolves them, and its client
// router turns the click into an in-app navigation.
export function pageHref(id: string): string {
  return id === "" ? "./" : `./${id}`;
}

export function byId(id: string): Explainer | undefined {
  return explainers.find((e) => e.id === id);
}

export function neighbours(id: string): { prev?: Explainer; next?: Explainer } {
  const i = explainers.findIndex((e) => e.id === id);
  if (i === -1) {
    return { next: explainers[0] };
  }

  return { prev: explainers[i - 1], next: explainers[i + 1] };
}
