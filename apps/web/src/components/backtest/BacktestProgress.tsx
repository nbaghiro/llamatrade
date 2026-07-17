/**
 * Backtest Progress Component
 * Shows real-time progress of a running backtest.
 */

import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { Ban, CheckCircle, Loader2, XCircle } from 'lucide-react';


interface BacktestProgressProps {
  backtest: BacktestRun;
  progress: number;
  message: string;
  onCancel: () => void;
}

const STATUS_CONFIG = {
  [BacktestStatus.UNSPECIFIED]: {
    label: 'Unknown',
    color: 'bg-bone text-ink/60',
    icon: null,
  },
  [BacktestStatus.PENDING]: {
    label: 'Pending',
    color: 'bg-orange-100 text-orange-700',
    icon: Loader2,
  },
  [BacktestStatus.RUNNING]: {
    label: 'Running',
    color: 'bg-blue-100 text-blue-700',
    icon: Loader2,
  },
  [BacktestStatus.COMPLETED]: {
    label: 'Completed',
    color: 'bg-green-100 text-green-700',
    icon: CheckCircle,
  },
  [BacktestStatus.FAILED]: {
    label: 'Failed',
    color: 'bg-red-100 text-red-700',
    icon: XCircle,
  },
  [BacktestStatus.CANCELLED]: {
    label: 'Cancelled',
    color: 'bg-bone text-ink/60',
    icon: Ban,
  },
};

export default function BacktestProgress({
  backtest,
  progress,
  message,
  onCancel,
}: BacktestProgressProps) {
  const statusConfig = STATUS_CONFIG[backtest.status] || STATUS_CONFIG[BacktestStatus.UNSPECIFIED];
  const StatusIcon = statusConfig.icon;
  const isRunning =
    backtest.status === BacktestStatus.RUNNING ||
    backtest.status === BacktestStatus.PENDING;

  return (
    <div className="bg-paper border-2 border-ink shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="font-display uppercase tracking-tight text-ink">Backtest Progress</h3>
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-mono uppercase tracking-wide border border-ink ${statusConfig.color}`}
          >
            {StatusIcon && (
              <StatusIcon
                className={`w-3.5 h-3.5 ${isRunning ? 'animate-spin' : ''}`}
              />
            )}
            {statusConfig.label}
          </span>
        </div>
        {isRunning && (
          <button
            onClick={onCancel}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-mono uppercase tracking-wide text-red-600 border border-ink hover:bg-red-50 transition-colors"
          >
            <Ban className="w-4 h-4" />
            Cancel
          </button>
        )}
      </div>

      {/* Progress Bar */}
      <div className="mb-3">
        <div className="h-2 bg-bone border border-ink overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ease-out ${
              backtest.status === BacktestStatus.FAILED
                ? 'bg-red-500'
                : backtest.status === BacktestStatus.COMPLETED
                  ? 'bg-green-500'
                  : 'bg-orange-500'
            }`}
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      </div>

      {/* Progress Details */}
      <div className="flex items-center justify-between text-sm">
        <span className="font-mono text-ink/60">{message}</span>
        <span className="font-mono font-bold tabular-nums text-ink">
          {progress.toFixed(0)}%
        </span>
      </div>

      {/* Current Date being processed */}
      {backtest.currentDate && isRunning && (
        <div className="mt-3 pt-3 border-t-2 border-ink">
          <p className="text-xs font-mono text-ink/60">
            Processing: {backtest.currentDate}
          </p>
        </div>
      )}
    </div>
  );
}
