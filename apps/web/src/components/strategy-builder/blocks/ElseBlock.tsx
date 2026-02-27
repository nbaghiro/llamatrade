import { ChevronDown, X } from 'lucide-react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { ElseBlock as ElseBlockType } from '../../../types/strategy-builder';

interface ElseBlockProps {
  block: ElseBlockType;
  allocationPercent?: number;
}

export function ElseBlock({ block }: ElseBlockProps) {
  const { ui, selectBlock, toggleExpand, deleteBlock } = useStrategyBuilderStore();
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
      {/* Main pill - blue style like Composer */}
      <div
        data-testid="else-block"
        className={`
          inline-flex items-center gap-1.5 pl-1.5 pr-3 py-1.5 rounded-full cursor-pointer
          transition-all duration-150 select-none
          bg-blue-500 text-white text-sm
          ${isSelected ? 'ring-2 ring-blue-300 ring-offset-2 ring-offset-white dark:ring-offset-gray-900' : 'hover:bg-blue-600'}
        `}
        onClick={handleClick}
      >
        {/* Delete button */}
        <button
          onClick={handleDeleteClick}
          className="p-0.5 rounded-full hover:bg-blue-600 transition-colors"
          title="Delete"
        >
          <X className="w-3.5 h-3.5" />
        </button>

        {/* Expand toggle */}
        <button
          onClick={handleExpandClick}
          className="p-0.5 rounded-full hover:bg-blue-600 transition-colors"
        >
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
        </button>

        {/* ELSE label */}
        <span className="font-semibold">ELSE</span>
      </div>
    </div>
  );
}
