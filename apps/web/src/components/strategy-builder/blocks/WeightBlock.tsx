import { ChevronDown, ChevronRight } from 'lucide-react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { WeightBlock as WeightBlockType } from '../../../types/strategy-builder';
import { getWeightMethodInfo } from '../../../types/strategy-builder';

interface WeightBlockProps {
  block: WeightBlockType;
  allocationPercent?: number;
}

export function WeightBlock({ block, allocationPercent }: WeightBlockProps) {
  const { ui, selectBlock, toggleExpand } = useStrategyBuilderStore();
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

  // Get display text for the weight method
  const getDisplayText = () => {
    let text = methodInfo.label;
    if (methodInfo.hasLookback && block.lookbackDays) {
      text += ` ${block.lookbackDays}d`;
    }
    return text;
  };

  return (
    <div className="flex items-center gap-2">
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className="px-2 py-0.5 text-xs font-semibold bg-blue-500 text-white rounded">
          {allocationPercent}%
        </span>
      )}

      {/* Weight pill */}
      <div
        className={`
          inline-flex items-center gap-2 px-3 py-1.5 rounded-full cursor-pointer
          transition-all duration-150 select-none
          ${methodInfo.color.bg} ${methodInfo.color.text}
          ${isSelected ? 'ring-2 ring-offset-1 ring-blue-400' : 'hover:brightness-95'}
        `}
        onClick={handleClick}
      >
        <button onClick={handleExpandClick} className="p-0.5 hover:bg-white/30 rounded">
          {isExpanded ? (
            <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
        </button>

        <span className="text-xs font-semibold uppercase tracking-wide">WEIGHT</span>
        <span className="text-xs font-medium">{getDisplayText()}</span>
      </div>
    </div>
  );
}
