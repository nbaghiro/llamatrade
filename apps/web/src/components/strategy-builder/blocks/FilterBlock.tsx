import { ChevronDown, X } from 'lucide-react';

import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import type { FilterBlock as FilterBlockType } from '../../../types/strategy-builder';
import { FILTER_UNIVERSES } from '../../../types/strategy-builder';
import { useBlockTheme } from '../useTheme';

interface FilterBlockProps {
  block: FilterBlockType;
  allocationPercent?: number;
  onEditFilter?: () => void;
  readOnly?: boolean;
}

export function FilterBlock({ block, allocationPercent, onEditFilter, readOnly }: FilterBlockProps) {
  const { ui, selectBlock, toggleExpand, deleteBlock } = useStrategyBuilderStoreWithContext();
  const theme = useBlockTheme();
  const filterColors = theme.filter;
  const allocationBadgeColors = theme.allocation;
  const isSelected = !readOnly && ui.selectedBlockId === block.id;
  const isExpanded = ui.expandedBlocks.has(block.id);

  const universeInfo = FILTER_UNIVERSES.find((u) => u.value === block.config.universe);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!readOnly) {
      selectBlock(block.id);
    }
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    toggleExpand(block.id);
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteBlock(block.id);
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!readOnly) {
      onEditFilter?.();
    }
  };

  // Build compact display text: "Top 10 Momentum (6m) · S&P 500"
  const getDisplayText = () => {
    const parts = [block.displayText];
    if (universeInfo) {
      parts.push(universeInfo.label);
    }
    return parts.join(' · ');
  };

  return (
    <div className="relative">
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className={`absolute -left-12 top-1/2 -translate-y-1/2 px-2 py-0.5 text-xs font-semibold ${allocationBadgeColors.bg} ${allocationBadgeColors.text} rounded`}>
          {allocationPercent}%
        </span>
      )}

      {/* Filter pill - violet inline style */}
      <div
        className={`
          inline-flex items-center gap-1.5 py-1.5 rounded-full
          transition-all duration-150 select-none
          ${filterColors.bg} text-white text-sm
          ${readOnly ? 'cursor-default pl-3 pr-3' : 'cursor-pointer pl-1.5 pr-3'}
          ${isSelected ? `ring-2 ${filterColors.ring} ring-offset-2 ring-offset-white dark:ring-offset-gray-900` : readOnly ? '' : filterColors.hover}
        `}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
      >
        {/* Delete button - hidden in readOnly mode */}
        {!readOnly && (
          <button
            onClick={handleDeleteClick}
            className={`p-0.5 rounded-full ${filterColors.hover} transition-colors`}
            title="Delete"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}

        {/* Expand toggle */}
        <button
          onClick={handleExpandClick}
          className={`p-0.5 rounded-full ${filterColors.hover} transition-colors`}
        >
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
        </button>

        {/* FILTER label and config */}
        <span className="font-semibold">FILTER</span>
        <span className="font-normal opacity-90">{getDisplayText()}</span>
      </div>
    </div>
  );
}
