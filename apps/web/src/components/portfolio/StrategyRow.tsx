/**
 * Strategy Row Component
 * A single row in the strategy list, showing summary info with expandable details.
 */

import { ChevronDown, ChevronRight, Eye, EyeOff, MoreVertical } from 'lucide-react';
import { useState } from 'react';

import type { Activity, Period, Position } from '../../store/portfolio';

import StrategyRowExpanded from './StrategyRowExpanded';

interface StrategyRowProps {
  id: string;
  name: string;
  status: 'live' | 'paper' | 'paused';
  color: string;
  returnPercent: number;
  allocatedCapital: number;
  currentValue: number;
  positionsCount: number;
  positions: Position[];
  recentActivity: Activity[];
  selectedPeriod: Period;
  isExpanded: boolean;
  isVisible: boolean;
  isHovered: boolean;
  onToggleExpand: () => void;
  onToggleVisibility: () => void;
  onHover: (hovered: boolean) => void;
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
  return `${sign}${value.toFixed(2)}%`;
}

const STATUS_STYLES = {
  live: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  paper: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  paused: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

export default function StrategyRow({
  id,
  name,
  status,
  color,
  returnPercent,
  allocatedCapital,
  currentValue,
  positionsCount,
  positions,
  recentActivity,
  isExpanded,
  isVisible,
  isHovered,
  onToggleExpand,
  onToggleVisibility,
  onHover,
}: StrategyRowProps) {
  const [showMenu, setShowMenu] = useState(false);

  const pnl = currentValue - allocatedCapital;

  return (
    <div
      className={`border-b border-gray-100 dark:border-gray-800 transition-colors ${
        isHovered ? 'bg-gray-50 dark:bg-gray-800/50' : ''
      }`}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      {/* Main Row */}
      <div
        className="flex items-center px-4 py-3 cursor-pointer"
        onClick={onToggleExpand}
      >
        {/* Expand Icon */}
        <div className="w-6 flex-shrink-0">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400" />
          )}
        </div>

        {/* Visibility Toggle */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleVisibility();
          }}
          className="w-8 flex-shrink-0 flex items-center justify-center"
        >
          {isVisible ? (
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: color }}
            />
          ) : (
            <div
              className="w-3 h-3 rounded-full border-2"
              style={{ borderColor: color }}
            />
          )}
        </button>

        {/* Name */}
        <div className="flex-1 min-w-0 pr-4">
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {name}
          </span>
        </div>

        {/* Status Badge */}
        <div className="w-20 flex-shrink-0">
          <span
            className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full uppercase ${STATUS_STYLES[status]}`}
          >
            {status}
          </span>
        </div>

        {/* Return */}
        <div className="w-24 flex-shrink-0 text-right">
          <span
            className={`text-sm font-medium font-data ${
              returnPercent >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}
          >
            {formatPercent(returnPercent)}
          </span>
        </div>

        {/* P&L */}
        <div className="w-28 flex-shrink-0 text-right">
          <span
            className={`text-sm font-data ${
              pnl >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}
          >
            {pnl >= 0 ? '+' : ''}
            {formatCurrency(pnl)}
          </span>
        </div>

        {/* Allocated */}
        <div className="w-28 flex-shrink-0 text-right">
          <span className="text-sm text-gray-700 dark:text-gray-300 font-data">
            {formatCurrency(allocatedCapital)}
          </span>
        </div>

        {/* Positions Count */}
        <div className="w-20 flex-shrink-0 text-right">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {positionsCount} pos
          </span>
        </div>

        {/* Actions Menu */}
        <div className="w-10 flex-shrink-0 flex justify-end relative">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowMenu(!showMenu);
            }}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
          >
            <MoreVertical className="w-4 h-4 text-gray-400" />
          </button>

          {showMenu && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowMenu(false);
                }}
              />
              <div className="absolute right-0 top-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20 py-1 min-w-[140px]">
                <button
                  className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleVisibility();
                    setShowMenu(false);
                  }}
                >
                  {isVisible ? (
                    <>
                      <EyeOff className="w-4 h-4" />
                      Hide from chart
                    </>
                  ) : (
                    <>
                      <Eye className="w-4 h-4" />
                      Show on chart
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <StrategyRowExpanded
          strategyId={id}
          status={status}
          positions={positions}
          recentActivity={recentActivity}
        />
      )}
    </div>
  );
}
