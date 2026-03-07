import { ChevronDown, X } from 'lucide-react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { WeightBlock as WeightBlockType } from '../../../types/strategy-builder';
import { getWeightMethodInfo } from '../../../types/strategy-builder';
import { useBlockTheme } from '../useTheme';

interface WeightBlockProps {
  block: WeightBlockType;
  allocationPercent?: number;
}

export function WeightBlock({ block, allocationPercent }: WeightBlockProps) {
  const { ui, selectBlock, toggleExpand, deleteBlock } = useStrategyBuilderStore();
  const theme = useBlockTheme();
  const isSelected = ui.selectedBlockId === block.id;
  const isExpanded = ui.expandedBlocks.has(block.id);
  const methodInfo = getWeightMethodInfo(block.method);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectBlock(block.id);
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    toggleExpand(block.id);
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteBlock(block.id);
  };

  // Get display text for the weight method
  const getDisplayText = () => {
    let text = methodInfo.label;
    if (methodInfo.hasLookback && block.lookbackDays) {
      text += ` ${block.lookbackDays}d`;
    }
    return text;
  };

  const colors = theme.weight;
  const allocationBadgeColors = theme.allocation;

  return (
    <div className="relative">
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className={`absolute -left-12 top-1/2 -translate-y-1/2 px-2 py-0.5 text-xs font-semibold ${allocationBadgeColors.bg} ${allocationBadgeColors.text} rounded`}>
          {allocationPercent}%
        </span>
      )}

      {/* Weight pill - orange style based on method */}
      <div
        data-testid="weight-block"
        className={`
          inline-flex items-center gap-1.5 pl-1.5 pr-3 py-1.5 rounded-full cursor-pointer
          transition-all duration-150 select-none
          ${colors.bg} text-white text-sm
          ${isSelected ? `ring-2 ${colors.ring} ring-offset-2 ring-offset-white dark:ring-offset-gray-900` : colors.hover}
        `}
        onClick={handleClick}
      >
        {/* Delete button */}
        <button
          onClick={handleDeleteClick}
          className={`p-0.5 rounded-full ${colors.hover} transition-colors`}
          title="Delete"
        >
          <X className="w-3.5 h-3.5" />
        </button>

        {/* Expand toggle */}
        <button
          onClick={handleExpandClick}
          className={`p-0.5 rounded-full ${colors.hover} transition-colors`}
        >
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
        </button>

        {/* WEIGHT label and method */}
        <span className="font-semibold">WEIGHT</span>
        <span className="font-normal opacity-90">{getDisplayText()}</span>
      </div>
    </div>
  );
}
