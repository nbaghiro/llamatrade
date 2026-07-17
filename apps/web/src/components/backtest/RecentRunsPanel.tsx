/**
 * Recent Runs rail panel.
 * Lists recently completed backtests (hydrated with metrics) for quick recall.
 */

import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';

interface RecentRunsPanelProps {
  runs: BacktestRun[];
  strategies: Strategy[];
  selectedId?: string;
  loading: boolean;
  onSelect: (id: string) => void;
}

// Decorative dot palette (Monolith accents), assigned per row by position.
const DOT_COLORS = ['#0f7a34', '#1a1aff', '#6b2fb3', '#c81e1e', '#0e8ba0'];

const TIMEFRAME_LABELS: Record<string, string> = {
  '1Min': '1 Min',
  '5Min': '5 Min',
  '15Min': '15 Min',
  '1H': 'Hourly',
  '4H': '4 Hour',
  '1D': 'Daily',
};

function formatDay(run: BacktestRun): string {
  const date = toDate(run.completedAt) ?? toDate(run.createdAt);
  if (!date) return '—';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function signedPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

export default function RecentRunsPanel({
  runs,
  strategies,
  selectedId,
  loading,
  onSelect,
}: RecentRunsPanelProps) {
  const strategyName = (run: BacktestRun): string =>
    strategies.find((s) => s.id === run.strategyId)?.name ?? 'Strategy';

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d]">
      <div className="flex items-center justify-between px-[15px] py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">Recent Runs</span>
        <span className="font-mono text-[10.5px] font-bold uppercase tracking-[0.05em] text-ink/40">
          {runs.length}
        </span>
      </div>

      {loading && runs.length === 0 ? (
        <div className="px-[15px] py-6 font-mono text-[10.5px] uppercase tracking-[0.05em] text-ink/40">
          Loading…
        </div>
      ) : runs.length === 0 ? (
        <div className="px-[15px] py-6 font-mono text-[10.5px] uppercase tracking-[0.05em] text-ink/40">
          No completed runs yet
        </div>
      ) : (
        runs.map((run, i) => {
          const metrics = run.results?.metrics;
          const ret = metrics ? toNumber(metrics.annualizedReturn) : 0;
          const sharpe = metrics ? toNumber(metrics.sharpeRatio) : 0;
          const active = selectedId === run.id;
          return (
            <button
              key={run.id}
              onClick={() => onSelect(run.id)}
              className={`w-full flex items-center gap-2.5 px-[15px] py-2.5 border-b border-line last:border-b-0 text-left transition-colors ${
                active ? 'bg-bone' : 'hover:bg-bone'
              }`}
            >
              <span
                className="w-2.5 h-2.5 flex-none border-2 border-ink"
                style={{ backgroundColor: DOT_COLORS[i % DOT_COLORS.length] }}
              />
              <span className="flex-1 min-w-0">
                <span className="block font-bold text-[13px] truncate">{strategyName(run)}</span>
                <span className="block font-mono text-[9.5px] uppercase tracking-[0.04em] text-ink/50 mt-px">
                  {formatDay(run)} · {TIMEFRAME_LABELS[run.config?.timeframe ?? ''] ?? run.config?.timeframe ?? '—'}
                </span>
              </span>
              <span className="text-right">
                <span
                  className={`block font-mono font-bold text-[13.5px] tabular-nums ${
                    ret >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {signedPercent(ret)}
                </span>
                <span className="block font-mono text-[9.5px] text-ink/50 tabular-nums mt-px">
                  {sharpe.toFixed(2)} SR
                </span>
              </span>
            </button>
          );
        })
      )}
    </div>
  );
}
