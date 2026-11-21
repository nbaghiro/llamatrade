/**
 * The fixed, illustrative Recession Radar v3 backtest shown beside the sign-in forms. It mirrors
 * apps/web/src/lib/illustrative/example.ts so both apps draw the same curve and figures.
 */

export const ILLUSTRATIVE_NOTE = "Illustrative figures, not anyone's account.";

export interface ExampleBacktest {
  name: string;
  benchmark: string;
  startingCapital: number;
  days: Date[];
  strategy: number[];
  benchmarkValues: number[];
  /** Total returns as fractions. */
  total: number;
  benchmarkTotal: number;
}

function mulberry(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussians(seed: number, n: number): number[] {
  const r = mulberry(seed);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const u = 1 - r();
    const v = r();
    out.push(Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v));
  }
  return out;
}

/** Weekdays from `start` to `end` inclusive (YYYY-MM-DD, UTC noon). */
export function tradingDays(start: string, end: string): Date[] {
  const out: Date[] = [];
  const d = new Date(`${start}T12:00:00Z`);
  const e = new Date(`${end}T12:00:00Z`);
  while (d <= e) {
    const w = d.getUTCDay();
    if (w !== 0 && w !== 6) out.push(new Date(d));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

/** Compounds log returns from `start`, drifted so the series ends exactly at `end`. */
export function compound(z: readonly number[], start: number, end: number): number[] {
  const n = z.length;
  if (n === 0) return [];
  if (n === 1) return [start];
  let s = 0;
  for (let i = 1; i < n; i++) s += z[i];
  const adj = (Math.log(end / start) - s) / (n - 1);
  const out = [start];
  let lv = Math.log(start);
  for (let i = 1; i < n; i++) {
    lv += z[i] + adj;
    out.push(Math.exp(lv));
  }
  return out;
}

function shock(z: number[], at: number, len: number, amount: number): void {
  for (let i = Math.max(0, at); i < at + len && i < z.length; i++) z[i] += amount / len;
}

let cached: ExampleBacktest | null = null;

export function exampleBacktest(): ExampleBacktest {
  if (cached) return cached;
  const days = tradingDays('2024-11-01', '2026-10-30');
  const n = days.length;
  const m = gaussians(11, n).map((x) => x * 0.0098);
  const idio = gaussians(29, n).map((x) => x * 0.0052);
  const aprIdx = days.findIndex((d) => d.toISOString().startsWith('2025-03-24'));
  shock(m, aprIdx, 12, -0.19);
  shock(m, aprIdx + 12, 30, 0.13);
  const spyZ = m.slice();
  const stratZ = m.map((x, i) => x * 0.62 + idio[i]);
  shock(stratZ, aprIdx + 3, 10, 0.065);
  const spy = compound(spyZ, 25000, 31228.4);
  const strat = compound(stratZ, 25000, 30352.18);
  cached = {
    name: 'Recession Radar v3',
    benchmark: 'SPY',
    startingCapital: 25000,
    days,
    strategy: strat,
    benchmarkValues: spy,
    total: strat[strat.length - 1] / strat[0] - 1,
    benchmarkTotal: spy[spy.length - 1] / spy[0] - 1,
  };
  return cached;
}
