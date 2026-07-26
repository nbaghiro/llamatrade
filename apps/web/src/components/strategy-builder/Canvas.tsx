import type { BlockId, ConditionExpression } from '@llamatrade/core/strategy/types';
import { hasChildren } from '@llamatrade/core/strategy/types';
import { ChevronDown, Pencil, X } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { useStrategyBuilderStoreWithContext } from '../../store/strategy-builder';
import {
  StrategyBlockRow,
  StrategyTree,
  type StrategyTreeRowContext,
  type TreeNode,
} from '../common/StrategyTree';
import { prepareTree } from '../common/strategyTreeModel';

import { AddBlockButton } from './blocks/AddBlockButton';
import { PercentageBadge } from './blocks/PercentageBadge';
import { ConditionEditor } from './panels/ConditionEditor';
import { strategyTreeToRawNode } from './treeAdapter';

interface CanvasProps {
  readOnly?: boolean;
}

const TEST_IDS: Partial<Record<string, string>> = {
  if: 'if-block',
  asset: 'asset-block',
  weight: 'weight-block',
  else: 'else-block',
};

/**
 * The interactive builder tree — renders through the shared {@link StrategyTree}
 * (the same component the auth animation and previews use), layering the
 * builder's select / expand / delete / edit affordances via the `renderRow`
 * slot. Rows are the shared {@link StrategyBlockRow}; only interactivity differs.
 */
export function Canvas({ readOnly }: CanvasProps) {
  const {
    tree,
    ui,
    compactView,
    selectBlock,
    toggleExpand,
    deleteBlock,
    setEditing,
    updateBlock,
    updateCondition,
  } = useStrategyBuilderStoreWithContext();

  const hideEditControls = readOnly || compactView;

  const [editingConditionId, setEditingConditionId] = useState<BlockId | null>(null);
  const [groupDraft, setGroupDraft] = useState('');

  const firstSymbol =
    Object.values(tree.blocks).find((b) => b.type === 'asset')?.symbol ?? 'SPY';

  // Close the inline condition editor on an outside click.
  useEffect(() => {
    if (!editingConditionId) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-condition-editor]')) setEditingConditionId(null);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [editingConditionId]);

  const rootNode = useMemo(() => {
    const raw = strategyTreeToRawNode(tree, { isExpanded: (id) => ui.expandedBlocks.has(id) });
    return raw ? prepareTree(raw).tree : null;
  }, [tree, ui.expandedBlocks]);

  const handleCanvasClick = () => {
    if (!hideEditControls) selectBlock(null);
  };

  const stop = (fn: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    fn();
  };

  const renderRow = ({ node }: StrategyTreeRowContext) => {
    const block = tree.blocks[node.id];
    if (!block) return null;
    const id = block.id;
    const isSelected = !hideEditControls && ui.selectedBlockId === id;
    const canExpand = hasChildren(block);
    const isExpanded = ui.expandedBlocks.has(id);

    // Inline group rename.
    if (!hideEditControls && block.type === 'group' && ui.editingBlockId === id) {
      const commit = () => {
        updateBlock(id, { name: groupDraft.trim() || 'Unnamed Group' });
        setEditing(null);
      };
      return (
        <div className="relative flex min-h-[40px] w-[480px] items-center gap-2.5 border-2 border-l-[5px] border-ink border-l-ink bg-paper px-3.5 py-1.5">
          <input
            autoFocus
            value={groupDraft}
            onChange={(e) => setGroupDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commit();
              else if (e.key === 'Escape') setEditing(null);
            }}
            onBlur={commit}
            onClick={(e) => e.stopPropagation()}
            className="flex-1 border-2 border-ink bg-bone px-2 py-0.5 font-mono text-[13px] outline-none"
          />
        </div>
      );
    }

    const leading =
      !hideEditControls && canExpand ? (
        <button
          onClick={stop(() => toggleExpand(id))}
          title={isExpanded ? 'Collapse' : 'Expand'}
          className="-ml-0.5 opacity-60 transition-opacity hover:opacity-100"
        >
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
        </button>
      ) : undefined;

    const parentBlock = block.parentId ? tree.blocks[block.parentId] : undefined;
    const isSpecifiedChild =
      !hideEditControls && parentBlock?.type === 'weight' && parentBlock.method === 'specified';

    const trailingEls: ReactNode[] = [];
    if (!hideEditControls && block.type === 'if') {
      trailingEls.push(
        <button
          key="edit"
          onClick={stop(() => {
            selectBlock(id);
            setEditingConditionId(id);
          })}
          title="Edit condition"
          className="p-0.5 text-ink/60 hover:text-ink"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      );
    }
    if (isSpecifiedChild && block.parentId) {
      trailingEls.push(
        <PercentageBadge key="pct" weightBlockId={block.parentId} childBlockId={id} />
      );
    }
    if (!hideEditControls && block.type !== 'root') {
      // Delete lives on the right, hover-revealed — keeps the default row clean.
      trailingEls.push(
        <button
          key="del"
          onClick={stop(() => deleteBlock(id))}
          title="Delete"
          className="ml-0.5 opacity-0 transition-opacity hover:text-red-600 group-hover:opacity-80"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      );
    }
    const trailing = trailingEls.length ? <>{trailingEls}</> : undefined;
    // The editable badge replaces the static allocation badge in edit mode.
    const rowNode = isSpecifiedChild ? { ...node, weight: undefined } : node;

    const onDoubleClick =
      !hideEditControls && block.type === 'group'
        ? (e: React.MouseEvent) => {
            e.stopPropagation();
            setGroupDraft(block.name);
            setEditing(id);
          }
        : undefined;

    const row = (
      <StrategyBlockRow
        node={rowNode as TreeNode}
        ground="bone"
        comfortable
        selected={isSelected}
        leading={leading}
        trailing={trailing}
        onClick={hideEditControls ? undefined : stop(() => selectBlock(id))}
        onDoubleClick={onDoubleClick}
        testId={TEST_IDS[block.type]}
        dataSymbol={block.type === 'asset' ? block.symbol : undefined}
        className={hideEditControls ? 'cursor-default' : 'cursor-pointer'}
      />
    );

    if (editingConditionId === id && block.type === 'if') {
      const handleSave = (condition: ConditionExpression) => {
        updateCondition(id, condition);
        setEditingConditionId(null);
      };
      return (
        <div className="relative" data-condition-editor>
          {row}
          <div className="absolute left-0 top-full z-50 mt-2">
            <ConditionEditor
              condition={block.condition}
              defaultSymbol={firstSymbol}
              onSave={handleSave}
              onCancel={() => setEditingConditionId(null)}
            />
          </div>
        </div>
      );
    }

    return row;
  };

  const renderAfterChildren = (node: TreeNode) => {
    if (hideEditControls) return null;
    const block = tree.blocks[node.id];
    if (!block || !hasChildren(block) || !ui.expandedBlocks.has(node.id)) return null;
    return (
      <div className="mt-2">
        <AddBlockButton parentId={node.id} />
      </div>
    );
  };

  return (
    <div className="no-scrollbar flex-1 overflow-auto pb-24" onClick={handleCanvasClick}>
      <div className="w-full pt-1">
        {rootNode && (
          <StrategyTree
            node={rootNode}
            ground="bone"
            comfortable
            renderRow={renderRow}
            renderAfterChildren={renderAfterChildren}
          />
        )}
      </div>
    </div>
  );
}
