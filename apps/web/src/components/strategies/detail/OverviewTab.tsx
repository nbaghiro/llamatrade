import { toDate } from '@llamatrade/core/format';
import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import type { Strategy, StrategyVersion } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { useMemo, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, formatPct } from '../../../lib/format';
import { etClock } from '../../../lib/marketClock';
import { nextRebalanceDate } from '../../../lib/sessionState';
import { AnnotatedCurve, type CurveLane } from '../../charts';
import { dayLabel, etToday, type SessionRow } from '../../sessions/sessionRows';
import type { RunningSession } from '../../strategy-builder/hooks/useRunningSession';
import { HOLDING_FILLS } from '../../strategy-builder/outline/holdingFills';
import { sessionHoldings } from '../../strategy-builder/rail/sessionHoldings';
import { StackedBar } from '../../strategy-builder/rail/StackedBar';
import { Money, PanelError, Pct, SkeletonChart, StatList } from '../../ui';
import { holdingWords, holdSentences } from '../holdSentences';
import { maxDrawdown } from '../sameDates';
import { rangeLabel, runFigures } from '../strategyView';

import type { FillDay } from './fills';
import { useSessionSeries } from './useSessionSeries';
import type { StrategySession } from './useStrategySession';

const DAY_MS = 86_400_000;

export function Figure({
  label,
  children,
  sub,
  big,
}: {
  label: string;
  children: ReactNode;
  sub?: ReactNode;
  big?: boolean;
}) {
  return (
    <div className="min-w-0">
      <span className="kicker">{label}</span>
      <div
        className={`mt-1 whitespace-nowrap font-mono font-medium tracking-[-0.02em] ${
          big ? 'text-[28px] sm:text-[32px]' : 'text-[15px]'
        }`}
      >
        {children}
      </div>
      {sub && <div className="mt-0.5 text-[11.5px] text-fg-3">{sub}</div>}
    </div>
  );
}

export function Panel({
  title,
  aside,
  children,
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel min-w-0">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-3.5">
        <h3 className="m-0 text-[13.5px] font-semibold">{title}</h3>
        {aside && <span className="text-[12px] text-fg-3">{aside}</span>}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function fillsLane(days: readonly FillDay[], label: string, next: Date | null): CurveLane {
  return {
    id: 'session',
    label,
    sub: 'Fills by day',
    events: days.map((d) => ({
      at: d.at,
      shape: 'dot' as const,
      count: d.fills.length,
      title: `${dayLabel(d.day)}: ${d.fills.length} ${d.fills.length === 1 ? 'fill' : 'fills'}`,
    })),
    future: next
      ? { events: [{ at: next, shape: 'planned', title: 'Next rebalance' }] }
      : undefined,
  };
}

function HoldsNow({ session }: { session: RunningSession }) {
  const held = useMemo(() => sessionHoldings(session.positions), [session.positions]);
  return (
    <Panel title="Holds now" aside={held.asOf ? etClock(held.asOf) : undefined}>
      {held.holdings.length === 0 ? (
        <p className="m-0 text-[12.5px] text-fg-2">The session holds no positions right now.</p>
      ) : (
        <div className="grid gap-2.5">
          <StackedBar
            label="Session holdings"
            segments={held.holdings.map((h, i) => ({
              key: h.symbol,
              pct: h.pct,
              fill: HOLDING_FILLS[i % HOLDING_FILLS.length],
            }))}
          />
          <div className="flex flex-wrap gap-x-3.5 gap-y-1 font-mono text-[12px] text-fg-2">
            {held.holdings.map((h) => (
              <span key={h.symbol}>
                <b className="font-semibold text-fg">{h.symbol}</b> {h.pct.toFixed(1)}%
              </span>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

function LastFills({ days }: { days: readonly FillDay[] }) {
  const last = days[days.length - 1];
  if (!last) {
    return (
      <Panel title="Fills">
        <p className="m-0 text-[12.5px] text-fg-2">
          No fills yet. The first orders go in at the first rebalance.
        </p>
      </Panel>
    );
  }
  return (
    <Panel title={`Fills on ${dayLabel(last.day)}`} aside={`${last.fills.length} filled`}>
      <ul className="m-0 grid list-none gap-0 p-0">
        {last.fills.slice(0, 5).map((f) => (
          <li
            key={f.id}
            className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-2 border-b border-line py-2 text-[12.5px] last:border-b-0"
          >
            <span className="rounded-[4px] border border-line-strong px-1 text-center font-mono text-[10px] uppercase text-fg-2">
              {f.side}
            </span>
            <span className="truncate">
              {f.quantity.toLocaleString('en-US', { maximumFractionDigits: 4 })} {f.symbol} at{' '}
              {formatMoney(f.price)}
            </span>
            <span className="font-mono">{formatMoney(f.notional)}</span>
          </li>
        ))}
      </ul>
      {last.fills.length > 5 && (
        <p className="m-0 mt-2 text-[12px] text-fg-3">
          {last.fills.length - 5} more in the session.
        </p>
      )}
    </Panel>
  );
}

function VersionNote({
  strategy,
  sessionVersion,
  onDeploy,
}: {
  strategy: Strategy;
  sessionVersion: number | null;
  onDeploy: () => void;
}) {
  if (sessionVersion !== null && strategy.version > sessionVersion) {
    return (
      <Panel title={`Version ${strategy.version} is saved`}>
        <p className="m-0 text-[12.5px] text-fg-2">
          The session keeps running version {sessionVersion} until you stop it and start version{' '}
          {strategy.version}.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link to={`/strategies/${strategy.id}/versions`} className="btn btn-secondary btn-sm">
            Compare versions
          </Link>
          <button type="button" onClick={onDeploy} className="btn btn-primary btn-sm">
            Start version {strategy.version} in paper
          </button>
        </div>
      </Panel>
    );
  }
  return (
    <Panel title="Version">
      <p className="m-0 text-[12.5px] text-fg-2">
        {sessionVersion !== null
          ? `The session runs version ${sessionVersion}, the latest saved.`
          : `Version ${strategy.version || 1} is the latest saved.`}
      </p>
      <Link to={`/strategies/${strategy.id}/versions`} className="btn btn-secondary btn-sm mt-3">
        See versions
      </Link>
    </Panel>
  );
}

function AsWritten({ strategy }: { strategy: Strategy }) {
  const sentences = useMemo(() => {
    const parsed = fromDSLString(strategy.dslCode);
    return parsed ? holdSentences(parsed.tree) : [];
  }, [strategy.dslCode]);
  return (
    <Panel title="What it holds, as written">
      {sentences.length === 0 ? (
        <p className="m-0 text-[12.5px] text-fg-2">The rules can’t be read as an outline.</p>
      ) : (
        <ul className="m-0 grid list-none gap-2 p-0 text-[12.5px] text-fg-2">
          {sentences.slice(0, 3).map((s, i) => (
            <li key={i}>
              {s.when ? `${s.when}: ` : ''}
              <span className="font-mono text-fg">{holdingWords(s.scenario)}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

interface OverviewProps {
  strategy: Strategy;
  ss: StrategySession;
  running: RunningSession;
  /** Undefined while loading, null when there is no completed backtest. */
  latestRun: BacktestRun | null | undefined;
  /** The run that best covers the session's dates, with full results. */
  sameRun: BacktestRun | null | undefined;
  versions: readonly StrategyVersion[];
  onDeploy: () => void;
}

/** The strategy's own curve, annotated (overview2 A). */
export function OverviewTab(props: OverviewProps) {
  return props.ss.row ? (
    <SessionOverview {...props} row={props.ss.row} />
  ) : (
    <BacktestOverview {...props} />
  );
}

function SessionOverview({
  strategy,
  ss,
  running,
  sameRun,
  versions,
  onDeploy,
  row,
}: OverviewProps & { row: SessionRow }) {
  const { daily, same, bench } = useSessionSeries(ss, sameRun);
  const now = new Date();
  const open = row.view.open;
  const live = row.session.mode === ExecutionMode.LIVE;
  const end = open ? now : (toDate(row.session.endedAt) ?? now);
  const next =
    row.state === 'running'
      ? nextRebalanceDate(row.rebalance || strategy.rebalance, etToday(now))
      : null;
  const sessionVersion = running.version ?? (row.version || null);

  const values = daily.map((d) => d.value);
  const start = row.startedAt ?? daily[0]?.at ?? now;
  const fills = ss.days.reduce((s, d) => s + d.fills.length, 0);
  const startedWith =
    row.figures.equity !== null && row.figures.total !== null
      ? row.figures.equity - row.figures.total
      : null;
  const high = values.length ? Math.max(...values) : null;
  const dd = values.length ? maxDrawdown(values) : null;

  const saved = versions
    .map((v) => ({ v: v.version, at: toDate(v.createdAt) }))
    .filter((v): v is { v: number; at: Date } => v.at !== null && v.at > start && v.at <= end);

  const lanes: CurveLane[] = [
    fillsLane(ss.days, live ? 'Live session' : 'Paper session', next),
    {
      id: 'version',
      label: 'Version',
      sub: 'What the session runs',
      spans: [
        {
          from: start,
          style: 'on',
          tone: 'muted',
          label: sessionVersion ? `v${sessionVersion}` : undefined,
        },
      ],
      events: saved.map((s) => ({
        at: s.at,
        shape: 'diamond' as const,
        title: `Version ${s.v} saved`,
        text: `v${s.v} saved ${dayLabel(etToday(s.at))}`,
      })),
      future:
        sessionVersion !== null && strategy.version > sessionVersion
          ? { note: `Start v${strategy.version} to run it` }
          : undefined,
    },
  ];

  const futureEnd = next
    ? new Date(Math.max(next.getTime() + 3 * DAY_MS, now.getTime() + 7 * DAY_MS))
    : new Date(now.getTime() + 14 * DAY_MS);

  return (
    <div className="grid gap-4">
      <section className="panel-rim px-5 pb-2 pt-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-x-8 gap-y-3">
          <div className="flex flex-wrap items-start gap-x-8 gap-y-3">
            <Figure big label={live ? 'Live sleeve' : 'Paper sleeve'}>
              {row.figures.equity !== null ? <Money value={row.figures.equity} /> : '—'}
            </Figure>
            {row.figures.totalPct !== null && row.startedAt && (
              <Figure label={`Since ${dayLabel(etToday(row.startedAt))}`}>
                <Pct value={row.figures.totalPct} pnl dp={1} />
              </Figure>
            )}
            {same && (
              <Figure
                label="Backtest, same dates"
                sub={
                  same.dates.length < daily.length ? `to ${dayLabel(etToday(same.end))}` : undefined
                }
              >
                <Pct value={same.backtest[same.backtest.length - 1]} pnl dp={1} />
              </Figure>
            )}
          </div>
        </div>
        {ss.curve.status === 'loading' || ss.curve.status === 'none' ? (
          <SkeletonChart height={196} />
        ) : ss.curve.status === 'error' ? (
          <PanelError title="The session’s curve couldn’t be loaded" onRetry={ss.retry} />
        ) : (
          <AnnotatedCurve
            label={`${strategy.name} ${live ? 'live' : 'paper'} sleeve since it started`}
            dates={daily.map((d) => d.at)}
            values={values}
            benchmark={bench}
            start={start}
            end={end}
            now={open ? { label: `Now ${etClock(now)}` } : undefined}
            future={
              open
                ? {
                    end: futureEnd,
                    title: next ? 'Until the next rebalance' : 'Next',
                    content: (
                      <div className="grid gap-1 text-[12px] text-fg-2">
                        {next ? (
                          <span>
                            <b className="font-mono text-fg">{dayLabel(next)}</b> Rebalance
                          </span>
                        ) : (
                          <span>
                            {row.rebalance
                              ? `Rebalances ${row.rebalance.toLowerCase()}`
                              : 'On its schedule'}
                          </span>
                        )}
                      </div>
                    ),
                  }
                : undefined
            }
            pins={
              row.startedAt
                ? [
                    {
                      at: row.startedAt,
                      label: sessionVersion
                        ? `Session started on v${sessionVersion}`
                        : 'Session started',
                    },
                  ]
                : []
            }
            side={
              <StatList
                items={[
                  ...(startedWith !== null
                    ? [{ label: 'Started with', value: formatMoney(startedWith) }]
                    : []),
                  ...(high !== null
                    ? [{ label: 'High', value: formatMoney(high, { dp: 0 }) }]
                    : []),
                  ...(dd !== null
                    ? [
                        {
                          label: 'Max drawdown',
                          value: formatPct(dd, { dp: 1 }),
                          tone: dd < 0 ? ('loss' as const) : undefined,
                        },
                      ]
                    : []),
                  { label: 'Days with fills', value: String(ss.days.length) },
                  { label: 'Fills', value: String(fills) },
                ]}
              />
            }
            lanes={lanes}
            legend={[
              { shape: 'dot', label: 'Fills' },
              { shape: 'planned', label: 'Planned' },
              { shape: 'diamond', label: 'Version' },
            ]}
          />
        )}
        {bench && (
          <p className="m-0 mb-2 mt-1 text-[11.5px] text-fg-3">
            The dashed line is a backtest of version {sameRun?.strategyVersion} over the same dates,
            scaled to the session’s starting value.
          </p>
        )}
      </section>
      <div className="grid gap-4 lg:grid-cols-3">
        <HoldsNow session={running} />
        <LastFills days={ss.days} />
        <VersionNote strategy={strategy} sessionVersion={sessionVersion} onDeploy={onDeploy} />
      </div>
    </div>
  );
}

function BacktestOverview({ strategy, latestRun, onDeploy }: OverviewProps) {
  const f = useMemo(() => runFigures(latestRun), [latestRun]);
  if (latestRun === undefined) return <SkeletonChart height={240} />;
  if (!f || f.equity.length < 2) {
    return (
      <div className="grid gap-4">
        <div className="panel flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <span className="text-[13px] text-fg-2">
            Not backtested yet. A backtest shows how it would have done before anything runs.
          </span>
          <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-primary btn-sm">
            Run a backtest
          </Link>
        </div>
        <AsWritten strategy={strategy} />
      </div>
    );
  }
  const last = f.dates[f.dates.length - 1];
  const bench = f.bench.length === f.equity.length ? f.bench : undefined;
  return (
    <div className="grid gap-4">
      <section className="panel-rim px-5 pb-2 pt-4">
        <div className="mb-3 flex flex-wrap items-start gap-x-8 gap-y-3">
          <Figure
            big
            label={`Backtest of version ${latestRun?.strategyVersion || strategy.version}`}
          >
            <Money value={f.equity[f.equity.length - 1]} />
          </Figure>
          <Figure label="Return" sub={rangeLabel(f)}>
            <Pct value={f.totalReturn} pnl dp={1} />
          </Figure>
          {f.benchmarkReturn !== null && (
            <Figure label={`${f.benchmarkSymbol}, same dates`}>
              <Pct value={f.benchmarkReturn} pnl dp={1} />
            </Figure>
          )}
        </div>
        <AnnotatedCurve
          label={`${strategy.name} latest backtest`}
          dates={f.dates}
          values={f.equity}
          benchmark={bench}
          end={last}
          future={{
            end: new Date(
              last.getTime() +
                Math.max(30, (last.getTime() - f.dates[0].getTime()) / DAY_MS / 8) * DAY_MS
            ),
            title: 'Not running',
            content: (
              <div className="grid gap-2 text-[12px] text-fg-2">
                <span>Start it in paper to run it on live prices without real money.</span>
                <button
                  type="button"
                  onClick={onDeploy}
                  className="btn btn-primary btn-sm justify-self-start"
                >
                  Start in paper
                </button>
              </div>
            ),
          }}
          side={
            <StatList
              items={[
                {
                  label: 'CAGR',
                  value: formatPct(f.cagr, { dp: 1, signed: true }),
                  tone: f.cagr >= 0 ? 'gain' : 'loss',
                },
                { label: 'Max drawdown', value: formatPct(f.maxDrawdown, { dp: 1 }), tone: 'loss' },
                { label: 'Sharpe', value: f.sharpe.toFixed(2) },
                { label: 'Starting capital', value: formatMoney(f.equity[0], { dp: 0 }) },
              ]}
            />
          }
          legend={[
            { shape: 'dot', label: strategy.name },
            ...(bench ? [{ shape: 'planned' as const, label: f.benchmarkSymbol }] : []),
          ]}
        />
      </section>
      <div className="grid gap-4 lg:grid-cols-2">
        <AsWritten strategy={strategy} />
        <Panel title="Not running yet">
          <p className="m-0 text-[12.5px] text-fg-2">
            A paper session runs this version on live prices with simulated money on your Alpaca
            paper account. Nothing trades with real money until you choose to.
          </p>
        </Panel>
      </div>
    </div>
  );
}
