import type { CurvePoint } from '@llamatrade/core/chart';
import type { DashboardPeriod } from '@llamatrade/core/stores/dashboard';

const PERIOD_DAYS: Record<DashboardPeriod, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
  ALL: null,
};

export interface EquityWindow {
  dates: Date[];
  /** Account return in percent, rebased to 0 at the window's first point. */
  account: number[];
  /** Benchmark return in percent on the same dates, or null when there is none to align. */
  bench: number[] | null;
  /** Account return over the window, as a fraction. */
  accountReturn: number;
  benchReturn: number | null;
}

const growth = (pct: number) => 1 + pct / 100;

function rebase(values: readonly number[]): number[] {
  const base = growth(values[0]);
  return values.map((v) => (base > 0 ? (growth(v) / base - 1) * 100 : 0));
}

/** For each date, the benchmark's latest value at or before it (its first value before it starts). */
export function alignAsOf(dates: readonly Date[], bench: readonly CurvePoint[]): number[] | null {
  if (bench.length === 0) return null;
  const points = bench
    .map((p) => ({ t: new Date(p.timestamp).getTime(), v: p.value }))
    .filter((p) => Number.isFinite(p.t))
    .sort((a, b) => a.t - b.t);
  if (points.length === 0) return null;
  const out: number[] = [];
  let j = 0;
  for (const d of dates) {
    const t = d.getTime();
    while (j + 1 < points.length && points[j + 1].t <= t) j++;
    out.push(points[j].v);
  }
  return out;
}

/**
 * The account and benchmark lines for one range, both rebased to the window's start.
 * A range with fewer than two points falls back to the full history.
 */
export function equityWindow(
  portfolio: readonly CurvePoint[],
  benchmark: readonly CurvePoint[],
  period: DashboardPeriod
): EquityWindow | null {
  if (portfolio.length < 2) return null;
  const days = PERIOD_DAYS[period];
  const lastT = new Date(portfolio[portfolio.length - 1].timestamp).getTime();
  const windowed =
    days === null
      ? portfolio
      : portfolio.filter((p) => new Date(p.timestamp).getTime() >= lastT - days * 86_400_000);
  const points = windowed.length > 1 ? windowed : portfolio;

  const dates = points.map((p) => new Date(p.timestamp));
  const account = rebase(points.map((p) => p.value));
  const aligned = alignAsOf(dates, benchmark);
  const bench = aligned ? rebase(aligned) : null;
  return {
    dates,
    account,
    bench,
    accountReturn: account[account.length - 1] / 100,
    benchReturn: bench ? bench[bench.length - 1] / 100 : null,
  };
}
