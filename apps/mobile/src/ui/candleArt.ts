/**
 * Background candle art, as on the marketing site and the design kit's `data-art="candles"`.
 * Pure and deterministic: the same seed and size always give the same paths, so a screen's
 * art is computed once and never changes while it is open.
 */

/** mulberry32, the generator the design kit uses. */
export function rng(seed: number): () => number {
  let a = seed >>> 0 || 1;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gauss(r: () => number): number {
  const u = Math.max(r(), 1e-9);
  const v = r();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/** A random walk of `n` points from 1 to 1 + `ret`. */
export function series(seed: number, n: number, ret: number, vol: number): number[] {
  const r = rng(seed);
  const v = [0];
  for (let i = 1; i < n; i++) v.push(v[i - 1] + gauss(r) * vol);
  const end = v[n - 1];
  const target = Math.log(1 + ret);
  const span = Math.max(1, n - 1);
  return v.map((x, i) => Math.exp(x + ((target - end) * i) / span));
}

/** Open, high, low, close. */
export type Candle = readonly [number, number, number, number];

export function candles(seed: number, n: number, ret: number, vol: number): Candle[] {
  const r = rng(seed + 9);
  const c = series(seed, n + 1, ret, vol);
  const out: Candle[] = [];
  for (let i = 1; i <= n; i++) {
    const o = c[i - 1];
    const cl = c[i];
    const h = Math.max(o, cl) * (1 + Math.abs(gauss(r)) * vol * 0.6);
    const l = Math.min(o, cl) * (1 - Math.abs(gauss(r)) * vol * 0.6);
    out.push([o, h, l, cl]);
  }
  return out;
}

/** A string seed (a screen's name) as a stable 32-bit number. */
export function hashSeed(key: string | number): number {
  if (typeof key === 'number') return key >>> 0 || 1;
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0 || 1;
}

export interface CandleArt {
  /** Every wick in one path. */
  wicks: string;
  /** Rising candles, drawn as outlines. */
  up: string;
  /** Falling candles, drawn filled. */
  down: string;
  /** Two dotted price levels, as y positions. */
  levels: readonly [number, number];
  /** Which side the glow comes from. */
  glowSide: 'left' | 'right';
}

const f = (v: number) => v.toFixed(1);

/**
 * Candles across `width` x `height`, about one every 12pt, in three paths so the whole chart
 * is three SVG nodes however many candles it has.
 */
export function candleArt(seed: number, width: number, height: number): CandleArt {
  const w = Math.max(1, width);
  const h = Math.max(1, height);
  const n = Math.max(12, Math.round(w / 12));
  const r = rng(seed + 31);
  const ret = 0.15 + r() * 0.45;
  const cs = candles(seed, n, ret, 0.02);
  let lo = Infinity;
  let hi = -Infinity;
  for (const [, ch, cl] of cs) {
    lo = Math.min(lo, cl);
    hi = Math.max(hi, ch);
  }
  const padT = h * 0.1;
  const plot = h - padT - h * 0.22;
  const range = hi - lo || 1;
  const Y = (v: number) => padT + (1 - (v - lo) / range) * plot;
  const step = w / n;
  const bw = Math.max(1.5, step * 0.56);
  let wicks = '';
  let up = '';
  let down = '';
  cs.forEach(([o, ch, cl, c], i) => {
    const x = i * step + step / 2;
    wicks += `M${f(x)} ${f(Y(ch))}V${f(Y(cl))}`;
    const top = Y(Math.max(o, c));
    const bh = Math.max(1, Y(Math.min(o, c)) - top);
    const rect = `M${f(x - bw / 2)} ${f(top)}h${f(bw)}v${f(bh)}h${f(-bw)}Z`;
    if (c >= o) up += rect;
    else down += rect;
  });
  return {
    wicks,
    up,
    down,
    levels: [h * 0.3, h * 0.62],
    glowSide: r() < 0.5 ? 'left' : 'right',
  };
}
