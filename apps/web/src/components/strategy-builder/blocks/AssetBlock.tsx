import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import type { AssetBlock as AssetBlockType } from '../../../types/strategy-builder';
import { useBlockTheme } from '../useTheme';

interface AssetBlockProps {
  block: AssetBlockType;
  allocationPercent?: number;
  readOnly?: boolean;
}

export function AssetBlock({ block, allocationPercent, readOnly }: AssetBlockProps) {
  const { ui, selectBlock } = useStrategyBuilderStoreWithContext();
  const theme = useBlockTheme();
  const assetColors = theme.asset;
  const allocationBadgeColors = theme.allocation;
  const isSelected = !readOnly && ui.selectedBlockId === block.id;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!readOnly) {
      selectBlock(block.id);
    }
  };

  return (
    <div
      data-testid="asset-block"
      data-symbol={block.symbol}
      className={`
        flex items-center gap-2 px-3 py-2.5 rounded-lg
        transition-all duration-150 select-none
        ${assetColors.bg} border
        ${readOnly ? 'cursor-default' : 'cursor-pointer'}
        ${isSelected
          ? `${assetColors.borderSelected} ${assetColors.ringSelected}`
          : `${assetColors.border} ${readOnly ? '' : assetColors.borderHover}`
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
