import { useStrategyBuilderStoreWithContext } from '../../store/strategy-builder';
import { hasChildren } from '@llamatrade/core/strategy/types';

import { AddBlockButton } from './blocks/AddBlockButton';
import { TreeNode } from './TreeNode';

interface CanvasProps {
  readOnly?: boolean;
}

export function Canvas({ readOnly }: CanvasProps) {
  const { tree, ui, compactView, selectBlock } = useStrategyBuilderStoreWithContext();
  const rootBlock = tree.blocks[tree.rootId];
  const isExpanded = ui.expandedBlocks.has(tree.rootId);

  const hideEditControls = readOnly || compactView;

  const handleCanvasClick = () => {
    if (!hideEditControls) {
      selectBlock(null);
    }
  };

  // Root block is rendered separately in StrategyBuilder, so we render its children here
  const canHaveChildren = rootBlock && hasChildren(rootBlock);
  const childIds = canHaveChildren ? rootBlock.childIds : [];

  return (
    <div
      className="flex-1 overflow-auto pb-24"
      onClick={handleCanvasClick}
    >
      {isExpanded && (
        <div className="relative">
          {/* Vertical connector line for children */}
          {childIds.length > 0 && (
            <div className="absolute left-3 top-0 w-0.5 h-full bg-ink/25" />
          )}

          <div className="space-y-4">
            {childIds.map((childId, index) => (
              <TreeNode
                key={childId}
                blockId={childId}
                depth={1}
                isLast={index === childIds.length - 1}
                readOnly={hideEditControls}
              />
            ))}
          </div>

          {!hideEditControls && (
            <div className="relative pl-6 mt-4">
              {/* Connector for add button */}
              <div className="absolute left-3 top-0 h-7 w-0.5 bg-ink/25" />
              <div className="absolute left-3 top-7 w-3 h-0.5 bg-ink/25" />
              <AddBlockButton parentId={tree.rootId} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
