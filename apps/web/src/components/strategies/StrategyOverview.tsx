import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { useMemo, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { writtenScenarios } from '../../lib/outline';
import { LineChart } from '../charts';
import type { RunningSession } from '../strategy-builder/hooks/useRunningSession';
import { HOLDING_FILLS } from '../strategy-builder/outline/holdingFills';
import { sessionHoldings } from '../strategy-builder/rail/sessionHoldings';
import { StackedBar } from '../strategy-builder/rail/StackedBar';
import { AttentionLine, Pct, Skeleton, SkeletonChart, StatusMark, type RunState } from '../ui';

import { rangeLabel, runFigures, type RunFigures } from './strategyView';

function Figure({ label, children, sub }: { label: string; children: ReactNode; sub?: string }) {
  return (
    <div className="min-w-0 border-l border-line px-4 first:border-l-0 first:pl-0 max-sm:odd:border-l-0 max-sm:odd:pl-0">
      <span className="kicker">{label}</span>
      <div className="mt-1 whitespace-nowrap font-mono text-[18px] font-medium tracking-[-0.02em] sm:text-[20px]">
        {children}
      </div>
      {sub && <div className="mt-px whitespace-nowrap font-mono text-[11px] text-fg-3">{sub}</div>}
    </div>
  );
}

function Figures({ f }: { f: RunFigures }) {
  const bench =
    f.benchmarkReturn !== null
      ? `${f.benchmarkSymbol} ${f.benchmarkReturn > 0 ? '+' : ''}${(f.benchmarkReturn * 100).toFixed(1)}%`
      : undefined;
  return (
    <div className="grid grid-cols-2 gap-y-4 sm:grid-cols-4">
      <Figure label="Return" sub={bench}>
        <Pct value={f.totalReturn} pnl dp={1} />
      </Figure>
      <Figure label="CAGR">
        <Pct value={f.cagr} pnl dp={1} />
      </Figure>
      <Figure label="Max drawdown">
        <Pct value={f.maxDrawdown} pnl dp={1} />
      </Figure>
      <Figure label="Sharpe">
        <span className="num">{f.sharpe.toFixed(2)}</span>
      </Figure>
    </div>
  );
}

const fmtTime = (d: Date) =>
  d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

function HoldsNow({ session }: { session: RunningSession }) {
  const held = useMemo(() => sessionHoldings(session.positions), [session.positions]);
  return (
    <section className="panel">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h3 className="m-0 text-[13px] font-semibold">Holds now</h3>
        {held.asOf && <span className="text-[12px] text-fg-3">as of {fmtTime(held.asOf)}</span>}
      </header>
      <div className="grid gap-2.5 px-4 py-3">
        {session.loading ? (
          <Skeleton className="h-2 w-full" />
        ) : !session.session ? (
          <p className="m-0 text-[12.5px] text-fg-2">Not running in paper.</p>
        ) : held.holdings.length === 0 ? (
          <p className="m-0 text-[12.5px] text-fg-2">The session holds no positions right now.</p>
        ) : (
          <>
            <StackedBar
              label="Session holdings"
              segments={held.holdings.map((h, i) => ({
                key: h.symbol,
                pct: h.pct,
                fill: HOLDING_FILLS[i % 5],
              }))}
            />
            <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-[12px] text-fg-2">
              {held.holdings.map((h) => (
                <span key={h.symbol}>
                  <b className="font-mono font-semibold text-fg">{h.symbol}</b> {h.pct.toFixed(1)}%
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function AsWritten({ dsl }: { dsl: string }) {
  const scenarios = useMemo(() => {
    const parsed = dsl ? fromDSLString(dsl) : null;
    return parsed ? writtenScenarios(parsed.tree) : [];
  }, [dsl]);
  return (
    <section className="panel">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h3 className="m-0 text-[13px] font-semibold">As written</h3>
        <span className="text-[12px] text-fg-3">structural estimate</span>
      </header>
      <div className="grid gap-3 px-4 py-3">
        {scenarios.length === 0 && <Skeleton className="h-2 w-full" />}
        {scenarios.slice(0, 2).map((s) => (
          <div key={s.label} className="grid gap-2">
            {scenarios.length > 1 && <span className="kicker">{s.label}</span>}
            <StackedBar
              label={s.label}
              segments={s.holdings
                .filter((h) => h.pct !== null)
                .map((h, i) => ({ key: h.symbol, pct: h.pct ?? 0, fill: HOLDING_FILLS[i % 5] }))}
            />
            <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-[12px] text-fg-2">
              {s.holdings.map((h) => (
                <span key={h.symbol}>
                  <b className="font-mono font-semibold text-fg">{h.symbol}</b>{' '}
                  {h.pct === null ? 'ranked' : `${h.pct.toFixed(1)}%`}
                </span>
              ))}
            </div>
          </div>
        ))}
        {scenarios.length > 2 && (
          <span className="text-[12px] text-fg-3">
            {scenarios.length - 2} more branches in the definition.
          </span>
        )}
      </div>
    </section>
  );
}

interface HeaderProps {
  strategy: Strategy;
  state: RunState;
  stateLabel?: string;
  meta: string;
  headingLevel?: 'h1' | 'h2';
}

/** Name, state, version line and the two actions every strategy view offers. */
export function StrategyHeader({
  strategy,
  state,
  stateLabel,
  meta,
  headingLevel = 'h2',
}: HeaderProps) {
  const H = headingLevel;
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-3">
          <H className="m-0 text-[22px] font-semibold leading-tight tracking-[-0.015em]">
            {strategy.name}
          </H>
          <StatusMark state={state} label={stateLabel} />
        </div>
        <p className="m-0 mt-1 text-[12px] text-fg-3">{meta}</p>
      </div>
      <div className="flex gap-2">
        <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-secondary">
          Backtest
        </Link>
        <Link to={`/strategies/${strategy.id}/edit`} className="btn btn-primary">
          Edit
        </Link>
      </div>
    </div>
  );
}

interface BodyProps {
  strategy: Strategy;
  state: RunState;
  /** undefined while loading, null when there is no completed backtest. */
  run: BacktestRun | null | undefined;
  session: RunningSession;
}

/** The latest backtest, what the session holds now and what the strategy holds as written. */
export function StrategyOverviewBody({ strategy, state, run, session }: BodyProps) {
  const figures = useMemo(() => runFigures(run), [run]);
  const attention =
    state === 'error'
      ? [
          {
            id: 'error',
            title: 'The paper session stopped with an error.',
            detail: 'Nothing trades for this strategy until the session is looked at.',
            action: session.session ? (
              <Link to={`/trading/${session.session.id}`} className="btn btn-secondary btn-sm">
                Review
              </Link>
            ) : undefined,
          },
        ]
      : [];

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
      <AttentionLine items={attention} />

      {run === undefined ? (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4" aria-busy="true">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="grid gap-2">
                <Skeleton className="h-2.5 w-16" />
                <Skeleton className="h-6 w-20" />
              </div>
            ))}
          </div>
          <SkeletonChart height={130} />
        </div>
      ) : figures ? (
        <>
          <Figures f={figures} />
          {figures.equity.length > 1 && (
            <div>
              <div className="mb-1.5 flex flex-wrap gap-4 text-[12px] text-fg-2">
                <span className="flex items-center gap-1.5">
                  <i className="h-0.5 w-3.5 bg-accent" />
                  {strategy.name}
                </span>
                {figures.bench.length > 1 && (
                  <span className="flex items-center gap-1.5">
                    <i className="h-0 w-3.5 border-t border-dashed border-fg-3" />
                    {figures.benchmarkSymbol}
                  </span>
                )}
                <span className="text-fg-3">{rangeLabel(figures)}</span>
              </div>
              <LineChart
                label={`${strategy.name} equity over the latest backtest`}
                height={130}
                dates={figures.dates}
                series={[
                  { values: figures.equity, kind: 'main', area: true, label: strategy.name },
                  ...(figures.bench.length > 1
                    ? [
                        {
                          values: figures.bench,
                          kind: 'bench' as const,
                          label: figures.benchmarkSymbol,
                        },
                      ]
                    : []),
                ]}
                yFormat={(v) => `$${Math.round(v / 1000)}k`}
              />
            </div>
          )}
        </>
      ) : (
        <div className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-3.5">
          <span className="text-[13px] text-fg-2">
            Not backtested yet. A backtest shows how it would have done before anything runs.
          </span>
          <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-secondary btn-sm">
            Run a backtest
          </Link>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <HoldsNow session={session} />
        <AsWritten dsl={strategy.dslCode} />
      </div>
    </div>
  );
}

/** The overview used on the split list: header and body together. */
export function StrategyOverview(props: HeaderProps & BodyProps) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
      <StrategyHeader {...props} />
      <StrategyOverviewBody {...props} />
    </div>
  );
}
