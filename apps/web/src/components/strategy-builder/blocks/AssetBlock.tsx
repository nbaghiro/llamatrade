import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { AssetBlock as AssetBlockType } from '../../../types/strategy-builder';
import { useBlockTheme } from '../useTheme';

interface AssetBlockProps {
  block: AssetBlockType;
  allocationPercent?: number;
}

export function AssetBlock({ block, allocationPercent }: AssetBlockProps) {
  const { ui, selectBlock } = useStrategyBuilderStore();
  const theme = useBlockTheme();
  const assetColors = theme.asset;
  const allocationBadgeColors = theme.allocation;
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
        ${assetColors.bg} border
        ${isSelected
          ? `${assetColors.borderSelected} ${assetColors.ringSelected}`
          : `${assetColors.border} ${assetColors.borderHover}`
        }
      `}
      onClick={handleClick}
    >
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className={`px-1.5 py-0.5 text-xs font-semibold ${allocationBadgeColors.bg} ${allocationBadgeColors.text} rounded`}>
          {allocationPercent}%
        </span>
      )}

      {/* Circle bullet - like Composer */}
      <span className={`w-3 h-3 rounded-full border-2 ${assetColors.bullet}`} />

      {/* Ticker */}
      <span className={`font-semibold ${assetColors.text}`}>{block.symbol}</span>

      {/* Full name */}
      <span className={`${assetColors.textMuted} text-sm`}>{block.displayName}</span>
    </div>
  );
}
