import { num, toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { Info } from 'lucide-react';
import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { formatMoney, formatPct, pnlTone, TONE_TEXT } from '../../../lib/format';
import { AnnotatedCurve } from '../../charts';
import { dayLabel, etToday } from '../../sessions/sessionRows';
import { EmptyState, Pct, SkeletonChart, SkeletonRows, StatList } from '../../ui';
import { LineKey } from '../LineKey';
import { maxDrawdown } from '../sameDates';
import { dayMonthYear, longestRun, monthYear, rangeLabel, runFigures } from '../strategyView';
import { useMediaQuery } from '../useMediaQuery';

import {
  andList,
  findStressPeriods,
  heldGoingIn,
  periodName,
  rebase,
  STRESS_THRESHOLD,
  type HeldGoingIn,
  type HeldGroup,
  type HeldTrade,
  type StressPeriod,
} from './stressPeriods';
import { useFullRun } from './useRuns';
import type { StrategySession } from './useStrategySession';

const STATUS_WORD: Record<BacktestStatus, string> = {
  [BacktestStatus.UNSPECIFIED]: 'Unknown',
  [BacktestStatus.PENDING]: 'Queued',
  [BacktestStatus.RUNNING]: 'Running',
  [BacktestStatus.COMPLETED]: 'Completed',
  [BacktestStatus.FAILED]: 'Failed',
  [BacktestStatus.CANCELLED]: 'Cancelled',
};

/** Runs that start after this miss the 2018 and 2020 falls; price data starts in 2016. */
const LONG_RUN_FROM = Date.UTC(2019, 0, 31);
const DATA_START = '2016-01-04';

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

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Feb 19 to Mar 23, 2020", or across years "Dec 3, 2018 to Jan 2, 2019". */
function periodRange(from: Date, to: Date): string {
  const a = `${MON[from.getUTCMonth()]} ${from.getUTCDate()}`;
  const b = `${MON[to.getUTCMonth()]} ${to.getUTCDate()}, ${to.getUTCFullYear()}`;
  return from.getUTCFullYear() === to.getUTCFullYear()
    ? `${a} to ${b}`
    : `${a}, ${from.getUTCFullYear()} to ${b}`;
}

/** "Feb to Mar 2020", "2022" for a stretch inside one year that runs most of it, "Apr 2025". */
function shortRange(from: Date, to: Date): string {
  const y0 = from.getUTCFullYear();
  const y1 = to.getUTCFullYear();
  const m0 = from.getUTCMonth();
  const m1 = to.getUTCMonth();
  if (y0 === y1 && m1 - m0 >= 6) return String(y0);
  if (y0 === y1 && m0 === m1) return monthYear(from);
  if (y0 === y1) return `${MON[m0]} to ${MON[m1]} ${y1}`;
  return `${monthYear(from)} to ${monthYear(to)}`;
}

const groupText = (g: HeldGroup) => `${andList(g.symbols)} from ${dayLabel(etToday(g.from))}`;

function heldText(h: HeldGoingIn, short = false): string {
  if (h.kind === 'unknown') return 'Not recorded in this run';
  const first = h.kind === 'cash' ? 'Cash' : h.groups.map(groupText).join(' and ');
  if (short || !h.then) return h.kind === 'cash' ? 'Cash' : `Held ${first}`;
  const more = h.more
    ? `, and bought on ${h.more} more ${h.more === 1 ? 'day' : 'days'} before the low`
    : '';
  return `${h.kind === 'cash' ? 'Cash' : first}, then ${groupText(h.then)}${more}`;
}

function backText(p: StressPeriod): string {
  if (p.strategyDrop === 0) return 'Didn’t fall';
  if (p.monthsBack === null) return 'Not yet';
  return `${p.monthsBack} ${p.monthsBack === 1 ? 'month' : 'months'}`;
}

const Drop = ({ v }: { v: number }) => (
  <span className={`num ${TONE_TEXT[pnlTone(v * 100, 1)]}`}>{formatPct(v, { dp: 1 })}</span>
);

interface PerformanceProps {
  strategy: Strategy;
  ss: StrategySession;
  sameRun: BacktestRun | null | undefined;
  runs: readonly BacktestRun[];
  runsLoading: boolean;
}

/** How the longest backtest did in the benchmark's worst stretches (performance2 C). */
export function PerformanceTab({ strategy, ss, runs, runsLoading }: PerformanceProps) {
  const navigate = useNavigate();
  const setConfig = useBacktestStore((s) => s.setConfig);
  const wide = useMediaQuery('(min-width: 768px)');
  const longest = useMemo(() => longestRun(runs, strategy.version), [runs, strategy.version]);
  const full = useFullRun(longest?.id);
  const figures = useMemo(() => runFigures(full), [full]);

  const series = useMemo(() => {
    if (!figures || figures.bench.length !== figures.equity.length || !figures.equity.length) {
      return null;
    }
    const bench = rebase(figures.bench, figures.equity[0]);
    return {
      dates: figures.dates,
      equity: figures.equity,
      bench,
      periods: findStressPeriods(figures.dates, figures.bench, figures.equity),
    };
  }, [figures]);

  const trades: HeldTrade[] | null = useMemo(() => {
    if (!full?.results) return null;
    const out: HeldTrade[] = [];
    for (const t of full.results.trades) {
      const entry = toDate(t.entryTime);
      if (entry) out.push({ symbol: t.symbol, entry, exit: toDate(t.exitTime) });
    }
    return out;
  }, [full]);

  const row = ss.row;
  const modeWord = row?.session.mode === ExecutionMode.LIVE ? 'live' : 'paper';
  const sessionDrop = useMemo(
    () => (ss.curve.status === 'ready' ? maxDrawdown(ss.curve.points.map((p) => p.value)) : null),
    [ss.curve]
  );

  const runFrom2016 = () => {
    const capital = num(full?.config?.initialCapital) || 25000;
    setConfig({
      strategyId: strategy.id,
      strategyVersion: strategy.version,
      startDate: DATA_START,
      endDate: new Date().toISOString().slice(0, 10),
      initialCapital: capital,
    });
    navigate('/backtest');
  };

  const benchSymbol = figures?.benchmarkSymbol || 'SPY';
  const start = figures?.start ?? null;
  const short = start !== null && start.getTime() > LONG_RUN_FROM;

  let body;
  if (runsLoading && runs.length === 0) {
    body = <SkeletonChart height={260} />;
  } else if (!longest) {
    body = (
      <div className="panel">
        <EmptyState
          title="No completed backtest yet"
          body={`Once a backtest finishes, this page shows how it did in the stretches where ${benchSymbol} fell more than 10% from a high.`}
          actions={
            <button type="button" className="btn btn-primary" onClick={runFrom2016}>
              Run from 2016
            </button>
          }
        />
      </div>
    );
  } else if (full === undefined) {
    body = <SkeletonChart height={260} />;
  } else if (!figures || !series) {
    body = (
      <div className="panel px-5 py-4">
        <b className="text-[14px] font-semibold">This run has no benchmark curve</b>
        <p className="m-0 mt-1 text-[13px] text-fg-2">
          The stretches are found from the benchmark’s own curve. Run a backtest with SPY as the
          benchmark to see them.
        </p>
        <button type="button" className="btn btn-primary btn-sm mt-3" onClick={runFrom2016}>
          Run from 2016
        </button>
      </div>
    );
  } else {
    const { periods } = series;
    const name = strategy.name;
    const lastI = series.equity.length - 1;
    body = (
      <>
        <section className="panel min-w-0 px-4 pb-2 pt-4 md:px-5">
          <AnnotatedCurve
            label={`${name} and ${benchSymbol} in the backtest, with the stretches where ${benchSymbol} fell more than 10%`}
            dates={series.dates}
            values={series.equity}
            benchmark={series.bench}
            height={wide ? 190 : 120}
            labelWidth={150}
            bands={periods.map((p) => ({ from: p.start, to: p.trough, tone: 'held' as const }))}
            pins={periods.map((p) => ({
              at: new Date((p.start.getTime() + p.trough.getTime()) / 2),
              label: '',
              count: p.n,
              tone: 'accent' as const,
              guide: false,
            }))}
            side={
              <StatList
                items={[
                  {
                    label: name,
                    value: formatPct(series.equity[lastI] / series.equity[0] - 1, {
                      dp: 1,
                      signed: true,
                    }),
                  },
                  {
                    label: benchSymbol,
                    value: formatPct(series.bench[lastI] / series.bench[0] - 1, {
                      dp: 1,
                      signed: true,
                    }),
                  },
                  { label: 'Worst drop', value: formatPct(figures.maxDrawdown, { dp: 1 }) },
                ]}
              />
            }
            tooltip={(i) => (
              <span className="font-mono text-[11.5px]">
                {dayLabel(etToday(series.dates[i]))}, {series.dates[i].getUTCFullYear()} ·{' '}
                {formatMoney(series.equity[i], { dp: 0 })} vs{' '}
                {formatMoney(series.bench[i], { dp: 0 })}
              </span>
            )}
          />
        </section>

        {periods.length === 0 ? (
          <p className="panel m-0 px-5 py-4 text-[13px] text-fg-2">
            {benchSymbol} didn’t fall more than 10% from a high between{' '}
            {start ? monthYear(start) : 'the run’s start'} and{' '}
            {figures.end ? monthYear(figures.end) : 'its end'}.
          </p>
        ) : wide ? (
          <div className="panel overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-[13px]">
              <thead>
                <tr className="text-left text-[10.5px] uppercase tracking-[0.06em] text-fg-3">
                  <th className="w-12 px-4 py-3 font-medium" aria-label="Number" />
                  <th className="min-w-[190px] px-3 py-3 font-medium">Period</th>
                  <th className="px-3 py-3 text-right font-medium">{benchSymbol}</th>
                  <th className="max-w-[130px] px-3 py-3 text-right font-medium">{name}</th>
                  <th className="px-3 py-3 pl-6 font-medium">What it held going in</th>
                  <th className="whitespace-nowrap px-4 py-3 text-right font-medium">
                    Back to its high
                  </th>
                </tr>
              </thead>
              <tbody>
                {periods.map((p) => (
                  <tr key={p.start.getTime()} className="border-t border-line">
                    <td className="px-4 py-3">
                      <PeriodDot n={p.n} />
                    </td>
                    <td className="px-3 py-3">
                      <span className="block">{periodRange(p.start, p.trough)}</span>
                      {periodName(p.start) && (
                        <span className="block text-[11.5px] text-fg-3">{periodName(p.start)}</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right font-mono">
                      <Drop v={p.benchDrop} />
                    </td>
                    <td className="px-3 py-3 text-right font-mono">
                      <Drop v={p.strategyDrop} />
                    </td>
                    <td className="px-3 py-3 pl-6 text-[12.5px] text-fg-2">
                      {heldText(heldGoingIn(trades, p.start, p.trough))}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-mono">
                      {backText(p)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ol className="m-0 grid list-none gap-2.5 p-0">
            {periods.map((p) => (
              <li key={p.start.getTime()} className="panel grid gap-1.5 px-4 py-3.5">
                <div className="flex items-center gap-2">
                  <PeriodDot n={p.n} />
                  <b className="min-w-0 flex-1 truncate text-[14px] font-semibold">
                    {periodName(p.start) ?? shortRange(p.start, p.trough)}
                  </b>
                  <span className="flex-none text-[11.5px] text-fg-3">
                    {periodName(p.start) ? shortRange(p.start, p.trough) : ''}
                  </span>
                </div>
                <div className="flex justify-between font-mono text-[12.5px]">
                  <span>
                    <span className="text-fg-3">{benchSymbol}</span> <Drop v={p.benchDrop} />
                  </span>
                  <span>
                    <span className="text-fg-3">This</span> <Drop v={p.strategyDrop} />
                  </span>
                </div>
                <span className="text-[11.5px] text-fg-3">
                  {heldText(heldGoingIn(trades, p.start, p.trough), true)}
                </span>
              </li>
            ))}
          </ol>
        )}

        {short && (
          <div className="panel flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
            <p className="m-0 max-w-[680px] text-[13px] text-fg-2">
              The longest run starts in {start ? monthYear(start) : 'a later year'}. Price data goes
              back to 2016, so a longer run includes more of these stretches.
            </p>
            <button type="button" className="btn btn-secondary btn-sm" onClick={runFrom2016}>
              Run from 2016
            </button>
          </div>
        )}

        <p className="m-0 flex items-start gap-2.5 rounded-[10px] border border-line bg-sunk px-4 py-3 text-[12.5px] text-fg-2">
          <Info className="mt-px h-4 w-4 flex-none text-fg-3" aria-hidden="true" />
          <span>
            {row && row.startedAt && sessionDrop !== null ? (
              <>
                These are backtest results. The {modeWord} session started{' '}
                {dayLabel(etToday(row.startedAt))} and its largest drop so far is{' '}
                <b className="font-semibold text-fg">
                  {formatPct(Math.abs(sessionDrop), { dp: 1 })}
                </b>
                .
              </>
            ) : row ? (
              <>These are backtest results. The {modeWord} session’s own drops show on Overview.</>
            ) : (
              <>These are backtest results. This strategy hasn’t run in a session yet.</>
            )}
          </span>
        </p>
      </>
    );
  }

  const sub = figures
    ? [
        `Version ${full?.strategyVersion || strategy.version}`,
        rangeLabel(figures),
        num(full?.config?.initialCapital) > 0
          ? formatMoney(num(full?.config?.initialCapital), { dp: 0 })
          : '',
      ]
        .filter(Boolean)
        .join(', ')
    : '';

  return (
    <div className="grid gap-4">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <h2 className="m-0 text-[15px] font-semibold">
            How the backtest did in the worst stretches for {benchSymbol}
          </h2>
          <p className="m-0 mt-1 text-[12px] text-fg-3">
            {sub ? `${sub} · ` : ''}periods where {benchSymbol} fell more than{' '}
            {Math.round(STRESS_THRESHOLD * 100)}% from a high
          </p>
        </div>
        {series && wide && (
          <span className="flex items-center gap-4">
            <LineKey>{strategy.name}</LineKey>
            <LineKey dashed>{benchSymbol}</LineKey>
          </span>
        )}
      </header>
      {body}
      <section className="mt-3 grid gap-3">
        <b className="text-[15px] font-semibold">All backtests</b>
        <RunsTable strategy={strategy} runs={runs} loading={runsLoading} />
      </section>
    </div>
  );
}

function PeriodDot({ n }: { n: number }) {
  return (
    <b className="grid h-[18px] w-[18px] flex-none place-items-center rounded-full bg-accent font-mono text-[10px] font-semibold text-canvas">
      {n}
    </b>
  );
}
