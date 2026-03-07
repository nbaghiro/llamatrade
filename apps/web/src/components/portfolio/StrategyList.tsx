/**
 * Strategy List Component
 * Scrollable list of strategies with filtering and sorting.
 */

import { ChevronDown, Filter } from 'lucide-react';
import { useState } from 'react';

import type { ExecutionMode, ExecutionStatus, Period, StrategyPerformance } from '../../store/portfolio';

import StrategyRow from './StrategyRow';

interface StrategyListProps {
  strategies: StrategyPerformance[];
  selectedPeriod: Period;
  expandedStrategyId: string | null;
  visibleStrategyIds: Set<string>;
  hoveredStrategyId: string | null;
  onToggleExpanded: (id: string) => void;
  onToggleVisibility: (id: string) => void;
  onHoverStrategy: (id: string | null) => void;
}

type DisplayStatus = 'live' | 'paper' | 'paused';
type StatusFilter = 'all' | DisplayStatus;
type SortField = 'name' | 'return' | 'allocated' | 'positions';
type SortDirection = 'asc' | 'desc';

/**
 * Derive display status from mode and execution status.
 * - Running strategies show as 'live' or 'paper' based on mode
 * - Non-running strategies show as 'paused'
 */
function getDisplayStatus(mode: ExecutionMode, status: ExecutionStatus): DisplayStatus {
  if (status === 'running') {
    return mode === 'live' ? 'live' : 'paper';
  }
  return 'paused';
}

export default function StrategyList({
  strategies,
  selectedPeriod,
  expandedStrategyId,
  visibleStrategyIds,
  hoveredStrategyId,
  onToggleExpanded,
  onToggleVisibility,
  onHoverStrategy,
}: StrategyListProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [showFilterDropdown, setShowFilterDropdown] = useState(false);
  const [sortField, setSortField] = useState<SortField>('return');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  // Count by display status (derived from mode + status)
  const statusCounts = strategies.reduce(
    (acc, s) => {
      const displayStatus = getDisplayStatus(s.mode, s.status);
      acc[displayStatus]++;
      acc.total++;
      return acc;
    },
    { live: 0, paper: 0, paused: 0, total: 0 }
  );

  // Filter strategies by display status
  const filteredStrategies = strategies.filter((s) => {
    if (statusFilter === 'all') return true;
    const displayStatus = getDisplayStatus(s.mode, s.status);
    return displayStatus === statusFilter;
  });

  // Sort strategies
  const sortedStrategies = [...filteredStrategies].sort((a, b) => {
    let comparison = 0;

    switch (sortField) {
      case 'name':
        comparison = a.name.localeCompare(b.name);
        break;
      case 'return':
        comparison = a.returns[selectedPeriod] - b.returns[selectedPeriod];
        break;
      case 'allocated':
        comparison = a.allocatedCapital - b.allocatedCapital;
        break;
      case 'positions':
        comparison = a.positionsCount - b.positionsCount;
        break;
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return null;
    return (
      <ChevronDown
        className={`w-3 h-3 transition-transform ${sortDirection === 'asc' ? 'rotate-180' : ''}`}
      />
    );
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm flex flex-col min-h-[300px]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Strategies</span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            ({statusCounts.live} live, {statusCounts.paper} paper
            {statusCounts.paused > 0 && `, ${statusCounts.paused} paused`})
          </span>
        </div>

        {/* Filter Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowFilterDropdown(!showFilterDropdown)}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
          >
            <Filter className="w-4 h-4" />
            <span>{statusFilter === 'all' ? 'All' : statusFilter}</span>
            <ChevronDown className="w-4 h-4" />
          </button>

          {showFilterDropdown && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowFilterDropdown(false)}
              />
              <div className="absolute right-0 top-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20 py-1 min-w-[120px]">
                {(['all', 'live', 'paper', 'paused'] as StatusFilter[]).map((filter) => (
                  <button
                    key={filter}
                    onClick={() => {
                      setStatusFilter(filter);
                      setShowFilterDropdown(false);
                    }}
                    className={`w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-between ${
                      statusFilter === filter
                        ? 'text-green-600 dark:text-green-400 font-medium'
                        : 'text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <span className="capitalize">{filter}</span>
                    <span className="text-gray-400 text-xs">
                      {filter === 'all' ? statusCounts.total : statusCounts[filter]}
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Column Headers */}
      <div className="flex items-center px-4 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
        <div className="w-6 flex-shrink-0" /> {/* Expand icon */}
        <div className="w-8 flex-shrink-0" /> {/* Color dot */}
        <button
          className="flex-1 min-w-0 text-left flex items-center gap-1 hover:text-gray-700 dark:hover:text-gray-300"
          onClick={() => handleSort('name')}
        >
          Name
          <SortIcon field="name" />
        </button>
        <div className="w-20 flex-shrink-0">Status</div>
        <button
          className="w-24 flex-shrink-0 text-right flex items-center justify-end gap-1 hover:text-gray-700 dark:hover:text-gray-300"
          onClick={() => handleSort('return')}
        >
          Return
          <SortIcon field="return" />
        </button>
        <div className="w-28 flex-shrink-0 text-right">P&L</div>
        <button
          className="w-28 flex-shrink-0 text-right flex items-center justify-end gap-1 hover:text-gray-700 dark:hover:text-gray-300"
          onClick={() => handleSort('allocated')}
        >
          Allocated
          <SortIcon field="allocated" />
        </button>
        <button
          className="w-20 flex-shrink-0 text-right flex items-center justify-end gap-1 hover:text-gray-700 dark:hover:text-gray-300"
          onClick={() => handleSort('positions')}
        >
          Positions
          <SortIcon field="positions" />
        </button>
        <div className="w-10 flex-shrink-0" /> {/* Actions */}
      </div>

      {/* Strategy Rows */}
      <div className="flex-1">
        {sortedStrategies.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-gray-400 dark:text-gray-500">
            No strategies found
          </div>
        ) : (
          sortedStrategies.map((strategy) => (
            <StrategyRow
              key={strategy.id}
              id={strategy.id}
              name={strategy.name}
              status={getDisplayStatus(strategy.mode, strategy.status)}
              color={strategy.color}
              returnPercent={strategy.returns[selectedPeriod] * 100}
              allocatedCapital={strategy.allocatedCapital}
              currentValue={strategy.currentValue}
              positionsCount={strategy.positionsCount}
              positions={strategy.positions}
              recentActivity={strategy.recentActivity}
              selectedPeriod={selectedPeriod}
              isExpanded={expandedStrategyId === strategy.id}
              isVisible={visibleStrategyIds.has(strategy.id)}
              isHovered={hoveredStrategyId === strategy.id}
              onToggleExpand={() => onToggleExpanded(strategy.id)}
              onToggleVisibility={() => onToggleVisibility(strategy.id)}
              onHover={(hovered) => onHoverStrategy(hovered ? strategy.id : null)}
            />
          ))
        )}
      </div>
    </div>
  );
}
