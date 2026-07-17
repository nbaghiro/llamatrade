/**
 * Strategy-tree data model + the pre-order reveal-index helper. Kept in a plain
 * module (not the component file) so StrategyTree.tsx only exports components and
 * React Fast Refresh stays happy.
 */

export type BlockKind = 'strategy' | 'if' | 'filter' | 'weight' | 'else' | 'asset';

/** A strategy block before pre-order reveal indices are assigned. */
export interface RawNode {
  kind: BlockKind;
  /** Coloured keyword prefix (empty for leaf assets). */
  kw: string;
  label: string;
  /** Optional allocation badge, e.g. "33%" (omitted for computed weight methods). */
  weight?: string;
  children?: RawNode[];
}

/** A strategy block with a pre-order reveal index (`seq`) assigned. */
export interface TreeNode extends RawNode {
  /** Pre-order reveal index (0-based). */
  seq: number;
  children?: TreeNode[];
}

/**
 * Assign pre-order reveal indices to every node and return the total block
 * count. Callers use `count` to drive build/hold/clear animation phases.
 */
export function prepareTree(raw: RawNode): { tree: TreeNode; count: number } {
  let n = 0;
  const walk = (node: RawNode): TreeNode => {
    const seq = n++;
    const children = node.children?.map(walk);
    return { ...node, seq, children };
  };
  const tree = walk(raw);
  return { tree, count: n };
}
