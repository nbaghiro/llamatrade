import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate } from '@llamatrade/core/stores/backtest';

export interface TimelineRun {
  run: BacktestRun;
  at: Date;
}

export interface StrategyRow {
  strategyId: string;
  /** Oldest first. */
  runs: TimelineRun[];
  latest: TimelineRun;
  latestCompleted: TimelineRun | null;
  versions: number;
}

/** When a run was made: its creation time, or when it finished if that's all it has. */
export function runAt(run: BacktestRun): Date | null {
  return toDate(run.createdAt) ?? toDate(run.completedAt) ?? toDate(run.startedAt);
}

/** One row per strategy, the strategy with the newest run first. */
export function strategyRows(runs: readonly BacktestRun[]): StrategyRow[] {
  const by = new Map<string, TimelineRun[]>();
  for (const run of runs) {
    const at = runAt(run);
    if (!at) continue;
    const list = by.get(run.strategyId) ?? [];
    list.push({ run, at });
    by.set(run.strategyId, list);
  }
  return [...by.entries()]
    .map(([strategyId, list]) => {
      const sorted = [...list].sort((a, b) => a.at.getTime() - b.at.getTime());
      const completed = sorted.filter((r) => r.run.status === BacktestStatus.COMPLETED);
      return {
        strategyId,
        runs: sorted,
        latest: sorted[sorted.length - 1],
        latestCompleted: completed[completed.length - 1] ?? null,
        versions: new Set(sorted.map((r) => r.run.strategyVersion)).size,
      };
    })
    .sort((a, b) => b.latest.at.getTime() - a.latest.at.getTime());
}

const DAY_MS = 86_400_000;

/** The calendar the timeline spans: a few days before the first run through today. */
export function timelineWindow(
  rows: readonly StrategyRow[],
  today: Date
): { start: Date; end: Date } | null {
  if (!rows.length) return null;
  const first = Math.min(...rows.map((r) => r.runs[0].at.getTime()));
  const end = Math.max(today.getTime(), ...rows.map((r) => r.latest.at.getTime()));
  const pad = Math.max(2 * DAY_MS, (end - first) * 0.03);
  return { start: new Date(first - pad), end: new Date(end + pad / 2) };
}

/** Runs still queued or running, newest first. */
export function inFlight(runs: readonly BacktestRun[]): BacktestRun[] {
  return runs
    .filter((r) => r.status === BacktestStatus.PENDING || r.status === BacktestStatus.RUNNING)
    .sort((a, b) => (runAt(b)?.getTime() ?? 0) - (runAt(a)?.getTime() ?? 0));
}
