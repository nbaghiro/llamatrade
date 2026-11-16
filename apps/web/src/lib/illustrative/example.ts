import { gaussians } from './random';
import {
  compound,
  drawdown,
  monthly,
  shock,
  stats,
  tradingDays,
  type MonthReturn,
  type SeriesStats,
} from './series';

/** Every surface built from this module shows this label; none of it is account data. */
export const ILLUSTRATIVE_LABEL = 'Illustrative';

export interface ExampleBacktest {
  name: string;
  benchmark: string;
  startingCapital: number;
  days: Date[];
  strategy: number[];
  benchmarkValues: number[];
  strategyStats: SeriesStats;
  benchmarkStats: SeriesStats;
  drawdown: number[];
  benchmarkDrawdown: number[];
  months: MonthReturn[];
}

let cached: ExampleBacktest | null = null;

/** A fixed example: Recession Radar v3 against SPY, Nov 1 2024 to Oct 30 2026, $25,000. */
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
    strategyStats: stats(strat, days),
    benchmarkStats: stats(spy, days),
    drawdown: drawdown(strat),
    benchmarkDrawdown: drawdown(spy),
    months: monthly(strat, days),
  };
  return cached;
}

/** A short seeded walk between 0.05 and 0.95, for sparkline art. */
export function illustrativeWalk(seed: number, up = true, points = 28): number[] {
  const r = gaussians(seed, points);
  const out: number[] = [];
  let v = 0.5;
  for (let i = 0; i < points; i++) {
    v += (r[i] * 0.5 + (up ? 0.15 : -0.15)) * 0.06;
    v = Math.max(0.05, Math.min(0.95, v));
    out.push(v);
  }
  return out;
}
