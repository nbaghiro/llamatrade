/** Plan and usage rows with a forecast for the monthly counters (billing/plan2 A). */

export interface UsageRowInput {
  label: string;
  used: number;
  /** Negative means unlimited; zero means not included in the plan. */
  limit: number;
  /** Counts that reset each month get a forecast. */
  monthly: boolean;
}

export interface UsageRow {
  label: string;
  used: number;
  limit: number;
  /** "212 of 500", "3 of no limit". */
  figure: string;
  /** Bar fill, 0 to 1. */
  fraction: number;
  /** Where the dashed stretch ends, 0 to 1, or null without a forecast. */
  forecastFraction: number | null;
  /** "About 375 by Nov 30", or null. */
  forecastNote: string | null;
  atLimit: boolean;
  /** The forecast passes the limit before the month ends. */
  willPass: boolean;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * Where a monthly counter ends up at this month's pace, or null when it's too early to say.
 * Usage so far divided by the days elapsed, times the days in the month.
 */
export function monthForecast(used: number, now: Date): number | null {
  const day = now.getDate();
  if (used <= 0 || day < 2) return null;
  const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const elapsed = day - 1 + (now.getHours() * 60 + now.getMinutes()) / 1440;
  if (elapsed <= 0) return null;
  return Math.max(used, Math.round((used / elapsed) * days));
}

/** "Nov 30". */
export function monthEndLabel(now: Date): string {
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  return `${MONTHS[end.getMonth()]} ${end.getDate()}`;
}

/** "Dec 1". */
export function resetLabel(now: Date): string {
  const next = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  return `${MONTHS[next.getMonth()]} ${next.getDate()}`;
}

const n = (v: number) => v.toLocaleString('en-US');

export function usageRow(input: UsageRowInput, now: Date): UsageRow {
  const used = Math.max(0, input.used);
  const { limit } = input;
  const unlimited = limit < 0;
  const fraction = limit > 0 ? Math.min(1, used / limit) : 0;
  const forecast = input.monthly ? monthForecast(used, now) : null;
  const showForecast = forecast !== null && forecast > used;
  return {
    label: input.label,
    used,
    limit,
    figure: unlimited ? `${n(used)}, no limit` : limit === 0 ? 'Not included' : `${n(used)} of ${n(limit)}`,
    fraction,
    forecastFraction: showForecast && limit > 0 ? Math.min(1, forecast / limit) : null,
    forecastNote: showForecast ? `About ${n(forecast)} by ${monthEndLabel(now)}` : null,
    atLimit: limit > 0 && used >= limit,
    willPass: showForecast && limit > 0 && forecast > limit && used < limit,
  };
}
