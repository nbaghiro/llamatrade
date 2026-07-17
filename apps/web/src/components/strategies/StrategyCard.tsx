import { MoreHorizontal, Play, Pause, Copy, Trash2, Edit2 } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import type { Timestamp } from '@llamatrade/core/proto/common_pb';
import {
  StrategyStatus,
  type Strategy,
} from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';

interface StrategyCardProps {
  strategy: Strategy;
}

type StatusKey = 'draft' | 'active' | 'paused' | 'archived';

type ImplementationType = 'dsl' | 'template' | 'custom';

const STATUS_COLORS: Record<StatusKey, { bg: string; text: string }> = {
  draft: { bg: 'bg-gray-100 dark:bg-gray-800', text: 'text-gray-700 dark:text-gray-300' },
  active: { bg: 'bg-orange-100 dark:bg-orange-900/30', text: 'text-orange-700 dark:text-orange-400' },
  paused: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400' },
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

function getImplementationType(strategy: Strategy): ImplementationType {
  if (strategy.templateId) return 'template';
  if (strategy.dslCode) return 'dsl';
  return 'custom';
}

function getTypeLabel(type: ImplementationType): string {
  switch (type) {
    case 'dsl':
      return 'DSL';
    case 'template':
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
    <div className="card-shadow p-4 transition-all hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-lg">
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-display uppercase tracking-tight text-ink truncate pr-2">
          {strategy.name}
        </h3>
        <div className="flex items-center gap-1 shrink-0">
          <span
            className={`px-2 py-0.5 text-[11px] font-mono font-bold uppercase tracking-wide border border-ink ${statusColors.bg} ${statusColors.text}`}
          >
            {statusKey.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="mb-3">
        <span className="px-2 py-0.5 text-[11px] font-mono font-bold uppercase tracking-wide border border-ink bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400">
          {getTypeLabel(getImplementationType(strategy))}
        </span>
      </div>

      {strategy.description && (
        <p className="text-sm text-ink/70 dark:text-gray-400 mb-3 line-clamp-2">
          {strategy.description}
        </p>
      )}

      <div className="text-[11px] font-mono uppercase tracking-wide text-ink/50 mb-4">
        Updated {formatTimeAgo(strategy.updatedAt)}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={handleEdit}
          className="btn btn-secondary btn-sm"
        >
          <Edit2 className="w-3.5 h-3.5" />
          Edit
        </button>

        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="p-1.5 text-ink/60 hover:text-ink hover:bg-ink/5 transition-colors"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>

          {menuOpen && (
            <div className="dropdown right-0 top-full mt-1 w-40 z-10">
              {(strategy.status === StrategyStatus.DRAFT || strategy.status === StrategyStatus.PAUSED) && (
                <button
                  onClick={handleToggleStatus}
                  className="dropdown-item w-full"
                >
                  <Play className="w-4 h-4" />
                  Activate
                </button>
              )}
              {strategy.status === StrategyStatus.ACTIVE && (
                <button
                  onClick={handleToggleStatus}
                  className="dropdown-item w-full"
                >
                  <Pause className="w-4 h-4" />
                  Pause
                </button>
              )}
              <button
                onClick={handleClone}
                className="dropdown-item w-full"
              >
                <Copy className="w-4 h-4" />
                Duplicate
              </button>
              <hr className="my-1 border-ink/15" />
              <button
                onClick={handleDelete}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-600 hover:bg-red-500 hover:text-bone transition-colors"
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
