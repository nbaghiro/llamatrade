/**
 * Metrics Panel Component
 * Displays backtest performance metrics in a grid layout.
 */

import {
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  Target,
  Percent,
  DollarSign,
} from 'lucide-react';

import type { BacktestMetrics } from '../../generated/proto/backtest_pb';
import { toNumber } from '../../store/backtest';

interface MetricsPanelProps {
  metrics: BacktestMetrics;
}

interface MetricCardProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  positive?: boolean;
  neutral?: boolean;
}

function MetricCard({ label, value, icon, positive, neutral }: MetricCardProps) {
  let valueColor = 'text-gray-900 dark:text-gray-100';
  if (!neutral) {
    if (positive !== undefined) {
      valueColor = positive
        ? 'text-green-600 dark:text-green-400'
        : 'text-red-600 dark:text-red-400';
    }
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-gray-400">{icon}</span>
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          {label}
        </span>
      </div>
      <p className={`text-xl font-semibold font-mono ${valueColor}`}>{value}</p>
    </div>
  );
}

function formatPercent(value: number, includeSign = true): string {
  const pct = value * 100;
  if (includeSign) {
    const sign = pct >= 0 ? '+' : '';
    return `${sign}${pct.toFixed(2)}%`;
  }
  return `${pct.toFixed(2)}%`;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatNumber(value: number, decimals = 2): string {
  return value.toFixed(decimals);
}

export default function MetricsPanel({ metrics }: MetricsPanelProps) {
  const totalReturn = toNumber(metrics.totalReturn);
  const annualizedReturn = toNumber(metrics.annualizedReturn);
  const sharpe = toNumber(metrics.sharpeRatio);
  const sortino = toNumber(metrics.sortinoRatio);
  const maxDrawdown = toNumber(metrics.maxDrawdown);
  const volatility = toNumber(metrics.volatility);
  const winRate = toNumber(metrics.winRate);
  const profitFactor = toNumber(metrics.profitFactor);
  const startingCapital = toNumber(metrics.startingCapital);
  const endingCapital = toNumber(metrics.endingCapital);
  const peakCapital = toNumber(metrics.peakCapital);
  const alpha = toNumber(metrics.alpha);
  const beta = toNumber(metrics.beta);
  const avgWin = toNumber(metrics.averageWin);
  const avgLoss = toNumber(metrics.averageLoss);

  return (
    <div className="space-y-6">
      {/* Returns Section */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Returns</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Total Return"
            value={formatPercent(totalReturn)}
            icon={<TrendingUp className="w-4 h-4" />}
            positive={totalReturn >= 0}
          />
          <MetricCard
            label="Annual Return"
            value={formatPercent(annualizedReturn)}
            icon={<TrendingUp className="w-4 h-4" />}
            positive={annualizedReturn >= 0}
          />
          <MetricCard
            label="Alpha"
            value={formatNumber(alpha, 3)}
            icon={<Target className="w-4 h-4" />}
            positive={alpha >= 0}
          />
          <MetricCard
            label="Beta"
            value={formatNumber(beta, 3)}
            icon={<Activity className="w-4 h-4" />}
            neutral
          />
        </div>
      </div>

      {/* Risk Section */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Risk Metrics</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Sharpe Ratio"
            value={formatNumber(sharpe)}
            icon={<BarChart3 className="w-4 h-4" />}
            positive={sharpe >= 1}
          />
          <MetricCard
            label="Sortino Ratio"
            value={formatNumber(sortino)}
            icon={<BarChart3 className="w-4 h-4" />}
            positive={sortino >= 1}
          />
          <MetricCard
            label="Max Drawdown"
            value={formatPercent(maxDrawdown, false)}
            icon={<TrendingDown className="w-4 h-4" />}
            positive={Math.abs(maxDrawdown) < 0.2}
          />
          <MetricCard
            label="Volatility"
            value={formatPercent(volatility, false)}
            icon={<Activity className="w-4 h-4" />}
            neutral
          />
        </div>
      </div>

      {/* Trade Statistics Section */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Trade Statistics
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Total Trades"
            value={metrics.totalTrades.toString()}
            icon={<Target className="w-4 h-4" />}
            neutral
          />
          <MetricCard
            label="Win Rate"
            value={formatPercent(winRate, false)}
            icon={<Percent className="w-4 h-4" />}
            positive={winRate >= 0.5}
          />
          <MetricCard
            label="Profit Factor"
            value={formatNumber(profitFactor)}
            icon={<BarChart3 className="w-4 h-4" />}
            positive={profitFactor >= 1}
          />
          <MetricCard
            label="Avg Win / Loss"
            value={`${formatCurrency(avgWin)} / ${formatCurrency(Math.abs(avgLoss))}`}
            icon={<DollarSign className="w-4 h-4" />}
            positive={avgWin > Math.abs(avgLoss)}
          />
        </div>
      </div>

      {/* Capital Section */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Capital</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Starting Capital"
            value={formatCurrency(startingCapital)}
            icon={<DollarSign className="w-4 h-4" />}
            neutral
          />
          <MetricCard
            label="Ending Capital"
            value={formatCurrency(endingCapital)}
            icon={<DollarSign className="w-4 h-4" />}
            positive={endingCapital >= startingCapital}
          />
          <MetricCard
            label="Peak Equity"
            value={formatCurrency(peakCapital)}
            icon={<TrendingUp className="w-4 h-4" />}
            neutral
          />
          <MetricCard
            label="Winning Trades"
            value={`${metrics.winningTrades} / ${metrics.totalTrades}`}
            icon={<Target className="w-4 h-4" />}
            positive={metrics.winningTrades > metrics.losingTrades}
          />
        </div>
      </div>
    </div>
  );
}
