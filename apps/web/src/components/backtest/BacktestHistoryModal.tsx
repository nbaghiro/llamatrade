/**
 * Backtest History Modal Component
 * Shows list of past backtests with ability to view details.
 */

import { ChevronDown, Clock, Loader2, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import {
  BacktestStatus,
  type BacktestRun,
} from '@llamatrade/core/proto/backtest_pb';
import { useBacktestStore, toDate, toNumber } from '@llamatrade/core/stores/backtest';

interface BacktestHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (backtestId: string) => void;
}

const STATUS_CONFIG: Record<BacktestStatus, { label: string; color: string }> = {
  [BacktestStatus.UNSPECIFIED]: {
    label: 'Unknown',
    color: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
  },
  [BacktestStatus.PENDING]: {
    label: 'Pending',
    color: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400',
  },
  [BacktestStatus.RUNNING]: {
    label: 'Running',
    color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
  },
  [BacktestStatus.COMPLETED]: {
    label: 'Completed',
    color: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
  },
  [BacktestStatus.FAILED]: {
    label: 'Failed',
    color: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400',
  },
  [BacktestStatus.CANCELLED]: {
    label: 'Cancelled',
    color: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
  },
};

function formatTimeAgo(date: Date | null): string {
  if (!date) return 'Unknown';

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 0) return `${diffDays}d ago`;
  if (diffHours > 0) return `${diffHours}h ago`;
  return 'Just now';
}

function formatDateRange(start: Date | null, end: Date | null): string {
  if (!start || !end) return 'Unknown range';
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' };
  return `${start.toLocaleDateString('en-US', opts)} - ${end.toLocaleDateString('en-US', opts)}`;
}

export default function BacktestHistoryModal({
  isOpen,
  onClose,
  onSelect,
}: BacktestHistoryModalProps) {
  const { backtests, loading, strategies, listBacktests, fetchStrategies } = useBacktestStore();
  const [strategyFilter, setStrategyFilter] = useState<string>('all');

  useEffect(() => {
    if (isOpen) {
      fetchStrategies();
      listBacktests(strategyFilter === 'all' ? undefined : strategyFilter);
    }
  }, [isOpen, strategyFilter, fetchStrategies, listBacktests]);

  if (!isOpen) return null;

  // Get strategy name by ID
  const getStrategyName = (id: string): string => {
    const strategy = strategies.find((s) => s.id === id);
    return strategy?.name ?? 'Unknown Strategy';
  };

  const handleSelect = (backtest: BacktestRun) => {
    onSelect(backtest.id);
    onClose();
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-paper border-2 border-ink shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b-2 border-ink">
            <h2 className="text-lg font-display uppercase tracking-tight text-ink">
              Backtest History
            </h2>
            <button
              onClick={onClose}
              className="p-2 text-ink/50 hover:text-ink hover:bg-bone transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Filter */}
          <div className="px-6 py-3 border-b-2 border-ink">
            <div className="relative w-48">
              <select
                value={strategyFilter}
                onChange={(e) => setStrategyFilter(e.target.value)}
                className="w-full appearance-none pl-3 pr-8 py-2 text-sm border-2 border-ink bg-paper text-ink font-mono focus:border-orange-500 outline-none"
              >
                <option value="all">All Strategies</option>
                {strategies.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 text-primary-500 animate-spin" />
              </div>
            ) : backtests.length === 0 ? (
              <div className="text-center py-12">
                <p className="font-mono uppercase tracking-wide text-ink/60">No backtests found</p>
                <p className="text-sm text-ink/40 mt-1">
                  Run your first backtest to see it here
                </p>
              </div>
            ) : (
              <div className="divide-y divide-ink/12">
                {backtests.map((backtest) => {
                  const statusConfig = STATUS_CONFIG[backtest.status] || STATUS_CONFIG[BacktestStatus.UNSPECIFIED];
                  const startDate = toDate(backtest.config?.startDate);
                  const endDate = toDate(backtest.config?.endDate);
                  const createdAt = toDate(backtest.createdAt);
                  const totalReturn = backtest.results?.metrics
                    ? toNumber(backtest.results.metrics.totalReturn)
                    : null;

                  return (
                    <button
                      key={backtest.id}
                      onClick={() => handleSelect(backtest)}
                      className="w-full px-6 py-4 text-left hover:bg-bone transition-colors"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-bold text-ink truncate">
                              {getStrategyName(backtest.strategyId)}
                            </span>
                            <span
                              className={`px-2 py-0.5 text-xs font-mono uppercase tracking-wide border border-ink ${statusConfig.color}`}
                            >
                              {statusConfig.label}
                            </span>
                          </div>
                          <p className="text-sm text-ink/60">
                            {formatDateRange(startDate, endDate)}
                          </p>
                          <div className="flex items-center gap-2 mt-1.5 text-xs font-mono text-ink/40">
                            <Clock className="w-3 h-3" />
                            {formatTimeAgo(createdAt)}
                          </div>
                        </div>

                        {/* Return if completed */}
                        {totalReturn !== null && backtest.status === BacktestStatus.COMPLETED && (
                          <div className="text-right">
                            <p
                              className={`text-lg font-mono font-bold tabular-nums ${
                                totalReturn >= 0
                                  ? 'text-green-600'
                                  : 'text-red-600'
                              }`}
                            >
                              {totalReturn >= 0 ? '+' : ''}
                              {(totalReturn * 100).toFixed(2)}%
                            </p>
                            <p className="text-[11px] font-mono uppercase tracking-wide text-ink/40">Total Return</p>
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
