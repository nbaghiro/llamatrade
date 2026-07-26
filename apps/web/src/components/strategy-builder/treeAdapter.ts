/**
 * Adapter: the builder's flat, id-keyed `Block` model (`@llamatrade/core`) →
 * the shared presentational `RawNode` model (`common/strategyTreeModel`). This
 * is what lets the interactive builder render through the same `StrategyTree`
 * component as the auth animation, marketing, and previews.
 *
 * Labels are derived with the exact same helpers the builder blocks used before
 * unification (`conditionToText`, `getWeightMethodInfo`, `displayText`,
 * `FILTER_UNIVERSES`), so the text is unchanged — only the rendering converges.
 */

import { conditionToText } from '@llamatrade/core/strategy/serializer';
import type { BlockId, StrategyTree } from '@llamatrade/core/strategy/types';
import { FILTER_UNIVERSES, getWeightMethodInfo, hasChildren } from '@llamatrade/core/strategy/types';

import type { RawNode } from '../common/strategyTreeModel';

export interface AdaptOptions {
  /** When provided, a block's children are omitted unless it returns true (collapse). */
  isExpanded?: (id: BlockId) => boolean;
}

/** Allocation badge for a direct child of a `specified` weight, else undefined. */
function childBadge(tree: StrategyTree, parentId: BlockId, childId: BlockId): string | undefined {
  const parent = tree.blocks[parentId];
  if (parent?.type === 'weight' && parent.method === 'specified') {
    return `${parent.allocations[childId] ?? 0}%`;
  }
  return undefined;
}

/** Convert a single block (and its subtree) to a presentational RawNode. */
export function blockToRawNode(
  tree: StrategyTree,
  blockId: BlockId,
  opts?: AdaptOptions,
  weight?: string
): RawNode | null {
  const block = tree.blocks[blockId];
  if (!block) return null;

  const expanded = opts?.isExpanded ? opts.isExpanded(blockId) : true;
  const children =
    expanded && hasChildren(block)
      ? block.childIds
          .map((cid) => blockToRawNode(tree, cid, opts, childBadge(tree, blockId, cid)))
          .filter((n): n is RawNode => n !== null)
      : undefined;

  switch (block.type) {
    case 'root':
      return { kind: 'root', kw: 'STRATEGY', label: block.name, id: block.id, children };
    case 'asset':
      return { kind: 'asset', kw: block.symbol, label: block.displayName, weight, id: block.id };
    case 'group':
      return { kind: 'group', kw: 'GROUP', label: block.name, weight, id: block.id, children };
    case 'weight': {
      const info = getWeightMethodInfo(block.method);
      const label =
        info.hasLookback && block.lookbackDays ? `${info.label} ${block.lookbackDays}d` : info.label;
      return { kind: 'weight', kw: 'WEIGHT', label, weight, id: block.id, children };
    }
    case 'if':
      return { kind: 'if', kw: 'IF', label: conditionToText(block.condition), weight, id: block.id, children };
    case 'else':
      return { kind: 'else', kw: 'ELSE', label: '', weight, id: block.id, children };
    case 'filter': {
      const universe = FILTER_UNIVERSES.find((u) => u.value === block.config.universe);
      const label = universe ? `${block.displayText} · ${universe.label}` : block.displayText;
      return { kind: 'filter', kw: 'FILTER', label, weight, id: block.id, children };
    }
  }
}

/** Map only the root's children to a forest (root omitted). */
export function rootChildrenToRawNodes(tree: StrategyTree, opts?: AdaptOptions): RawNode[] {
  const root = tree.blocks[tree.rootId];
  if (!root || !hasChildren(root)) return [];
  return root.childIds
    .map((cid) => blockToRawNode(tree, cid, opts, childBadge(tree, tree.rootId, cid)))
    .filter((n): n is RawNode => n !== null);
}

/** Whole-tree RawNode (root included) — for previews that render the full tree. */
export function strategyTreeToRawNode(tree: StrategyTree, opts?: AdaptOptions): RawNode | null {
  return blockToRawNode(tree, tree.rootId, opts);
}

export interface AllocationSlice {
  symbol: string;
  pct: number;
}

/**
 * Structural allocation ESTIMATE (not a live evaluation). Walks the tree giving
 * each `specified` weight its declared splits and every other parent an equal
 * split, and assumes conditions evaluate true (skips `else` branches). Good
 * enough for an at-a-glance holdings bar; momentum / inverse-vol / filtered
 * strategies only resolve exactly at run time.
 */
export function estimateAllocation(tree: StrategyTree): AllocationSlice[] {
  const acc = new Map<string, number>();

  const walk = (id: BlockId, weight: number): void => {
    const b = tree.blocks[id];
    if (!b) return;
    if (b.type === 'asset') {
      acc.set(b.symbol, (acc.get(b.symbol) ?? 0) + weight);
      return;
    }
    if (!hasChildren(b)) return;
    // Assume conditions are true → ignore the else branch for a structural view.
    const kids = b.childIds.filter((k) => tree.blocks[k]?.type !== 'else');
    if (kids.length === 0) return;

    if (b.type === 'weight' && b.method === 'specified') {
      const total = kids.reduce((s, k) => s + (b.allocations[k] ?? 0), 0);
      if (total > 0) {
        kids.forEach((k) => walk(k, weight * ((b.allocations[k] ?? 0) / total)));
        return;
      }
    }
    kids.forEach((k) => walk(k, weight / kids.length));
  };

  walk(tree.rootId, 1);
  return [...acc.entries()]
    .map(([symbol, w]) => ({ symbol, pct: w * 100 }))
    .sort((a, b) => b.pct - a.pct);
}
