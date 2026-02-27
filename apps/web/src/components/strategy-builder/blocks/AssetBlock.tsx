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
      data-testid="asset-block"
      data-symbol={block.symbol}
      className={`
        flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer
        transition-all duration-150 select-none
        bg-white dark:bg-gray-900 border
        ${isSelected
          ? 'border-gray-400 dark:border-gray-500 ring-2 ring-gray-200 dark:ring-gray-700'
          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
        }
      `}
      onClick={handleClick}
    >
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className="px-1.5 py-0.5 text-xs font-semibold bg-blue-500 text-white rounded">
          {allocationPercent}%
        </span>
      )}

      {/* Circle bullet - like Composer */}
      <span className="w-3 h-3 rounded-full border-2 border-gray-400 dark:border-gray-500" />

      {/* Ticker */}
      <span className="font-semibold text-gray-900 dark:text-gray-100">{block.symbol}</span>

      {/* Full name */}
      <span className="text-gray-500 dark:text-gray-400 text-sm">{block.displayName}</span>
    </div>
  );
}
