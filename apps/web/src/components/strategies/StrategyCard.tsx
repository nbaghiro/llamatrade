import { MoreHorizontal, Play, Pause, Copy, Trash2, Edit2 } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import type { Timestamp } from '../../generated/proto/llamatrade/v1/common_pb';
import {
  StrategyStatus,
  StrategyType,
  type Strategy,
} from '../../generated/proto/llamatrade/v1/strategy_pb';
import { useStrategiesStore } from '../../store/strategies';

interface StrategyCardProps {
  strategy: Strategy;
}

type StatusKey = 'draft' | 'active' | 'paused' | 'archived';

const STATUS_COLORS: Record<StatusKey, { bg: string; text: string }> = {
  draft: { bg: 'bg-gray-100 dark:bg-gray-800', text: 'text-gray-700 dark:text-gray-300' },
  active: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400' },
  paused: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400' },
  archived: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400' },
};

function getStatusKey(status: StrategyStatus): StatusKey {
  switch (status) {
    case StrategyStatus.DRAFT:
      return 'draft';
    case StrategyStatus.ACTIVE:
      return 'active';
    case StrategyStatus.PAUSED:
      return 'paused';
    case StrategyStatus.ARCHIVED:
      return 'archived';
    default:
      return 'draft';
  }
}

function getTypeLabel(type: StrategyType): string {
  switch (type) {
    case StrategyType.DSL:
      return 'DSL';
    case StrategyType.PYTHON:
      return 'Python';
    case StrategyType.TEMPLATE:
      return 'Template';
    default:
      return 'Custom';
  }
}

function formatTimeAgo(timestamp: Timestamp | undefined): string {
  if (!timestamp) return 'Unknown';
  const date = new Date(Number(timestamp.seconds) * 1000);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export function StrategyCard({ strategy }: StrategyCardProps) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const { activateStrategy, pauseStrategy, cloneStrategy, deleteStrategy } = useStrategiesStore();

  const statusKey = getStatusKey(strategy.status);
  const statusColors = STATUS_COLORS[statusKey];

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [menuOpen]);

  const handleEdit = () => {
    navigate(`/strategies/${strategy.id}`);
  };

  const handleToggleStatus = async () => {
    if (strategy.status === StrategyStatus.ACTIVE) {
      await pauseStrategy(strategy.id);
    } else if (strategy.status === StrategyStatus.DRAFT || strategy.status === StrategyStatus.PAUSED) {
      await activateStrategy(strategy.id);
    }
    setMenuOpen(false);
  };

  const handleClone = async () => {
    await cloneStrategy(strategy.id, `${strategy.name} (Copy)`);
    setMenuOpen(false);
  };

  const handleDelete = async () => {
    if (confirm(`Are you sure you want to delete "${strategy.name}"?`)) {
      await deleteStrategy(strategy.id);
    }
    setMenuOpen(false);
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate pr-2">
          {strategy.name}
        </h3>
        <div className="flex items-center gap-1 shrink-0">
          <span
            className={`px-2 py-0.5 text-xs font-medium rounded ${statusColors.bg} ${statusColors.text}`}
          >
            {statusKey.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Type badge */}
      <div className="mb-3">
        <span className="px-2 py-0.5 text-xs font-medium rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400">
          {getTypeLabel(strategy.type)}
        </span>
      </div>

      {/* Description */}
      {strategy.description && (
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3 line-clamp-2">
          {strategy.description}
        </p>
      )}

      {/* Meta */}
      <div className="text-xs text-gray-500 dark:text-gray-500 mb-4">
        Updated {formatTimeAgo(strategy.updatedAt)}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={handleEdit}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
        >
          <Edit2 className="w-3.5 h-3.5" />
          Edit
        </button>

        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="p-1.5 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 w-40 bg-white dark:bg-gray-900 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-10">
              {(strategy.status === StrategyStatus.DRAFT || strategy.status === StrategyStatus.PAUSED) && (
                <button
                  onClick={handleToggleStatus}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  <Play className="w-4 h-4" />
                  Activate
                </button>
              )}
              {strategy.status === StrategyStatus.ACTIVE && (
                <button
                  onClick={handleToggleStatus}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  <Pause className="w-4 h-4" />
                  Pause
                </button>
              )}
              <button
                onClick={handleClone}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <Copy className="w-4 h-4" />
                Duplicate
              </button>
              <hr className="my-1 border-gray-200 dark:border-gray-700" />
              <button
                onClick={handleDelete}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
              >
                <Trash2 className="w-4 h-4" />
                Delete
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
