/** Seeded figures for the screen art. None of it is account data; the page says so. */

import { compound, gaussians, tradingDays } from '../../lib/illustrative';

import type { Shade } from './editorLevels';

export interface AccountMonth {
  days: Date[];
  account: number[];
  benchmark: number[];
}

let cached: AccountMonth | null = null;

/** One month of account equity against SPY, Oct 14 to Nov 13 2026, ending at $103,410.27. */
export function accountMonth(): AccountMonth {
  if (cached) return cached;
  const days = tradingDays('2026-10-14', '2026-11-13');
  const z = gaussians(5, days.length).map((x) => x * 0.0046);
  const zb = gaussians(8, days.length).map((x, i) => x * 0.007 + z[i] * 0.5);
  cached = {
    days,
    account: compound(z, 101_284.6, 103_410.27),
    benchmark: compound(zb, 101_284.6, 102_633.9),
  };
  return cached;
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
