/**
 * Card component for displaying a backtest result in the gallery.
 * Shows equity curve chart with key metrics.
 */

import { Link } from 'react-router-dom';

import type { BacktestRunView } from '../../types/backtest';

import { MiniChart } from './MiniChart';

interface BacktestCardProps {
  backtest: BacktestRunView;
}

function formatDate(date: Date): string {
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function BacktestCard({ backtest }: BacktestCardProps) {
  const positive = backtest.returnPct >= 0;

  return (
    <Link
      to={`/backtest?strategy=${backtest.strategyId}&run=${backtest.id}`}
      className="block card-shadow p-3 transition-all duration-200 hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-lg"
    >
      {/* Equity Curve Chart */}
      <div className="mb-2">
        <MiniChart
          data={backtest.equityCurve}
          benchmarkData={backtest.benchmarkCurve}
          positive={positive}
          width={248}
          height={80}
          showBenchmark={true}
        />
      </div>

      {/* Strategy Name */}
      <h3 className="font-display uppercase tracking-tight text-ink text-sm truncate mb-1">
        {backtest.strategyName}
      </h3>

      {/* Metrics Row */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          <span
            className={`font-semibold font-mono ${
              positive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
            }`}
          >
            {positive ? '+' : ''}
            {backtest.returnPct.toFixed(1)}%
          </span>
          <span className="text-gray-500 dark:text-gray-400">
            {backtest.sharpeRatio.toFixed(2)} SR
          </span>
        </div>
        <span className="text-gray-400 dark:text-gray-500">
          {formatDate(backtest.runDate)}
        </span>
      </div>
    </Link>
  );
}
