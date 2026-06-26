// Deterministic PRNG so every interactive simulation is reproducible from a
// seed (the user can replay the exact same noisy shot). mulberry32 is a tiny,
// fast 32-bit generator -- plenty for teaching visualizations.

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;

  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;

    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Standard normal via Box-Muller, drawing from a [0,1) generator.
export function gaussian(rng: () => number): number {
  let u = 0;
  let v = 0;
  while (u === 0) {
    u = rng();
  }
  while (v === 0) {
    v = rng();
  }

  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export function bernoulli(rng: () => number, p: number): boolean {
  return rng() < p;
}

// Sample one item, optionally weighted (weights need not be normalized).
export function choice<T>(rng: () => number, items: T[], weights?: number[]): T {
  if (!weights) {
    return items[Math.floor(rng() * items.length)];
  }

  const total = weights.reduce((s, w) => s + w, 0);
  let threshold = rng() * total;
  for (let i = 0; i < items.length; i += 1) {
    threshold -= weights[i];
    if (threshold <= 0) {
      return items[i];
    }
  }

  return items[items.length - 1];
}
