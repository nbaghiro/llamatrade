import { ExecutionStatus, type SleeveSummary } from '@llamatrade/core/stores/portfolio';

import type { RunState } from '../ui/StatusMark';

const CHART_TONES = 5;

/** Each sleeve's series colour, from the chart ramp in sleeve order. */
export function sleeveColor(index: number): string {
  return `rgb(var(--chart-${(index % CHART_TONES) + 1}))`;
}

/** A frozen sleeve reads as frozen whatever its execution reports. */
export function sleeveRunState(
  sleeve: Pick<SleeveSummary, 'frozen' | 'executionStatus'>
): RunState {
  if (sleeve.frozen) return 'frozen';
  switch (sleeve.executionStatus) {
    case ExecutionStatus.RUNNING:
      return 'running';
    case ExecutionStatus.PAUSED:
      return 'paused';
    case ExecutionStatus.ERROR:
      return 'error';
    case ExecutionStatus.PENDING:
      return 'waiting';
    default:
      return 'stopped';
  }
}

/** "Rebalances monthly", or empty when the strategy's schedule is unknown. */
export function rebalanceLabel(rebalance: string): string {
  return rebalance ? `Rebalances ${rebalance.toLowerCase()}` : '';
}

const SHORT_DATE = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });

export function shortDate(d: Date | null): string {
  return d ? SHORT_DATE.format(d) : '';
}

/** Sleeve value less the capital first allocated to it. */
export function sinceStart(sleeve: Pick<SleeveSummary, 'value' | 'allocatedCapital'>): number {
  return sleeve.value - sleeve.allocatedCapital;
}

/** The header line under "Portfolio". Paper is the only account type in the beta. */
export function accountLine(openPositions: number | null, loading = false): string {
  if (loading) return 'Loading your paper account';
  if (openPositions === null) return 'Alpaca paper account';
  const positions = `${openPositions} open ${openPositions === 1 ? 'position' : 'positions'}`;
  return `Alpaca paper account · ${positions}`;
}
