import { CircleDot } from 'lucide-react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { AssetBlock as AssetBlockType } from '../../../types/strategy-builder';

interface AssetBlockProps {
  block: AssetBlockType;
  allocationPercent?: number;
}

export function AssetBlock({ block, allocationPercent }: AssetBlockProps) {
  const { ui, selectBlock } = useStrategyBuilderStore();
  const isSelected = ui.selectedBlockId === block.id;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectBlock(block.id);
  };

  return (
    <div
      className={`
        flex items-center gap-3 px-4 py-3 rounded-lg border bg-white dark:bg-gray-900 cursor-pointer
        transition-all duration-150 select-none
        ${isSelected ? 'border-blue-500 ring-2 ring-blue-500/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'}
      `}
      onClick={handleClick}
    >
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className="px-2 py-0.5 text-xs font-semibold bg-blue-500 text-white rounded">
          {allocationPercent}%
        </span>
      )}

      <CircleDot className="w-4 h-4 text-gray-400" />

      <span className="font-semibold text-gray-900 dark:text-gray-100">{block.symbol}</span>

      <span className="text-gray-500 dark:text-gray-400">{block.displayName}</span>

      <span className="ml-auto text-xs text-gray-400">· {block.exchange}</span>
    </div>
  );
}
