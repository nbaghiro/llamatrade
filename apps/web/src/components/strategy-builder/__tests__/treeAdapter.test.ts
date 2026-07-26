import type { Block, BlockId, StrategyTree } from '@llamatrade/core/strategy/types';
import { getWeightMethodInfo } from '@llamatrade/core/strategy/types';
import { describe, expect, it } from 'vitest';

import { blockToRawNode, rootChildrenToRawNodes } from '../treeAdapter';

function makeTree(): StrategyTree {
  const blocks: Record<BlockId, Block> = {
    root: { id: 'root', type: 'root', parentId: null, name: 'Test', childIds: ['grp'] },
    grp: { id: 'grp', type: 'group', parentId: 'root', name: 'Core', childIds: ['w'] },
    w: {
      id: 'w',
      type: 'weight',
      parentId: 'grp',
      method: 'specified',
      allocations: { a: 60, b: 40 },
      childIds: ['a', 'b'],
    },
    a: { id: 'a', type: 'asset', parentId: 'w', symbol: 'AAPL', exchange: 'NASDAQ', displayName: 'Apple' },
    b: { id: 'b', type: 'asset', parentId: 'w', symbol: 'MSFT', exchange: 'NASDAQ', displayName: 'Microsoft' },
  };
  return { rootId: 'root', blocks };
}

describe('treeAdapter', () => {
  it('maps a block subtree to the shared RawNode model with kinds, kws and labels', () => {
    const tree = makeTree();
    const node = blockToRawNode(tree, 'grp');

    expect(node?.kind).toBe('group');
    expect(node?.kw).toBe('GROUP');
    expect(node?.label).toBe('Core');
    expect(node?.id).toBe('grp');

    const weight = node?.children?.[0];
    expect(weight?.kind).toBe('weight');
    expect(weight?.kw).toBe('WEIGHT');
    expect(weight?.label).toBe(getWeightMethodInfo('specified').label);
  });

  it('adds allocation badges to direct children of a specified weight', () => {
    const tree = makeTree();
    const [group] = rootChildrenToRawNodes(tree);
    const assets = group?.children?.[0]?.children;
    const assetA = assets?.[0];
    const assetB = assets?.[1];

    expect(assetA?.kind).toBe('asset');
    expect(assetA?.kw).toBe('AAPL');
    expect(assetA?.label).toBe('Apple');
    expect(assetA?.weight).toBe('60%');
    expect(assetB?.weight).toBe('40%');
  });

  it('prunes children of collapsed blocks when an isExpanded predicate is given', () => {
    const tree = makeTree();
    const expandedAll = rootChildrenToRawNodes(tree, { isExpanded: () => true });
    expect(expandedAll[0].children).toBeDefined();

    const collapsedGroup = rootChildrenToRawNodes(tree, { isExpanded: (id) => id !== 'grp' });
    expect(collapsedGroup[0].kind).toBe('group');
    expect(collapsedGroup[0].children).toBeUndefined();
  });
});
