import { useStrategyBuilderStore } from '../../store/strategy-builder';
import type { BlockId } from '../../types/strategy-builder';
import { hasChildren } from '../../types/strategy-builder';

import { AddBlockButton } from './blocks/AddBlockButton';
import { AssetBlock } from './blocks/AssetBlock';
import { ElseBlock } from './blocks/ElseBlock';
import { FilterBlock } from './blocks/FilterBlock';
import { GroupBlock } from './blocks/GroupBlock';
import { IfBlock } from './blocks/IfBlock';
import { RootBlock } from './blocks/RootBlock';
import { WeightBlock } from './blocks/WeightBlock';

interface TreeNodeProps {
  blockId: BlockId;
  depth?: number;
  isLast?: boolean;
  parentWeightId?: BlockId;
}

export function TreeNode({ blockId, depth = 0, isLast = true, parentWeightId }: TreeNodeProps) {
  const { tree, ui } = useStrategyBuilderStore();
  const block = tree.blocks[blockId];

  if (!block) return null;

  const isExpanded = ui.expandedBlocks.has(blockId);
  const canHaveChildren = hasChildren(block);
  const isRoot = block.type === 'root';
  const isGroup = block.type === 'group';

  // Determine if parent is a specified weight block (for percentage badges)
  const parentIsSpecifiedWeight =
    parentWeightId &&
    tree.blocks[parentWeightId]?.type === 'weight' &&
    (tree.blocks[parentWeightId] as { method: string }).method === 'specified';

  // Get allocation percentage for this block if parent is specified weight
  const allocationPercent = parentIsSpecifiedWeight
    ? (tree.blocks[parentWeightId] as { allocations: Record<string, number> }).allocations[
        blockId
      ] ?? 0
    : undefined;

  // For weight blocks, pass the weightId to children
  const childWeightId = block.type === 'weight' ? blockId : undefined;

  // Render the appropriate block component
  const renderBlock = () => {
    switch (block.type) {
      case 'root':
        return <RootBlock block={block} />;
      case 'asset':
        return <AssetBlock block={block} allocationPercent={allocationPercent} />;
      case 'group':
        return <GroupBlock block={block} allocationPercent={allocationPercent} />;
      case 'weight':
        return <WeightBlock block={block} allocationPercent={allocationPercent} />;
      case 'if':
        return <IfBlock block={block} allocationPercent={allocationPercent} />;
      case 'else':
        return <ElseBlock block={block} allocationPercent={allocationPercent} />;
      case 'filter':
        return <FilterBlock block={block} allocationPercent={allocationPercent} />;
      default:
        return null;
    }
  };

  // Determine spacing based on block type
  const getChildSpacing = () => {
    if (block.type === 'root' || block.type === 'weight' || block.type === 'if' || block.type === 'else' || block.type === 'filter') {
      return 'space-y-4';
    }
    return 'space-y-3';
  };

  return (
    <div className={`relative ${isGroup && depth > 0 ? 'mt-1' : ''}`} data-block-id={blockId}>
      {/* Connector line from parent (except for root) */}
      {!isRoot && depth > 0 && (
        <div className="absolute left-0 top-0 bottom-0 w-6">
          {/* Vertical line */}
          <div
            className={`absolute left-3 top-0 w-0.5 bg-gray-300 dark:bg-gray-600 ${isLast ? 'h-7' : 'h-full'}`}
          />
          {/* Horizontal connector */}
          <div className="absolute left-3 top-7 w-3 h-0.5 bg-gray-300 dark:bg-gray-600" />
        </div>
      )}

      {/* Block content */}
      <div className={depth > 0 ? 'pl-6' : ''}>
        {renderBlock()}

        {/* Children */}
        {canHaveChildren && isExpanded && (
          <div className="relative mt-3">
            {/* Vertical connector line for children */}
            {block.childIds.length > 0 && (
              <div className="absolute left-3 top-0 w-0.5 h-full bg-gray-300 dark:bg-gray-600" />
            )}

            <div className={getChildSpacing()}>
              {block.childIds.map((childId, index) => (
                <TreeNode
                  key={childId}
                  blockId={childId}
                  depth={depth + 1}
                  isLast={index === block.childIds.length - 1}
                  parentWeightId={childWeightId}
                />
              ))}
            </div>

            {/* Add block button */}
            <div className="relative pl-6 mt-3">
              {/* Connector for add button */}
              <div className="absolute left-3 top-0 h-7 w-0.5 bg-gray-300 dark:bg-gray-600" />
              <div className="absolute left-3 top-7 w-3 h-0.5 bg-gray-300 dark:bg-gray-600" />
              <AddBlockButton parentId={blockId} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
