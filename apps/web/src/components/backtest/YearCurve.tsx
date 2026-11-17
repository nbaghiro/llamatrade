import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useMemo } from 'react';

import { alignTo, monthLabel, type TradeInput } from '../../lib/backtestView';
import { Segmented } from '../ui/Tabs';

import { Panel } from './parts';
import { RunCurve } from './RunCurve';
import { runMeta, toCurve } from './runData';

/** The results curve zoomed to the picked month's year, with the month shaded (months-trades2 A). */
export function YearCurve({
  run,
  trades,
  month,
  strategyName,
  onMonth,
}: {
  run: BacktestRun;
  trades: readonly TradeInput[] | null;
  /** "2025-03"; the year shown is this month's. */
  month: string | null;
  strategyName: string;
  onMonth: (month: string) => void;
}) {
  const full = useMemo(() => {
    const eq = toCurve(run.results?.equityCurve);
    const bench = alignTo(eq.dates, toCurve(run.results?.benchmarkEquityCurve));
    return { ...eq, bench: bench.every((v): v is number => v !== null) ? bench : null };
  }, [run]);

  const years = useMemo(
    () => [...new Set(full.dates.map((d) => String(d.getUTCFullYear())))],
    [full.dates]
  );
  const year = month?.slice(0, 4) ?? years[years.length - 1] ?? '';

  const slice = useMemo(() => {
    const idx = full.dates.flatMap((d, i) => (String(d.getUTCFullYear()) === year ? [i] : []));
    if (idx.length < 2) return null;
    const a = idx[0];
    const b = idx[idx.length - 1] + 1;
    return {
      dates: full.dates.slice(a, b),
      values: full.values.slice(a, b),
      bench: full.bench ? full.bench.slice(a, b) : null,
    };
  }, [full, year]);

  if (!slice) return null;
  const highlight = month
    ? (() => {
        const [y, m] = month.split('-').map(Number);
        return { from: new Date(Date.UTC(y, m - 1, 1)), to: new Date(Date.UTC(y, m, 0)) };
      })()
    : null;
  const firstMonthOf = (y: string) =>
    full.dates
      .find((d) => String(d.getUTCFullYear()) === y)
      ?.toISOString()
      .slice(0, 7) ?? `${y}-01`;

  return (
    <Panel
      title={month ? `${year} · ${monthLabel(month)} shaded` : year}
      aside={
        years.length > 1 ? (
          <Segmented
            label="Year"
            value={year}
            onChange={(y) => onMonth(firstMonthOf(y))}
            options={years.map((y) => ({ key: y, label: y }))}
          />
        ) : undefined
      }
    >
      <div className="px-3.5 py-3">
        <RunCurve
          strategyName={strategyName}
          benchmark={runMeta(run).benchmark}
          dates={slice.dates}
          values={slice.values}
          benchValues={slice.bench}
          trades={trades}
          highlight={highlight}
        />
      </div>
    </Panel>
  );
}
