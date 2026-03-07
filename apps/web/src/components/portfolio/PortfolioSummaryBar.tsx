/**
 * Portfolio Summary Bar
 * Displays aggregate portfolio stats in a compact header row.
 */

import { ArrowDownRight, ArrowUpRight, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';

interface PortfolioSummaryBarProps {
  totalEquity: number;
  dayPnl: number;
  dayPnlPercent: number;
  totalReturn: number;
  totalReturnPercent: number;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number, showSign = true): string {
  const sign = showSign && value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export default function PortfolioSummaryBar({
  totalEquity,
  dayPnl,
  dayPnlPercent,
  totalReturn,
  totalReturnPercent,
}: PortfolioSummaryBarProps) {
  return (
    <div className="flex items-center gap-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 px-6 py-4 shadow-sm">
      {/* Total Equity */}
      <div className="flex flex-col shrink-0">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide whitespace-nowrap">
          Total Equity
        </span>
        <span className="text-2xl font-semibold text-gray-900 dark:text-gray-100 font-data whitespace-nowrap">
          {formatCurrency(totalEquity)}
        </span>
      </div>

      {/* Divider */}
      <div className="h-10 w-px bg-gray-200 dark:bg-gray-700 shrink-0" />

      {/* Day P&L */}
      <div className="flex flex-col shrink-0">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide whitespace-nowrap">
          Day P&L
        </span>
        <div className="flex items-center gap-1.5 whitespace-nowrap">
          {dayPnl >= 0 ? (
            <ArrowUpRight className="w-4 h-4 text-green-500 shrink-0" />
          ) : (
            <ArrowDownRight className="w-4 h-4 text-red-500 shrink-0" />
          )}
          <span
            className={`text-lg font-semibold font-data ${
              dayPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
            }`}
          >
            {dayPnl >= 0 ? '+' : ''}
            {formatCurrency(dayPnl)}
          </span>
          <span
            className={`text-sm font-data ${
              dayPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
            }`}
          >
            ({formatPercent(dayPnlPercent)})
          </span>
        </div>
      </div>

      {/* Divider */}
      <div className="h-10 w-px bg-gray-200 dark:bg-gray-700 shrink-0" />

      {/* Total Return */}
      <div className="flex flex-col shrink-0">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide whitespace-nowrap">
          Total Return
        </span>
        <div className="flex items-center gap-1.5 whitespace-nowrap">
          {totalReturn >= 0 ? (
            <ArrowUpRight className="w-4 h-4 text-green-500 shrink-0" />
          ) : (
            <ArrowDownRight className="w-4 h-4 text-red-500 shrink-0" />
          )}
          <span
            className={`text-lg font-semibold font-data ${
              totalReturn >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}
          >
            {totalReturn >= 0 ? '+' : ''}
            {formatCurrency(totalReturn)}
          </span>
          <span
            className={`text-sm font-data ${
              totalReturn >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}
          >
            ({formatPercent(totalReturnPercent)})
          </span>
        </div>
      </div>

      {/* Spacer */}
      <div className="flex-1 min-w-0" />

      {/* Add Strategy Button */}
      <Link
        to="/strategies/new"
        className="flex items-center gap-2 px-4 py-2.5 bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/30 text-green-700 dark:text-green-400 rounded-lg font-medium transition-colors border border-green-200 dark:border-green-800 shrink-0 whitespace-nowrap"
      >
        <Plus className="w-4 h-4" />
        Add Strategy
      </Link>
    </div>
  );
}
