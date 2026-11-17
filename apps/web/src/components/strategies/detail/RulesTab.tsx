import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { lazy, Suspense, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatPct } from '../../../lib/format';
import {
  buildOutline,
  longestLookback,
  metaParts,
  rebalanceWord,
  strategySymbols,
} from '../../../lib/outline';
import { nextRebalanceDate } from '../../../lib/sessionState';
import { AnnotatedCurve } from '../../charts';
import { dayLabel, etToday } from '../../sessions/sessionRows';
import { Outline, Parts } from '../../strategy-builder/outline/Outline';
import { Pct, Segmented, Skeleton, SkeletonChart, StatList } from '../../ui';
import { longestRun, rangeLabel, runFigures } from '../strategyView';

import { Panel } from './OverviewTab';
import { useFullRun } from './useRuns';

const DslCodeBlock = lazy(() => import('../DslCodeBlock'));

const VIEWS = [
  { key: 'outline', label: 'Outline' },
  { key: 'code', label: 'Code' },
] as const;

/**
 * Rules (rules2 C, with round one's numbered outline): the longest backtest's curve on top,
 * then the rules as numbered sentences beside what they need.
 */
export function RulesTab({ strategy, runs }: { strategy: Strategy; runs: readonly BacktestRun[] }) {
  const [view, setView] = useState<'outline' | 'code'>('outline');
  const parsed = useMemo(() => fromDSLString(strategy.dslCode), [strategy.dslCode]);
  const lines = useMemo(() => (parsed ? buildOutline(parsed.tree) : []), [parsed]);
  const longest = useMemo(() => longestRun(runs, strategy.version), [runs, strategy.version]);
  const full = useFullRun(longest?.id);
  const f = useMemo(() => runFigures(full), [full]);

  const timeframe = parsed?.metadata.timeframe ?? '1D';
  const benchmark = parsed?.metadata.benchmark ?? '';
  const symbols = parsed ? strategySymbols(parsed.tree, benchmark) : { held: [], signals: [] };
  const lookback = parsed ? longestLookback(parsed.tree) : 0;
  const rebalance = rebalanceWord(timeframe);
  const next = nextRebalanceDate(strategy.rebalance || rebalance, etToday());

  return (
    <div className="grid gap-5">
      {longest && (
        <section className="panel-rim px-5 pb-2 pt-4">
          <span className="kicker">
            Version {full?.strategyVersion || longest.strategyVersion} over its longest backtest
          </span>
          {full === undefined ? (
            <SkeletonChart height={196} />
          ) : !f || f.equity.length < 2 ? (
            <p className="m-0 py-6 text-[13px] text-fg-2">This backtest has no curve to draw.</p>
          ) : (
            <>
              <div className="mb-3 mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <b className="text-[17px] font-semibold">{rangeLabel(f)}</b>
                <span className="font-mono text-[13px]">
                  <Pct value={f.totalReturn} pnl dp={1} />
                </span>
                {f.benchmarkReturn !== null && (
                  <span className="font-mono text-[12.5px] text-fg-3">
                    {f.benchmarkSymbol} {formatPct(f.benchmarkReturn, { dp: 1, signed: true })}
                  </span>
                )}
              </div>
              <AnnotatedCurve
                label={`${strategy.name} over its longest backtest`}
                dates={f.dates}
                values={f.equity}
                benchmark={f.bench.length === f.equity.length ? f.bench : undefined}
                side={
                  <StatList
                    items={[
                      { label: 'Trades', value: String(full?.results?.metrics?.totalTrades ?? 0) },
                      {
                        label: 'Max drawdown',
                        value: formatPct(f.maxDrawdown, { dp: 1 }),
                        tone: 'loss',
                      },
                      { label: 'Sharpe', value: f.sharpe.toFixed(2) },
                    ]}
                  />
                }
                legend={[
                  { shape: 'dot', label: strategy.name },
                  ...(f.bench.length
                    ? [{ shape: 'planned' as const, label: f.benchmarkSymbol }]
                    : []),
                ]}
              />
              <p className="m-0 mb-2 mt-1 text-[11.5px] text-fg-3">
                Backtests don’t record which branch held at each rebalance yet, so the timeline
                shows the curve without the branch band.{' '}
                <Link to={`/backtest/${longest.id}`} className="text-accent hover:underline">
                  Open this backtest
                </Link>
              </p>
            </>
          )}
        </section>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <b className="text-[15px] font-semibold">Version {strategy.version || 1}</b>
            <span className="flex gap-2">
              <Segmented label="Rules view" options={VIEWS} value={view} onChange={setView} />
              <Link to={`/strategies/${strategy.id}/edit`} className="btn btn-secondary btn-sm">
                Edit
              </Link>
            </span>
          </div>
          {view === 'code' || !parsed ? (
            <Suspense fallback={<Skeleton className="h-48 w-full" />}>
              <DslCodeBlock code={strategy.dslCode} className="rounded-panel border border-line" />
            </Suspense>
          ) : (
            <div className="panel px-5 py-4">
              <p className="m-0 mb-4 text-[13.5px] text-fg-2">
                <Parts parts={metaParts({ timeframe, benchmark })} />
              </p>
              <Outline lines={lines} label={`${strategy.name} outline`} />
            </div>
          )}
        </section>
        <Panel title="What the rules need">
          <StatList
            items={[
              { label: 'Symbols held', value: String(symbols.held.length) },
              ...(symbols.signals.length
                ? [{ label: 'Signals read', value: symbols.signals.join(' ') }]
                : []),
              {
                label: 'History before the first rebalance',
                value: lookback ? `${lookback} days` : 'None',
              },
              { label: 'Rebalance', value: rebalance },
              ...(next ? [{ label: 'Next scheduled', value: dayLabel(next) }] : []),
            ]}
          />
          <p className="m-0 mt-3 font-mono text-[11.5px] leading-[1.7] text-fg-2">
            {symbols.held.join(' ')}
          </p>
        </Panel>
      </div>
    </div>
  );
}
