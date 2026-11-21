import type { Block, BlockId, StrategyTree } from '@llamatrade/core/strategy/types';

import { matchBlocks } from '../../../lib/strategyDiff';

export interface VersionTree {
  version: number;
  tree: StrategyTree;
}

export interface ValueChange {
  /** The version that set today's value. */
  version: number;
  /** The value before that version, as read. */
  was: string;
}

/**
 * When a block's value last changed, walking back through saved versions (newest first, the
 * first entry being the current one). Null when it reads the same in every version, or the
 * block can't be traced back.
 */
export function lastChange(
  versions: readonly VersionTree[],
  blockId: BlockId,
  read: (block: Block, tree: StrategyTree) => string | null
): ValueChange | null {
  if (versions.length < 2) return null;
  let id: BlockId | undefined = blockId;
  let current = versions[0];
  const now = current.tree.blocks[blockId];
  const value = now ? read(now, current.tree) : null;
  if (value === null) return null;
  for (let i = 1; i < versions.length && id !== undefined; i++) {
    const older = versions[i];
    const olderId: BlockId | undefined = matchBlocks(older.tree, current.tree).get(id);
    const block = olderId !== undefined ? older.tree.blocks[olderId] : undefined;
    if (!block) return null;
    const was = read(block, older.tree);
    if (was !== value) return was === null ? null : { version: current.version, was };
    id = olderId;
    current = older;
  }
  return null;
}
