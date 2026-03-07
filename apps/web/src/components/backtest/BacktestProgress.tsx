/**
 * Backtest Progress Component
 * Shows real-time progress of a running backtest.
 */

import { Ban, CheckCircle, Loader2, XCircle } from 'lucide-react';

import { BacktestStatus, type BacktestRun } from '../../generated/proto/backtest_pb';

interface BacktestProgressProps {
  backtest: BacktestRun;
  progress: number;
  message: string;
  onCancel: () => void;
}

const STATUS_CONFIG = {
  [BacktestStatus.UNSPECIFIED]: {
    label: 'Unknown',
    color: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
    icon: null,
  },
  [BacktestStatus.PENDING]: {
    label: 'Pending',
    color: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400',
    icon: Loader2,
  },
  [BacktestStatus.RUNNING]: {
    label: 'Running',
    color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
    icon: Loader2,
  },
  [BacktestStatus.COMPLETED]: {
    label: 'Completed',
    color: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
    icon: CheckCircle,
  },
  [BacktestStatus.FAILED]: {
    label: 'Failed',
    color: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400',
    icon: XCircle,
  },
  [BacktestStatus.CANCELLED]: {
    label: 'Cancelled',
    color: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
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
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="font-medium text-gray-900 dark:text-gray-100">Backtest Progress</h3>
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full ${statusConfig.color}`}
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
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
          >
            <Ban className="w-4 h-4" />
            Cancel
          </button>
        )}
      </div>

      {/* Progress Bar */}
      <div className="mb-3">
        <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ease-out rounded-full ${
              backtest.status === BacktestStatus.FAILED
                ? 'bg-red-500'
                : backtest.status === BacktestStatus.COMPLETED
                  ? 'bg-green-500'
                  : 'bg-primary-500'
            }`}
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      </div>

      {/* Progress Details */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-600 dark:text-gray-400">{message}</span>
        <span className="font-mono text-gray-900 dark:text-gray-100">
          {progress.toFixed(0)}%
        </span>
      </div>

      {/* Current Date being processed */}
      {backtest.currentDate && isRunning && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Processing: {backtest.currentDate}
          </p>
        </div>
      )}
    </div>
  );
}
