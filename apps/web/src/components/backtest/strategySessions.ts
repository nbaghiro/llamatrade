import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import type { StrategyExecution } from '@llamatrade/core/proto/strategy_pb';
import type { TradingSession } from '@llamatrade/core/proto/trading_pb';
import { toDate } from '@llamatrade/core/stores/backtest';
import { executionFor } from '@llamatrade/core/stores/trading';

export type SessionMode = 'paper' | 'live';

/** A paper or live session of a strategy, with the version its execution runs. */
export interface StrategySession {
  strategyId: string;
  version: number;
  mode: SessionMode;
  /** Running or paused, as opposed to stopped. */
  active: boolean;
  startedAt: Date | null;
  stoppedAt: Date | null;
  /** The session page, when the session behind the execution is known. */
  href: string | null;
}

const ACTIVE = new Set([ExecutionStatus.RUNNING, ExecutionStatus.PAUSED, ExecutionStatus.PENDING]);

/**
 * Every execution as a session link, newest first. A session matches its execution on the sleeve
 * both carry, or failing that on strategy, mode and start time.
 */
export function strategySessions(
  executions: readonly StrategyExecution[],
  sessions: readonly TradingSession[]
): StrategySession[] {
  return executions
    .filter((e) => e.mode === ExecutionMode.PAPER || e.mode === ExecutionMode.LIVE)
    .map((e) => {
      const mode: SessionMode = e.mode === ExecutionMode.LIVE ? 'live' : 'paper';
      const startedAt = toDate(e.startedAt);
      const session =
        sessions.find((s) => executionFor(s, [e]) !== null) ??
        sessions.find(
          (s) =>
            s.strategyId === e.strategyId &&
            s.mode === e.mode &&
            toDate(s.startedAt)?.getTime() === startedAt?.getTime()
        ) ??
        null;
      return {
        strategyId: e.strategyId,
        version: e.version,
        mode,
        active: ACTIVE.has(e.status),
        startedAt,
        stoppedAt: toDate(e.stoppedAt),
        href: session ? `/trading/${session.id}` : null,
      };
    })
    .sort((a, b) => (b.startedAt?.getTime() ?? 0) - (a.startedAt?.getTime() ?? 0));
}

/** The session running this exact version, live before paper; null when none does. */
export function sessionForVersion(
  list: readonly StrategySession[],
  strategyId: string,
  version: number
): StrategySession | null {
  const running = list.filter(
    (s) => s.strategyId === strategyId && s.version === version && s.active
  );
  return running.find((s) => s.mode === 'live') ?? running[0] ?? null;
}

/** The newest session of a strategy, active ones first; null when it never ran as one. */
export function latestSession(
  list: readonly StrategySession[],
  strategyId: string
): StrategySession | null {
  const mine = list.filter((s) => s.strategyId === strategyId);
  return mine.find((s) => s.active) ?? mine[0] ?? null;
}

/** "Open the paper session" / "Open the v3 live session". */
export function openSessionLabel(s: StrategySession, withVersion = false): string {
  return `Open the ${withVersion ? `v${s.version} ` : ''}${s.mode} session`;
}
