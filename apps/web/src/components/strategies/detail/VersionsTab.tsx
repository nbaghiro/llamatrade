import { toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { useMemo } from 'react';

import { etClock } from '../../../lib/marketClock';
import { tradingDaysBetween } from '../../../lib/marketHolidays';
import { AnnotatedCurve, type CurveLane, type LaneEvent } from '../../charts';
import { dayLabel, etToday } from '../../sessions/sessionRows';
import { rebalanceEvery, rebalanceIndexes } from '../../strategy-builder/blocks/conditionHistory';
import { Money, Pct, SkeletonChart, StatList } from '../../ui';
import { dailyCloses } from '../sameDates';
import type { useVersions } from '../versions/useVersions';
import { VersionsView } from '../versions/VersionsView';

import { Figure } from './OverviewTab';
import type { StrategySession } from './useStrategySession';

const DAY_MS = 86_400_000;

interface VersionsTabProps {
  strategy: Strategy;
  ss: StrategySession;
  sessionVersion: number | null;
  runs: readonly BacktestRun[];
  source: ReturnType<typeof useVersions>;
  onDeploy: () => void;
}

/** Versions on the curve (versions2 A): which version was latest, what the session ran, each backtest. */
export function VersionsTab({
  strategy,
  ss,
  sessionVersion,
  runs,
  source,
  onDeploy,
}: VersionsTabProps) {
  const versions = useMemo(
    () => (source.state.status === 'ready' ? source.state.versions : []),
    [source.state]
  );
  const daily = useMemo(
    () => dailyCloses(ss.curve.status === 'ready' ? ss.curve.points : []),
    [ss.curve]
  );

  const now = new Date();
  const saved = versions
    .map((v) => ({ v, at: toDate(v.createdAt) }))
    .filter((x): x is { v: (typeof versions)[number]; at: Date } => x.at !== null)
    .sort((a, b) => a.at.getTime() - b.at.getTime());
  const row = ss.row;
  const sessionStart = row?.startedAt ?? null;
  const firstAt = Math.min(
    saved[0]?.at.getTime() ?? now.getTime(),
    sessionStart?.getTime() ?? now.getTime()
  );
  const start = new Date(firstAt - Math.max(DAY_MS, (now.getTime() - firstAt) * 0.02));

  const versionSpans = saved.map((s, i) => ({
    from: s.at,
    to: saved[i + 1]?.at,
    style: 'bar' as const,
    tone: s.v.version === strategy.version ? ('accent' as const) : ('muted' as const),
    label: `v${s.v.version}${s.v.changeSummary ? ` · ${s.v.changeSummary}` : ''}`,
  }));

  const runEvents: LaneEvent[] = runs
    .map((r) => ({ r, at: toDate(r.createdAt) }))
    .filter((x): x is { r: BacktestRun; at: Date } => x.at !== null && x.at >= start)
    .map(({ r, at }) => ({
      at,
      shape: 'ring' as const,
      tone: r.status === BacktestStatus.FAILED ? ('risk' as const) : ('muted' as const),
      title: `Backtest of v${r.strategyVersion} on ${dayLabel(etToday(at))}${
        r.status === BacktestStatus.FAILED ? ', failed' : ''
      }`,
    }));

  const live = row?.session.mode === ExecutionMode.LIVE;
  const lanes: CurveLane[] = [
    { id: 'latest', label: 'Latest version', spans: versionSpans },
    ...(row && sessionStart
      ? [
          {
            id: 'session',
            label: `${live ? 'Live' : 'Paper'} session${sessionVersion ? `, v${sessionVersion}` : ''}`,
            spans: [
              {
                from: sessionStart,
                to: toDate(row.session.endedAt) ?? undefined,
                style: row.view.open ? ('on' as const) : ('off' as const),
              },
            ],
            events: ss.days.map((d) => ({
              at: d.at,
              shape: 'ring' as const,
              title: `${dayLabel(d.day)}: ${d.fills.length} fills`,
            })),
          },
        ]
      : []),
    {
      id: 'backtests',
      label: 'Backtests',
      sub: `${runs.length} ${runs.length === 1 ? 'run' : 'runs'}`,
      spans: [],
      events: runEvents,
    },
  ];

  const behind = sessionVersion !== null && strategy.version > sessionVersion;
  const parsed = useMemo(() => fromDSLString(strategy.dslCode), [strategy.dslCode]);
  const every = rebalanceEvery(parsed?.metadata.timeframe ?? '1D');
  const sessionDays = sessionStart
    ? tradingDaysBetween(etToday(sessionStart), etToday(now)) + 1
    : 0;
  const rebalances = rebalanceIndexes(
    daily.map((d) => d.at),
    every
  ).length;
  const whileItRan =
    row && sessionVersion && daily.length > 1 ? (
      <div className="grid gap-1.5 text-[12px]">
        <span className="text-fg-3">While it ran</span>
        <span className="font-mono">
          v{sessionVersion}{' '}
          {row.figures.totalPct !== null && <Pct value={row.figures.totalPct} pnl dp={1} />}{' '}
          <span className="text-fg-3">{sessionDays} days</span>
        </span>
        <StatList
          className="mt-2"
          items={[
            ...(sessionStart
              ? [
                  {
                    label: `${live ? 'Live' : 'Paper'} since`,
                    value: dayLabel(etToday(sessionStart)),
                  },
                ]
              : []),
            { label: `Rebalances on v${sessionVersion}`, value: String(rebalances) },
          ]}
        />
        <span className="mt-1 text-[11.5px] leading-[1.5] text-fg-3">
          Sessions keep the version they started with, so other versions have no paper record.
        </span>
      </div>
    ) : undefined;

  return (
    <div className="grid gap-6">
      <section className="panel-rim px-5 pb-2 pt-4">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-4">
          {row ? (
            <Figure
              big
              label={`${live ? 'Live' : 'Paper'} session${sessionVersion ? `, run on version ${sessionVersion}` : ''}`}
              sub={
                row.figures.totalPct !== null && sessionStart ? (
                  <>
                    <Pct value={row.figures.totalPct} pnl dp={1} /> since{' '}
                    {dayLabel(etToday(sessionStart))}
                  </>
                ) : undefined
              }
            >
              {row.figures.equity !== null ? <Money value={row.figures.equity} /> : '—'}
            </Figure>
          ) : (
            <Figure label="Saved versions">{versions.length}</Figure>
          )}
          {behind && (
            <div className="flex max-w-[460px] flex-wrap items-center gap-3 rounded-panel bg-accent-soft px-4 py-3 text-[12.5px] text-fg-2">
              <span className="min-w-0 flex-1">
                Version {strategy.version} is the latest. The session still runs version{' '}
                {sessionVersion} and keeps it until you stop it.
              </span>
              <button type="button" onClick={onDeploy} className="btn btn-primary btn-sm">
                Start version {strategy.version} in paper
              </button>
            </div>
          )}
        </div>
        {source.state.status === 'loading' || (row && ss.curve.status === 'loading') ? (
          <SkeletonChart height={196} />
        ) : (
          <AnnotatedCurve
            label={`${strategy.name} versions over time`}
            dates={daily.map((d) => d.at)}
            values={daily.map((d) => d.value)}
            start={start}
            end={now}
            height={daily.length > 1 ? 196 : 56}
            now={{ label: `Now ${etClock(now)}` }}
            lanes={lanes}
            side={
              daily.length > 1 ? (
                whileItRan
              ) : (
                <p className="m-0 text-[12px] text-fg-3">
                  No session has run yet, so there is no curve to draw.
                </p>
              )
            }
            legend={[
              { shape: 'ring', label: 'Rebalance or run' },
              { shape: 'ring', tone: 'risk', label: 'Failed' },
            ]}
          />
        )}
      </section>
      <VersionsView
        strategyId={strategy.id}
        strategyName={strategy.name}
        sessionVersion={sessionVersion}
        source={source}
      />
    </div>
  );
}
