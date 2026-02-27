import { ChevronDown, ChevronRight, Filter } from 'lucide-react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { FilterBlock as FilterBlockType } from '../../../types/strategy-builder';
import { FILTER_UNIVERSES } from '../../../types/strategy-builder';

interface FilterBlockProps {
  block: FilterBlockType;
  allocationPercent?: number;
  onEditFilter?: () => void;
}

export function FilterBlock({ block, allocationPercent, onEditFilter }: FilterBlockProps) {
  const { ui, selectBlock, toggleExpand } = useStrategyBuilderStore();
  const isSelected = ui.selectedBlockId === block.id;
  const isExpanded = ui.expandedBlocks.has(block.id);

  const universeInfo = FILTER_UNIVERSES.find((u) => u.value === block.config.universe);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectBlock(block.id);
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    toggleExpand(block.id);
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onEditFilter?.();
  };

  return (
    <div
      className={`
        flex items-start gap-3 px-4 py-3 rounded-lg border cursor-pointer
        transition-all duration-150 select-none
        bg-purple-50 dark:bg-purple-900/20
        ${isSelected ? 'border-purple-500 ring-2 ring-purple-500/20' : 'border-purple-200 dark:border-purple-800 hover:border-purple-300 dark:hover:border-purple-700'}
      `}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className="px-2 py-0.5 text-xs font-semibold bg-blue-500 text-white rounded shrink-0">
          {allocationPercent}%
        </span>
      )}

      <button
        onClick={handleExpandClick}
        className="p-0.5 mt-0.5 hover:bg-purple-200 dark:hover:bg-purple-800 rounded shrink-0"
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-purple-600 dark:text-purple-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-purple-600 dark:text-purple-400" />
        )}
      </button>

      <Filter className="w-4 h-4 text-purple-500 dark:text-purple-400 mt-0.5 shrink-0" />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-bold uppercase tracking-wide text-purple-700 dark:text-purple-300">
            FILTER
          </span>
          <span className="text-sm font-medium text-purple-900 dark:text-purple-100">
            {block.displayText}
          </span>
        </div>
        {universeInfo && (
          <p className="text-xs text-purple-600 dark:text-purple-400">
            From: {universeInfo.label}
          </p>
        )}
      </div>
    </div>
  );
}
