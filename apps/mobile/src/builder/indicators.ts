/** Indicator series from daily closes, for drawing a threshold over its own history (builder/condition2 A). */

/** Wilder's RSI; null until `period` changes have been seen. */
export function rsi(closes: readonly number[], period: number): (number | null)[] {
  const out: (number | null)[] = closes.map(() => null);
  if (period < 1 || closes.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) gain += d;
    else loss -= d;
  }
  gain /= period;
  loss /= period;
  const value = () => (loss === 0 ? (gain === 0 ? 50 : 100) : 100 - 100 / (1 + gain / loss));
  out[period] = value();
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    gain = (gain * (period - 1) + Math.max(d, 0)) / period;
    loss = (loss * (period - 1) + Math.max(-d, 0)) / period;
    out[i] = value();
  }
  return out;
}

export function sma(closes: readonly number[], period: number): (number | null)[] {
  const out: (number | null)[] = closes.map(() => null);
  if (period < 1) return out;
  let sum = 0;
  closes.forEach((c, i) => {
    sum += c;
    if (i >= period) sum -= closes[i - period];
    if (i >= period - 1) out[i] = sum / period;
  });
  return out;
}

export function ema(closes: readonly number[], period: number): (number | null)[] {
  const out: (number | null)[] = closes.map(() => null);
  if (period < 1 || closes.length < period) return out;
  const k = 2 / (period + 1);
  let prev = closes.slice(0, period).reduce((s, c) => s + c, 0) / period;
  out[period - 1] = prev;
  for (let i = period; i < closes.length; i++) {
    prev = closes[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

/** The series for an indicator the builder can draw, or null for one it can't compute from closes. */
export function indicatorSeries(name: string, closes: readonly number[], period: number | null): (number | null)[] | null {
  const p = period ?? 14;
  switch (name) {
    case 'rsi':
      return rsi(closes, p);
    case 'sma':
      return sma(closes, p);
    case 'ema':
      return ema(closes, p);
    case 'price':
      return [...closes];
    default:
      return null;
  }
}

/** How many days the series sat above a threshold, and how often it crossed upward. */
export function thresholdCounts(series: readonly (number | null)[], threshold: number): { above: number; crossings: number; days: number } {
  let above = 0;
  let crossings = 0;
  let days = 0;
  let prev: number | null = null;
  for (const v of series) {
    if (v === null) continue;
    days++;
    if (v > threshold) above++;
    if (prev !== null && prev <= threshold && v > threshold) crossings++;
    prev = v;
  }
  return { above, crossings, days };
}
