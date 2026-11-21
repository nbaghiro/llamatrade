import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useMemo } from 'react';

import type { TradeInput } from '../../lib/backtestView';
import { pctAt } from '../../lib/chart/timeScale';
import { Pct } from '../ui/Num';

import { Panel } from './parts';
import { RunCurve } from './RunCurve';
import { runMeta } from './runData';
import { monthBounds, periodReturn, sliceYear, yearMonths, type YearSlice } from './yearView';

/** Matches RunCurve's label column, so the month rows sit under the curve's months. */
const LABEL_W = 112;

/** The results curve zoomed to one year, the picked month shaded, monthly returns under it. */
export function YearCurve({
  run,
  full,
  trades,
  year,
  month,
  strategyName,
}: {
  run: BacktestRun;
  full: YearSlice;
  trades: readonly TradeInput[] | null;
  year: string;
  /** "2025-03", shaded on the curve. */
  month: string | null;
  strategyName: string;
}) {
  const slice = useMemo(() => sliceYear(full, year), [full, year]);
  const bench = runMeta(run).benchmark;
  const reported = run.results?.monthlyReturns;

  const rows = useMemo(
    () =>
      yearMonths(year).map((m) => {
        const { from, to } = monthBounds(m);
        return {
          month: m,
          mid: new Date((from.getTime() + to.getTime()) / 2),
          own: reported?.[m] ?? periodReturn(full.dates, full.values, from, to),
          bench: full.bench ? periodReturn(full.dates, full.bench, from, to) : null,
        };
      }),
    [year, reported, full]
  );

  if (!slice) {
    return (
      <Panel title={year}>
        <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
          This run has fewer than two closes in {year}.
        </p>
      </Panel>
    );
  }
  const start = slice.dates[0];
  const end = slice.dates[slice.dates.length - 1];
  const highlight = month && month.startsWith(year) ? monthBounds(month) : null;
  const shortName = `v${run.strategyVersion}`;

  const row = (label: string, pick: (r: (typeof rows)[number]) => number | null) => (
    <div
      className="grid h-[22px] items-center"
      style={{ gridTemplateColumns: `${LABEL_W}px minmax(0,1fr)` }}
    >
      <span className="text-[11px] text-fg-3">{label}</span>
      <span className="relative h-full">
        {rows.map((r) => {
          const v = pick(r);
          if (r.mid.getTime() < start.getTime() - 15 * 86_400_000) return null;
          if (r.mid.getTime() > end.getTime() + 15 * 86_400_000) return null;
          return (
            <span
              key={r.month}
              className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 text-[11px] ${
                r.month === month ? 'font-semibold' : ''
              }`}
              style={{ left: pctAt(r.mid, start, end) }}
            >
              {v === null ? <span className="text-fg-3">·</span> : <Pct value={v} pnl dp={1} />}
            </span>
          );
        })}
      </span>
    </div>
  );

  return (
    <Panel title={year}>
      <div className="px-3.5 py-3">
        <RunCurve
          strategyName={strategyName}
          benchmark={bench}
          dates={slice.dates}
          values={slice.values}
          benchValues={slice.bench}
          trades={trades}
          highlight={highlight}
        />
        <div
          className="mt-2 hidden border-t border-line pt-1 md:block"
          aria-label="Monthly returns"
        >
          {row(`Month, ${shortName}`, (r) => r.own)}
          {full.bench && bench ? row(`Month, ${bench}`, (r) => r.bench) : null}
        </div>
      </div>
    </Panel>
  );
}
