import { num, toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatNumber, formatPct } from '../../../lib/format';
import { AnnotatedCurve, LaneMarker } from '../../charts';
import { dayLabel, etToday } from '../../sessions/sessionRows';
import {
  EmptyState,
  PanelError,
  Pct,
  Segmented,
  SkeletonChart,
  SkeletonRows,
  StatList,
} from '../../ui';
import { gapSteps } from '../sameDates';
import { dayMonthYear, rangeLabel } from '../strategyView';

import { Figure } from './OverviewTab';
import { useSessionSeries } from './useSessionSeries';
import type { StrategySession } from './useStrategySession';

const STATUS_WORD: Record<BacktestStatus, string> = {
  [BacktestStatus.UNSPECIFIED]: 'Unknown',
  [BacktestStatus.PENDING]: 'Queued',
  [BacktestStatus.RUNNING]: 'Running',
  [BacktestStatus.COMPLETED]: 'Completed',
  [BacktestStatus.FAILED]: 'Failed',
  [BacktestStatus.CANCELLED]: 'Cancelled',
};

const pts = (v: number, signed = true) => `${formatNumber(v, { dp: 2, signed })} pts`;

/** Every backtest of the strategy, newest first. */
export function RunsTable({
  strategy,
  runs,
  loading,
}: {
  strategy: Strategy;
  runs: readonly BacktestRun[];
  loading: boolean;
}) {
  if (loading && runs.length === 0) {
    return (
      <div className="panel">
        <SkeletonRows rows={4} cols={4} />
      </div>
    );
  }
  if (runs.length === 0) {
    return (
      <div className="panel">
        <EmptyState
          title="No backtests yet"
          body="A backtest shows how this strategy would have done before anything runs."
          actions={
            <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-primary">
              Run a backtest
            </Link>
          }
        />
      </div>
    );
  }
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-[11.5px] text-fg-3">
            <th className="px-4 py-2.5 font-medium">Run</th>
            <th className="px-4 py-2.5 font-medium">Version</th>
            <th className="px-4 py-2.5 font-medium">Range</th>
            <th className="px-4 py-2.5 font-medium">State</th>
            <th className="px-4 py-2.5 text-right font-medium">Return</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const when = toDate(r.completedAt) ?? toDate(r.createdAt);
            const range = rangeLabel({
              start: toDate(r.config?.startDate),
              end: toDate(r.config?.endDate),
            });
            const total = r.results?.metrics ? num(r.results.metrics.totalReturn) : null;
            const failed = r.status === BacktestStatus.FAILED;
            return (
              <tr key={r.id} className="border-t border-line hover:bg-sunk/60">
                <td className="px-4 py-2.5">
                  <Link
                    to={`/backtest/${r.id}`}
                    className="text-fg hover:text-accent hover:underline"
                  >
                    {when ? dayMonthYear(when) : r.id.slice(0, 8)}
                  </Link>
                </td>
                <td className="num px-4 py-2.5 text-fg-2">{r.strategyVersion || ''}</td>
                <td className="px-4 py-2.5 text-fg-2">{range}</td>
                <td className={`px-4 py-2.5 ${failed ? 'text-risk' : 'text-fg-2'}`}>
                  {STATUS_WORD[r.status]}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {total === null ? '' : <Pct value={total} pnl dp={1} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface PerformanceProps {
  strategy: Strategy;
  ss: StrategySession;
  sameRun: BacktestRun | null | undefined;
  runs: readonly BacktestRun[];
  runsLoading: boolean;
}

/** Paper against a backtest over the same dates, the gap drawn and stepped (performance2 A). */
export function PerformanceTab({ strategy, ss, sameRun, runs, runsLoading }: PerformanceProps) {
  const [view, setView] = useState<'gap' | 'both'>('gap');
  const { same } = useSessionSeries(ss, sameRun);
  const steps = useMemo(
    () =>
      same
        ? gapSteps(
            same,
            ss.days.map((d) => d.day)
          )
        : null,
    [same, ss.days]
  );
  const row = ss.row;
  const modeWord = row?.session.mode === ExecutionMode.LIVE ? 'Live' : 'Paper';

  let top;
  if (!row) {
    top = (
      <div className="panel">
        <EmptyState
          title="Not running yet"
          body="Once a paper session runs this strategy, this page compares it with a backtest over the same dates."
        />
      </div>
    );
  } else if (ss.curve.status === 'error') {
    top = <PanelError title="The session’s curve couldn’t be loaded" onRetry={ss.retry} />;
  } else if (ss.curve.status !== 'ready' || sameRun === undefined) {
    top = <SkeletonChart height={240} />;
  } else if (!same || !steps) {
    const from = row.startedAt ? dayLabel(etToday(row.startedAt)) : 'the session’s start';
    top = (
      <div className="panel px-5 py-4">
        <b className="text-[14px] font-semibold">No backtest covers the session’s dates yet</b>
        <p className="m-0 mt-1 text-[13px] text-fg-2">
          Run a backtest from {from} to today to compare the {modeWord.toLowerCase()} session with
          what the rules did on the same prices.
        </p>
        <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-primary btn-sm mt-3">
          Run a backtest
        </Link>
      </div>
    );
  } else {
    const lastI = same.dates.length - 1;
    const runStart = toDate(sameRun?.config?.startDate);
    const sameCapital =
      row.figures.equity !== null &&
      row.figures.total !== null &&
      Math.abs(num(sameRun?.config?.initialCapital) - (row.figures.equity - row.figures.total)) < 1;
    top = (
      <>
        <section className="panel grid grid-cols-2 gap-x-6 gap-y-4 px-5 py-4 md:grid-cols-4">
          <Figure
            label={`${modeWord} session${row.version ? `, v${row.version}` : ''}`}
            sub={`${dayLabel(etToday(same.start))} to ${dayLabel(etToday(same.end))}`}
          >
            <Pct value={same.paper[lastI]} pnl dp={1} />
          </Figure>
          <Figure
            label="Backtest, same dates"
            sub={`version ${sameRun?.strategyVersion ?? ''}${sameCapital ? ', same capital' : ''}`}
          >
            <Pct value={same.backtest[lastI]} dp={1} signed />
          </Figure>
          <Figure label="Gap" sub="paper minus backtest">
            <span
              className={same.gap[lastI] < 0 ? 'text-loss' : same.gap[lastI] > 0 ? 'text-gain' : ''}
            >
              {pts(same.gap[lastI])}
            </span>
          </Figure>
          <Figure
            label="Compared"
            sub={runStart && runStart > same.start ? 'from the backtest’s start' : 'trading days'}
          >
            {same.dates.length} days
          </Figure>
        </section>

        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          <section className="panel min-w-0 px-5 pb-2 pt-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
              <span className="text-[12px] text-fg-3">
                {view === 'gap'
                  ? 'Paper minus backtest, in percentage points'
                  : 'Return since the first shared day'}
              </span>
              <Segmented
                label="Chart"
                options={[
                  { key: 'gap', label: 'Gap' },
                  { key: 'both', label: 'Both curves' },
                ]}
                value={view}
                onChange={setView}
              />
            </div>
            <AnnotatedCurve
              key={view}
              label={
                view === 'gap' ? 'Gap between paper and backtest' : 'Paper and backtest returns'
              }
              dates={same.dates}
              values={view === 'gap' ? same.gap : same.paper.map((v) => v * 100)}
              benchmark={view === 'gap' ? same.gap.map(() => 0) : same.backtest.map((v) => v * 100)}
              area={view !== 'gap'}
              labelWidth={150}
              side={
                <StatList
                  items={[
                    {
                      label: 'Paper',
                      value: formatPct(same.paper[lastI], { dp: 1, signed: true }),
                    },
                    {
                      label: 'Backtest',
                      value: formatPct(same.backtest[lastI], { dp: 1, signed: true }),
                    },
                    { label: 'Gap', value: pts(same.gap[lastI]) },
                  ]}
                />
              }
              lanes={[
                {
                  id: 'steps',
                  label: 'Days with fills',
                  events: steps.steps.map((s, i) => ({
                    at: s.at,
                    shape: 'dot' as const,
                    count: i + 1,
                    title: `${dayLabel(etToday(s.at))}: ${pts(s.change)}`,
                  })),
                },
              ]}
              tooltip={(i) => (
                <span className="font-mono text-[11.5px]">
                  {dayLabel(etToday(same.dates[i]))} ·{' '}
                  {view === 'gap'
                    ? pts(same.gap[i])
                    : `${formatNumber(same.paper[i] * 100, { dp: 2, signed: true })}% vs ${formatNumber(same.backtest[i] * 100, { dp: 2, signed: true })}%`}
                </span>
              )}
            />
          </section>

          <section className="panel">
            <header className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-3.5">
              <h3 className="m-0 text-[13.5px] font-semibold">Where the gap moved</h3>
              <span className="font-mono text-[12px] text-fg-2">{pts(steps.total)}</span>
            </header>
            <ol className="m-0 list-none p-0">
              {steps.steps.map((s, i) => (
                <li
                  key={s.at.getTime()}
                  className="grid grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-line px-5 py-2.5 text-[12.5px]"
                >
                  <LaneMarker shape="dot" count={i + 1} />
                  <span>
                    {dayLabel(etToday(s.at))}
                    {i === 0 ? ', first orders' : ', fills'}
                  </span>
                  <span
                    className={`font-mono ${s.change > 0 ? 'text-gain' : s.change < 0 ? 'text-loss' : ''}`}
                  >
                    {pts(s.change)}
                  </span>
                </li>
              ))}
              <li className="grid grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-2.5 px-5 py-2.5 text-[12.5px]">
                <LaneMarker shape="muted" />
                <span>Between days with fills</span>
                <span className="font-mono">{pts(steps.between)}</span>
              </li>
            </ol>
            <p className="m-0 border-t border-line px-5 py-3 text-[11.5px] text-fg-3">
              Each step is how much the gap moved on a day with fills. Causes such as fill timing,
              fees and cash kept back aren’t broken out yet, and a gap from orders placed in Alpaca
              directly shows up here too.
            </p>
          </section>
        </div>
      </>
    );
  }

  return (
    <div className="grid gap-5">
      {top}
      <section className="grid gap-3">
        <b className="text-[15px] font-semibold">All backtests</b>
        <RunsTable strategy={strategy} runs={runs} loading={runsLoading} />
      </section>
    </div>
  );
}
