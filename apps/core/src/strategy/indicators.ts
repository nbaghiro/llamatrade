// Client-side indicator history for the editor. The formulas mirror
// libs/runtime/llamatrade_runtime/indicators/library.py so a threshold drawn here
// matches what the engine tests in a backtest. Values before warm-up are NaN.

import type { Comparator, IndicatorName } from "./types";

export function sma(values: readonly number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (period < 1 || values.length < period) return out;
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

export function ema(values: readonly number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (period < 1 || values.length < period) return out;
  const k = 2 / (period + 1);
  let prev = 0;
  for (let i = 0; i < period; i++) prev += values[i];
  prev /= period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

/** Wilder's RSI, seeded with the simple mean of the first `period` changes. */
export function rsi(values: readonly number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (period < 1 || values.length < period + 1) return out;
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    gains.push(d > 0 ? d : 0);
    losses.push(d < 0 ? -d : 0);
  }
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 0; i < period; i++) {
    avgGain += gains[i];
    avgLoss += losses[i];
  }
  avgGain /= period;
  avgLoss /= period;
  const value = () =>
    avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  out[period] = value();
  for (let i = period; i < gains.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    out[i + 1] = value();
  }
  return out;
}

/** Difference from `period` bars ago. */
export function momentum(values: readonly number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  for (let i = period; i < values.length; i++)
    out[i] = values[i] - values[i - period];
  return out;
}

/** Rolling population standard deviation. */
export function stddev(values: readonly number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (period < 1) return out;
  for (let i = period - 1; i < values.length; i++) {
    let mean = 0;
    for (let j = i - period + 1; j <= i; j++) mean += values[j];
    mean /= period;
    let sq = 0;
    for (let j = i - period + 1; j <= i; j++) sq += (values[j] - mean) ** 2;
    out[i] = Math.sqrt(sq / period);
  }
  return out;
}

const CLOSE_INDICATORS = {
  sma,
  ema,
  rsi,
  momentum,
} as const satisfies Partial<
  Record<IndicatorName, (v: readonly number[], p: number) => number[]>
>;

export type DrawableIndicator = keyof typeof CLOSE_INDICATORS;

/** Indicators the editor can draw from daily closes alone. */
export function isDrawableIndicator(
  name: IndicatorName,
): name is DrawableIndicator {
  return name in CLOSE_INDICATORS;
}

export function indicatorFromCloses(
  name: DrawableIndicator,
  closes: readonly number[],
  period: number,
): number[] {
  return CLOSE_INDICATORS[name](closes, period);
}

/** Bars of history an indicator needs before its first value. */
export function warmupBars(name: DrawableIndicator, period: number): number {
  return name === "rsi" || name === "momentum" ? period + 1 : period;
}

export function compares(
  value: number,
  comparator: Comparator,
  threshold: number,
): boolean {
  switch (comparator) {
    case "gt":
    case "cross_above":
      return value > threshold;
    case "lt":
    case "cross_below":
      return value < threshold;
    case "gte":
      return value >= threshold;
    case "lte":
      return value <= threshold;
    case "eq":
      return value === threshold;
    case "neq":
      return value !== threshold;
  }
}

export interface HeldStretch {
  from: number;
  to: number;
}

export interface ConditionStats {
  /** Days the condition held, counting only days with a value. */
  days: number;
  /** Separate runs of consecutive days when it held. */
  stretches: HeldStretch[];
  /** Indexes of `rebalanceIdx` at which it held. */
  rebalancesHeld: number[];
}

/**
 * How often a comparison against a fixed threshold held over a series, and at which
 * rebalance days. `rebalanceIdx` are indexes into `values`.
 */
export function conditionStats(
  values: readonly number[],
  comparator: Comparator,
  threshold: number,
  rebalanceIdx: readonly number[] = [],
): ConditionStats {
  const held = values.map(
    (v) => Number.isFinite(v) && compares(v, comparator, threshold),
  );
  const stretches: HeldStretch[] = [];
  let days = 0;
  let start = -1;
  for (let i = 0; i < held.length; i++) {
    if (held[i]) {
      days++;
      if (start < 0) start = i;
    } else if (start >= 0) {
      stretches.push({ from: start, to: i - 1 });
      start = -1;
    }
  }
  if (start >= 0) stretches.push({ from: start, to: held.length - 1 });
  const rebalancesHeld = rebalanceIdx.filter((i) => held[i]);
  return { days, stretches, rebalancesHeld };
}

/** Index of the first trading day in each calendar month of `dates` (UTC). */
export function monthStarts(dates: readonly Date[]): number[] {
  const out: number[] = [];
  let last = "";
  dates.forEach((d, i) => {
    const key = `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
    if (key !== last) {
      out.push(i);
      last = key;
    }
  });
  return out;
}
