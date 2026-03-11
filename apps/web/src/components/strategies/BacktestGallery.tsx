/**
 * Gallery component for displaying recent backtest results.
 * Shows scrollable list of backtest cards with equity curves.
 */

import { BarChart3, Loader2 } from 'lucide-react';

import type { BacktestRun } from '../../data/demo-strategies';

import { BacktestCard } from './BacktestCard';

interface BacktestGalleryProps {
  backtests: BacktestRun[];
  loading?: boolean;
}

export function BacktestGallery({ backtests, loading = false }: BacktestGalleryProps) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 flex-shrink-0">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Recent Backtests
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {loading ? 'Loading...' : `${backtests.length} results`}
        </p>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-primary-500 animate-spin" />
        </div>
      ) : backtests.length === 0 ? (
        <div className="flex-1 flex items-center justify-center py-12">
          <div className="text-center">
            <div className="w-10 h-10 bg-gray-100 dark:bg-gray-800 rounded-lg flex items-center justify-center mx-auto mb-3">
              <BarChart3 className="w-5 h-5 text-gray-400" />
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">No backtests yet</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              Run a backtest to see results here
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
          {backtests.map((backtest) => (
            <BacktestCard key={backtest.id} backtest={backtest} />
          ))}
        </div>
      )}
    </div>
  );
}
