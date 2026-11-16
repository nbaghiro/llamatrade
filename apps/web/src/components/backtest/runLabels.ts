import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { toDate } from '@llamatrade/core/stores/backtest';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Nov 12, 4:02 pm" in the viewer's time zone. */
export function runWhen(run: BacktestRun): string {
  const d = toDate(run.completedAt) ?? toDate(run.createdAt);
  if (!d) return '·';
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }).toLowerCase();
  return `${MON[d.getMonth()]} ${d.getDate()}, ${time}`;
}

/** "2024-11 → 2026-10" from a run's config. */
export function runRange(run: BacktestRun): string {
  const a = toDate(run.config?.startDate);
  const b = toDate(run.config?.endDate);
  return a && b ? `${a.toISOString().slice(0, 7)} → ${b.toISOString().slice(0, 7)}` : '·';
}

export function strategyNameOf(strategies: readonly Strategy[], id: string): string {
  return strategies.find((s) => s.id === id)?.name ?? 'Strategy';
}
