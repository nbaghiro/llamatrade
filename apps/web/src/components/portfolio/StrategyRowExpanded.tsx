/**
 * Strategy Row Expanded Content
 * Shows positions, recent activity, and action buttons when a strategy row is expanded.
 */

import { Edit, Eye, Pause, Play, Square } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { Activity, Position } from '../../store/portfolio';

interface StrategyRowExpandedProps {
  strategyId: string;
  status: 'live' | 'paper' | 'paused';
  positions: Position[];
  recentActivity: Activity[];
  onPause?: () => void;
  onResume?: () => void;
  onStop?: () => void;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}

function formatTimeAgo(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (days > 0) {
    return days === 1 ? 'yesterday' : `${days}d ago`;
  }
  if (hours > 0) {
    return `${hours}h ago`;
  }
  return 'just now';
}

export default function StrategyRowExpanded({
  strategyId,
  status,
  positions,
  recentActivity,
  onPause,
  onResume,
  onStop,
}: StrategyRowExpandedProps) {
  const displayPositions = positions.slice(0, 4);
  const morePositionsCount = positions.length - displayPositions.length;

  return (
    <div className="px-4 pb-4 pt-2 bg-gray-50 dark:bg-gray-800/50 border-t border-gray-100 dark:border-gray-800">
      {/* Positions */}
      <div className="mb-4">
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
          Positions
        </h4>
        {positions.length === 0 ? (
          <p className="text-sm text-gray-400 dark:text-gray-500 italic">No open positions</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {displayPositions.map((pos) => (
              <div
                key={pos.symbol}
                className="flex flex-col bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2 min-w-[100px]"
              >
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {pos.symbol}
                </span>
                <span
                  className={`text-xs font-data ${
                    pos.unrealizedPnl >= 0
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {pos.unrealizedPnl >= 0 ? '+' : ''}
                  {formatCurrency(pos.unrealizedPnl)} ({formatPercent(pos.unrealizedPnlPercent)})
                </span>
              </div>
            ))}
            {morePositionsCount > 0 && (
              <div className="flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-lg px-3 py-2 min-w-[80px]">
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  +{morePositionsCount} more
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Recent Activity */}
      <div className="mb-4">
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
          Recent Activity
        </h4>
        {recentActivity.length === 0 ? (
          <p className="text-sm text-gray-400 dark:text-gray-500 italic">No recent activity</p>
        ) : (
          <div className="space-y-1">
            {recentActivity.slice(0, 3).map((activity) => (
              <div key={activity.id} className="flex items-center gap-2 text-sm">
                <span
                  className={`font-medium ${
                    activity.type === 'buy'
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {activity.type === 'buy' ? 'Bought' : 'Sold'}
                </span>
                <span className="text-gray-700 dark:text-gray-300">
                  {activity.qty} {activity.symbol}
                </span>
                <span className="text-gray-500 dark:text-gray-400">
                  @ {formatCurrency(activity.price)}
                </span>
                <span className="text-gray-400 dark:text-gray-500">—</span>
                <span className="text-gray-400 dark:text-gray-500">
                  {formatTimeAgo(activity.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <Link
          to={`/strategies/${strategyId}`}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <Eye className="w-4 h-4" />
          View Details
        </Link>

        <Link
          to={`/strategies/${strategyId}/edit`}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <Edit className="w-4 h-4" />
          Edit
        </Link>

        {status === 'live' || status === 'paper' ? (
          <button
            onClick={onPause}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors"
          >
            <Pause className="w-4 h-4" />
            Pause
          </button>
        ) : (
          <button
            onClick={onResume}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors"
          >
            <Play className="w-4 h-4" />
            Resume
          </button>
        )}

        {(status === 'live' || status === 'paper') && (
          <button
            onClick={onStop}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
          >
            <Square className="w-4 h-4" />
            Stop
          </button>
        )}
      </div>
    </div>
  );
}
