/** Seeded figures for the screen art. None of it is account data; the page says so. */

import { compound, gaussians, tradingDays } from '../../lib/illustrative';

import type { Shade } from './editorLevels';

export interface AccountMonth {
  days: Date[];
  account: number[];
  benchmark: number[];
}

let cached: AccountMonth | null = null;

/** Equity on account and sleeve screens, as of the Nov 13 close. */
export const EQUITY = { total: 103_410.27, today: 895.4 } as const;

/** Compounds `z` from `start` to the day before the close, then moves by `today` to `end`. */
function closingSeries(z: readonly number[], start: number, end: number, today: number): number[] {
  return [...compound(z.slice(0, -1), start, end - today), end];
}

/** One month of account equity against SPY, Oct 14 to Nov 13 2026, ending at $103,410.27. */
export function accountMonth(): AccountMonth {
  if (cached) return cached;
  const days = tradingDays('2026-10-14', '2026-11-13');
  const z = gaussians(5, days.length).map((x) => x * 0.0046);
  const zb = gaussians(8, days.length).map((x, i) => x * 0.007 + z[i] * 0.5);
  cached = {
    days,
    account: closingSeries(z, 101_284.6, EQUITY.total, EQUITY.today),
    benchmark: compound(zb, 101_284.6, 102_633.9),
  };
  return cached;
}

/** Today's change as a fraction of yesterday's close. */
export function dayChange(value: number, today: number): number {
  return today / (value - today);
}

export interface SleeveRow {
  name: string;
  state: 'running' | 'frozen';
  note: string;
  equity: number;
  today: number;
  /** One month of sleeve equity, ending at `equity` after today's move. */
  month: number[];
}

let sleeves: SleeveRow[] | null = null;

/** The three sleeves on the portfolio screen, with a month of equity each for sparklines. */
export function sleeveRows(): SleeveRow[] {
  if (sleeves) return sleeves;
  const n = accountMonth().days.length;
  const tech = techMomentum();
  sleeves = [
    {
      name: 'All-Weather Portfolio',
      state: 'running',
      note: 'Running · next Dec 1',
      equity: 35_982.55,
      today: -84.12,
      month: closingSeries(
        gaussians(21, n).map((x) => x * 0.003),
        35_610,
        35_982.55,
        -84.12
      ),
    },
    {
      name: 'Recession Radar',
      state: 'frozen',
      note: 'Frozen since 10:15',
      equity: 25_436.18,
      today: 112.4,
      month: closingSeries(
        gaussians(34, n).map((x) => x * 0.004),
        25_190,
        25_436.18,
        112.4
      ),
    },
    {
      name: 'Tech Momentum Rotation',
      state: 'running',
      note: 'Running · next Dec 1',
      equity: tech.equity[tech.equity.length - 1],
      today: tech.today,
      month: tech.equity.slice(-n),
    },
  ];
  return sleeves;
}

export interface SessionCurve {
  days: Date[];
  equity: number[];
  allocated: number;
  today: number;
  /** Index of the Nov 2 rebalance in `days`. */
  rebalanceAt: number;
}

let techCurve: SessionCurve | null = null;

/** Tech Momentum Rotation since it started on Oct 1 with $25,000, ending at $24,914.42. */
export function techMomentum(): SessionCurve {
  if (techCurve) return techCurve;
  const days = tradingDays('2026-10-01', '2026-11-13');
  const z = gaussians(47, days.length).map((x) => x * 0.009);
  for (let i = 12; i < 24; i++) z[i] -= 0.003;
  techCurve = {
    days,
    equity: closingSeries(z, 25_000, 24_914.42, 867.12),
    allocated: 25_000,
    today: 867.12,
    rebalanceAt: days.findIndex((d) => d.getUTCMonth() === 10 && d.getUTCDate() === 2),
  };
  return techCurve;
}

export interface MomentumLine {
  sym: string;
  /** Return over the 90-day lookback, as a fraction. */
  ret: number;
  /** Growth of 1 over the lookback. */
  values: number[];
}

/** QQQ, XLK and SMH over the 90-day lookback to Nov 13, ranked by return. SMH and QQQ hold. */
export function momentumLines(): MomentumLine[] {
  const days = tradingDays('2026-07-03', '2026-11-13').length;
  return (
    [
      ['SMH', 0.142, 61],
      ['QQQ', 0.087, 62],
      ['XLK', 0.061, 63],
    ] as const
  ).map(([sym, ret, seed]) => ({
    sym,
    ret,
    values: compound(
      gaussians(seed, days).map((x) => x * 0.011),
      1,
      1 + ret
    ),
  }));
}

export const INDICATORS: readonly string[] = [
  'adx',
  'atr',
  'bbands',
  'cci',
  'donchian',
  'ema',
  'keltner',
  'macd',
  'mfi',
  'momentum',
  'obv',
  'rsi',
  'sma',
  'stddev',
  'stoch',
  'vwap',
  'williams-r',
];

export const METRICS: readonly string[] = ['return', 'volatility', 'drawdown'];

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Nov 13". */
export function shortDate(d: Date): string {
  return `${MON[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

/** Sleeves as shares of total equity, with the unallocated share hatched. */
export const SLEEVE_SPLIT: readonly { shade: Shade; weight: number }[] = [
  { shade: 'h1', weight: 34.8 },
  { shade: 'h2', weight: 24.6 },
  { shade: 'h3', weight: 24.1 },
  { shade: 'hfree', weight: 16.5 },
];
