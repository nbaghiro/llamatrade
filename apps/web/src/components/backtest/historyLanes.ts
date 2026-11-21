import {
  BacktestStatus,
  type BacktestMetrics,
  type BacktestRun,
} from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';

import type { RebalanceFrequency } from '../../lib/backtestView';

import { scheduleFor } from './annotations';
import type { StrategyRow, TimelineRun } from './historyTimeline';
import { runMeta } from './runData';
import { latestSession, type StrategySession } from './strategySessions';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const shortDay = (d: Date) => `${MON[d.getMonth()]} ${d.getDate()}`;

const done = (r: TimelineRun) => r.run.status === BacktestStatus.COMPLETED;

/** Two runs used the same dates, capital and benchmark, as far as the list carries them. */
export function sameSettings(
  a: BacktestRun,
  b: BacktestRun,
  metrics: Readonly<Record<string, BacktestMetrics>> = {}
): boolean {
  const day = (r: BacktestRun, k: 'startDate' | 'endDate') =>
    toDate(r.config?.[k])?.toISOString().slice(0, 10) ?? '';
  const bench = (r: BacktestRun) =>
    r.config?.benchmarkSymbol || metrics[r.id]?.benchmarkSymbol || '';
  return (
    day(a, 'startDate') !== '' &&
    day(a, 'startDate') === day(b, 'startDate') &&
    day(a, 'endDate') === day(b, 'endDate') &&
    toNumber(a.config?.initialCapital) === toNumber(b.config?.initialCapital) &&
    bench(a) === bench(b)
  );
}

/** The newest completed run of each version, oldest version first. */
export function versionResults(row: StrategyRow): TimelineRun[] {
  const by = new Map<number, TimelineRun>();
  for (const r of row.runs) if (done(r)) by.set(r.run.strategyVersion, r);
  return [...by.values()].sort((a, b) => a.run.strategyVersion - b.run.strategyVersion);
}

export interface AheadOf {
  /** Total return of the latest run minus the earlier version's, in percentage points. */
  points: number;
  version: number;
}

/**
 * How the latest finished run compares with the newest finished run of an earlier version on
 * identical settings; null when no earlier version ran the same settings.
 */
export function aheadOfPrevious(
  row: StrategyRow,
  metrics: Readonly<Record<string, BacktestMetrics>>
): AheadOf | null {
  const latest = row.latestCompleted;
  if (!latest || !metrics[latest.run.id]) return null;
  const earlier = row.runs
    .filter(
      (r) =>
        done(r) &&
        r.run.strategyVersion < latest.run.strategyVersion &&
        metrics[r.run.id] &&
        sameSettings(r.run, latest.run, metrics)
    )
    .sort(
      (a, b) => b.run.strategyVersion - a.run.strategyVersion || b.at.getTime() - a.at.getTime()
    )[0];
  if (!earlier) return null;
  return {
    points:
      (toNumber(metrics[latest.run.id].totalReturn) -
        toNumber(metrics[earlier.run.id].totalReturn)) *
      100,
    version: earlier.run.strategyVersion,
  };
}

/** "Paper from v3", "Live from v2", "Stopped Nov 12". */
export function sessionBarLabel(s: StrategySession): string {
  if (!s.active && s.stoppedAt) return `Stopped ${shortDay(s.stoppedAt)}`;
  return `${s.mode === 'live' ? 'Live' : 'Paper'} from v${s.version}`;
}

/** "4 versions · paper session runs v3", "session stopped Nov 12" or "not run as a session". */
export function laneSubtitle(row: StrategyRow, session: StrategySession | null): string {
  const versions = `${row.versions} ${row.versions === 1 ? 'version' : 'versions'}`;
  if (!session) return `${versions} · not run as a session`;
  if (!session.active) {
    return `${versions} · session stopped${session.stoppedAt ? ` ${shortDay(session.stoppedAt)}` : ''}`;
  }
  return `${versions} · ${session.mode} session runs v${session.version}`;
}

export interface NewerThanTrading {
  session: StrategySession;
  /** The newest run of a version above the one the session trades. */
  newer: TimelineRun;
  /** The newest finished run of the version the session trades, if there is one. */
  trading: TimelineRun | null;
  /** Both finished on identical settings: newer's return minus trading's, in points. */
  points: number | null;
}

/** A run of a newer version than the active session trades, finished or in flight. */
export function newerThanTrading(
  row: StrategyRow,
  sessions: readonly StrategySession[],
  metrics: Readonly<Record<string, BacktestMetrics>>
): NewerThanTrading | null {
  const session = latestSession(sessions, row.strategyId);
  if (!session?.active) return null;
  const live = (r: TimelineRun) =>
    r.run.status === BacktestStatus.COMPLETED ||
    r.run.status === BacktestStatus.RUNNING ||
    r.run.status === BacktestStatus.PENDING;
  const newer = [...row.runs]
    .reverse()
    .find((r) => r.run.strategyVersion > session.version && live(r));
  if (!newer) return null;
  const trading =
    [...row.runs].reverse().find((r) => done(r) && r.run.strategyVersion === session.version) ??
    null;
  const points =
    trading &&
    done(newer) &&
    metrics[newer.run.id] &&
    metrics[trading.run.id] &&
    sameSettings(newer.run, trading.run, metrics)
      ? (toNumber(metrics[newer.run.id].totalReturn) -
          toNumber(metrics[trading.run.id].totalReturn)) *
        100
      : null;
  return { session, newer, trading, points };
}

/** "28 of 70 rebalances" through the simulated date, for calendar schedules; null otherwise. */
export function rebalancesThrough(
  run: BacktestRun,
  rebalance: RebalanceFrequency | null
): { passed: number; total: number } | null {
  const meta = runMeta(run);
  const schedule = scheduleFor(meta.start, meta.end, rebalance);
  if (!schedule.length || !run.currentDate) return null;
  const through = new Date(`${run.currentDate}T00:00:00Z`).getTime();
  if (Number.isNaN(through)) return null;
  return {
    passed: schedule.filter((d) => d.getTime() <= through).length,
    total: schedule.length,
  };
}

/** "Nov 12", the day a run finished or was made. */
export function runDay(run: BacktestRun): string {
  const d = toDate(run.completedAt) ?? toDate(run.createdAt);
  return d ? shortDay(d) : '·';
}
