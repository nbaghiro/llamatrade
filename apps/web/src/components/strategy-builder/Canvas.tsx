import { useStrategyBuilderStore } from '../../store/strategy-builder';

import { TreeNode } from './TreeNode';

export function Canvas() {
  const { tree, selectBlock } = useStrategyBuilderStore();

  // Deselect when clicking on empty canvas area
  const handleCanvasClick = () => {
    selectBlock(null);
  };

  return (
    <div
      className="flex-1 min-w-0 overflow-auto pt-4 px-6 pb-24"
      onClick={handleCanvasClick}
    >
      <TreeNode blockId={tree.rootId} />
    </div>
  );
}
