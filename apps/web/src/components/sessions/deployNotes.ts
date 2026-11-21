import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';

import { formatPct } from '../../lib/format';
import { marketDay } from '../../lib/marketHolidays';

import { dayLabel } from './sessionRows';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const monthYear = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`;

/**
 * The newest completed backtest of a strategy in one line, and whether the version about to start
 * differs from the one backtested. Null when the strategy has no completed run.
 */
export function backtestLine(
  runs: readonly BacktestRun[],
  strategyId: string,
  version: number
): string | null {
  const ofStrategy = runs
    .filter((r) => r.strategyId === strategyId && r.results?.metrics)
    .sort(
      (a, b) =>
        (toDate(b.completedAt) ?? toDate(b.createdAt) ?? new Date(0)).getTime() -
        (toDate(a.completedAt) ?? toDate(a.createdAt) ?? new Date(0)).getTime()
    );
  const run =
    (version ? ofStrategy.find((r) => r.strategyVersion === version) : undefined) ?? ofStrategy[0];
  const m = run?.results?.metrics;
  if (!run || !m) return null;
  const from = toDate(run.config?.startDate);
  const to = toDate(run.config?.endDate);
  const span = from && to ? `, ${monthYear(from)} to ${monthYear(to)}` : '';
  const yearly = formatPct(toNumber(m.annualizedReturn), { dp: 1 });
  const dd = formatPct(-Math.abs(toNumber(m.maxDrawdown)), { dp: 1 });
  const line = `Backtest of version ${run.strategyVersion}${span}: ${yearly} a year, largest drawdown ${dd}.`;
  return version && run.strategyVersion !== version
    ? `${line} Version ${version} hasn't been backtested yet.`
    : line;
}

/**
 * Why a scheduled date isn't the first weekday of its period: the weekday holidays just before
 * it, e.g. "Jan 1 is New Year's Day, so this one runs on Mon, Jan 4". Null when none.
 */
export function holidayNote(at: Date): string | null {
  const skipped: { day: Date; name: string }[] = [];
  const d = new Date(at);
  for (let i = 0; i < 6; i++) {
    d.setUTCDate(d.getUTCDate() - 1);
    const md = marketDay(d);
    if (!md.closed) break;
    if (md.name) skipped.unshift({ day: new Date(d), name: md.name });
  }
  if (skipped.length === 0) return null;
  const first = skipped[0];
  return `${dayLabel(first.day)} is ${first.name}, so this one runs on ${WEEKDAY[at.getUTCDay()]}, ${dayLabel(at)}.`;
}
