/**
 * Strategy-tree data model + pre-order reveal-index helpers. Kept in a plain
 * module (not the component file) so StrategyTree.tsx only exports components and
 * React Fast Refresh stays happy.
 *
 * This is the single presentational model shared by every strategy-tree render
 * site: the interactive builder (via `blockTreeToRawNode`), the auth build
 * animation, marketing, previews, and empty states.
 */

export type BlockKind =
  | 'strategy'
  | 'root'
  | 'group'
  | 'if'
  | 'filter'
  | 'weight'
  | 'else'
  | 'asset';

/** A strategy block before pre-order reveal indices are assigned. */
export interface RawNode {
  kind: BlockKind;
  /** Coloured keyword prefix (empty for leaf assets). */
  kw: string;
  label: string;
  /** Optional allocation badge, e.g. "33%" (omitted for computed weight methods). */
  weight?: string;
  /** Stable id — the builder passes real BlockIds; synthesized from `seq` when absent. */
  id?: string;
  children?: RawNode[];
}

/** A strategy block with a pre-order reveal index (`seq`) and a resolved id. */
export interface TreeNode extends RawNode {
  /** Pre-order reveal index (0-based). */
  seq: number;
  id: string;
  children?: TreeNode[];
}

function walkWith(counter: { n: number }): (node: RawNode) => TreeNode {
  const walk = (node: RawNode): TreeNode => {
    const seq = counter.n++;
    const id = node.id ?? `n${seq}`;
    const children = node.children?.map(walk);
    return { ...node, seq, id, children };
  };
  return walk;
}

/**
 * Assign pre-order reveal indices to a single-rooted tree and return the total
 * block count. Callers use `count` to drive build/hold/clear animation phases.
 */
export function prepareTree(raw: RawNode): { tree: TreeNode; count: number } {
  const counter = { n: 0 };
  const tree = walkWith(counter)(raw);
  return { tree, count: counter.n };
}

/**
 * Assign pre-order reveal indices across a forest (used by the builder, which
 * renders the root's children rather than a single root node).
 */
export function prepareForest(raws: RawNode[]): { nodes: TreeNode[]; count: number } {
  const counter = { n: 0 };
  const nodes = raws.map(walkWith(counter));
  return { nodes, count: counter.n };
}
