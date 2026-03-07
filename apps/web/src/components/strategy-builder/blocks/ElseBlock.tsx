import { ChevronDown, X } from 'lucide-react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { ElseBlock as ElseBlockType } from '../../../types/strategy-builder';
import { useBlockTheme } from '../useTheme';

interface ElseBlockProps {
  block: ElseBlockType;
  allocationPercent?: number;
}

export function ElseBlock({ block }: ElseBlockProps) {
  const { ui, selectBlock, toggleExpand, deleteBlock } = useStrategyBuilderStore();
  const theme = useBlockTheme();
  const elseColors = theme.elseBlock;
  const isSelected = ui.selectedBlockId === block.id;
  const isExpanded = ui.expandedBlocks.has(block.id);

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

  return (
    <div className="relative">
      {/* Main pill - uses centralized theme */}
      <div
        data-testid="else-block"
        className={`
          inline-flex items-center gap-1.5 pl-1.5 pr-3 py-1.5 rounded-full cursor-pointer
          transition-all duration-150 select-none
          ${elseColors.bg} text-white text-sm
          ${isSelected ? `ring-2 ${elseColors.ring} ring-offset-2 ring-offset-white dark:ring-offset-gray-900` : elseColors.hover}
        `}
        onClick={handleClick}
      >
        {/* Delete button */}
        <button
          onClick={handleDeleteClick}
          className={`p-0.5 rounded-full ${elseColors.hover} transition-colors`}
          title="Delete"
        >
          <X className="w-3.5 h-3.5" />
        </button>

        {/* Expand toggle */}
        <button
          onClick={handleExpandClick}
          className={`p-0.5 rounded-full ${elseColors.hover} transition-colors`}
        >
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
        </button>

        {/* ELSE label */}
        <span className="font-semibold">ELSE</span>
      </div>
    </div>
  );
}
