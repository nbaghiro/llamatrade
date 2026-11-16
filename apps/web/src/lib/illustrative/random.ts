/** Seeded randomness so illustrative series are identical on every render and device. */

export function mulberry(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** `n` standard normal draws (Box-Muller) from one seed. */
export function gaussians(seed: number, n: number): number[] {
  const r = mulberry(seed);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const u = 1 - r();
    const v = r();
    out.push(Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v));
  }
  return out;
}
