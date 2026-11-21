import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { Link } from 'react-router-dom';

import { longDate, type RebalanceFrequency } from '../../lib/backtestView';
import { formatNumber } from '../../lib/format';
import { StatusMark } from '../ui/StatusMark';

import { rebalancesThrough } from './historyLanes';

/** A run in progress, above the history, with how far it has got and a way back to it. */
export function RunningStrip({
  run,
  strategyName,
  rebalance = null,
}: {
  run: BacktestRun;
  strategyName: string;
  rebalance?: RebalanceFrequency | null;
}) {
  const pct = Math.max(0, Math.min(100, run.progressPercent));
  const queued = pct === 0 && !run.currentDate;
  const count = rebalancesThrough(run, rebalance);
  const through = run.currentDate ? new Date(`${run.currentDate}T00:00:00Z`) : null;
  return (
    <section
      aria-label={`${strategyName} run in progress`}
      className="flex flex-wrap items-center gap-x-3.5 gap-y-2 rounded-panel border border-accent/40 bg-accent-soft px-3.5 py-2.5 text-[12.5px]"
    >
      <StatusMark
        state={queued ? 'waiting' : 'running'}
        label={`${strategyName} v${run.strategyVersion}`}
      />
      <span className="num text-fg-3">
        {queued
          ? 'Queued'
          : through && !Number.isNaN(through.getTime())
            ? `Through ${longDate(through)}`
            : 'Starting'}
        {count &&
          ` · ${formatNumber(count.passed, { dp: 0 })} of ${formatNumber(count.total, { dp: 0 })} rebalances`}
      </span>
      <span
        className="relative h-1 min-w-[80px] flex-1 overflow-hidden rounded-full bg-line"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <i className="absolute inset-y-0 left-0 bg-accent-fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="num">{formatNumber(pct, { dp: 0 })}%</span>
      <Link to={`/backtest?run=${run.id}`} className="btn btn-secondary">
        Open
      </Link>
    </section>
  );
}
