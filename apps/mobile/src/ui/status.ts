import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';

import type { RunState } from './index';

/** A session's execution status as a run state. */
export function runStateOfExecution(status: ExecutionStatus): RunState {
  switch (status) {
    case ExecutionStatus.RUNNING:
      return 'running';
    case ExecutionStatus.PENDING:
      return 'waiting';
    case ExecutionStatus.PAUSED:
      return 'paused';
    case ExecutionStatus.ERROR:
      return 'error';
    default:
      return 'stopped';
  }
}

/** A strategy's run state: the session's when one is deployed, else the strategy's own status. */
export function runStateOfStrategy(status: StrategyStatus, execution?: ExecutionStatus): RunState {
  if (status === StrategyStatus.ARCHIVED) return 'archived';
  if (status === StrategyStatus.PAUSED) return 'paused';
  if (status === StrategyStatus.ACTIVE) return execution === undefined ? 'running' : runStateOfExecution(execution);
  return 'draft';
}

/** "quarterly" as "Quarterly"; empty when the strategy has no rebalance cadence. */
export function cadence(rebalance: string): string {
  const r = rebalance.trim();
  return r ? r.charAt(0).toUpperCase() + r.slice(1).toLowerCase() : '';
}
