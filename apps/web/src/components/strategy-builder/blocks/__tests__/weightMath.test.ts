import type { StrategyTree, WeightBlock } from '@llamatrade/core/strategy/types';
import { describe, expect, it } from 'vitest';

import {
  dragEdge,
  edgePositions,
  knownWeights,
  roundKeepingSum,
  rowOf,
  setWeight,
  shareOfWhole,
  splitEvenly,
  total,
} from '../weightMath';

describe('splitEvenly', () => {
  it('splits into shares that add to 100', () => {
    expect(splitEvenly(4)).toEqual([25, 25, 25, 25]);
    const three = splitEvenly(3);
    expect(total(three)).toBe(100);
    expect(three).toEqual([33.4, 33.3, 33.3]);
  });

  it('returns nothing for no rows', () => {
    expect(splitEvenly(0)).toEqual([]);
  });
});

describe('roundKeepingSum', () => {
  it('keeps the rounded total', () => {
    expect(total(roundKeepingSum([33.333, 33.333, 33.334]))).toBe(100);
  });
});

describe('dragEdge', () => {
  it('moves weight between the two neighbours only', () => {
    expect(dragEdge([60, 40, 0], 0, -5)).toEqual([55, 45, 0]);
    expect(dragEdge([55, 35, 10], 1, 5)).toEqual([55, 40, 5]);
  });

  it('stops at zero on either side', () => {
    expect(dragEdge([60, 40], 0, 70)).toEqual([100, 0]);
    expect(dragEdge([60, 40], 0, -80)).toEqual([0, 100]);
  });

  it('ignores an edge that does not exist', () => {
    expect(dragEdge([100], 0, 5)).toEqual([100]);
  });
});

describe('setWeight', () => {
  it('moves the unlocked others in proportion', () => {
    expect(setWeight([60, 40], [false, false], 0, 70)).toEqual([70, 30]);
    expect(setWeight([50, 30, 20], [false, false, false], 0, 60)).toEqual([60, 24, 16]);
  });

  it('never moves a locked row', () => {
    expect(setWeight([55, 35, 10], [false, false, true], 0, 60)).toEqual([60, 30, 10]);
  });

  it('caps the row at what the locked rows leave', () => {
    expect(setWeight([50, 40, 10], [false, false, true], 0, 95)).toEqual([90, 0, 10]);
  });

  it('shares equally when the others are all zero', () => {
    expect(setWeight([100, 0, 0], [false, false, false], 0, 50)).toEqual([50, 25, 25]);
  });

  it('changes only the edited row when nothing can absorb it', () => {
    expect(setWeight([60, 40], [false, true], 0, 70)).toEqual([70, 40]);
  });
});

describe('edgePositions', () => {
  it('gives the running total after each row but the last', () => {
    expect(edgePositions([55, 35, 10])).toEqual([55, 90]);
  });
});

describe('block helpers', () => {
  const tree: StrategyTree = {
    rootId: 'r',
    blocks: {
      r: { id: 'r', type: 'root', parentId: null, name: 'S', childIds: ['w0'] },
      w0: {
        id: 'w0',
        type: 'weight',
        parentId: 'r',
        method: 'specified',
        allocations: { g: 60, a3: 40 },
        childIds: ['g', 'a3'],
      },
      g: { id: 'g', type: 'group', parentId: 'w0', name: 'Bonds', childIds: ['w1'] },
      w1: {
        id: 'w1',
        type: 'weight',
        parentId: 'g',
        method: 'equal',
        allocations: {},
        childIds: ['a1', 'a2'],
      },
      a1: {
        id: 'a1',
        type: 'asset',
        parentId: 'w1',
        symbol: 'TLT',
        exchange: '',
        displayName: 'TLT',
      },
      a2: {
        id: 'a2',
        type: 'asset',
        parentId: 'w1',
        symbol: 'GLD',
        exchange: '',
        displayName: 'SPDR Gold Shares',
      },
      a3: { id: 'a3', type: 'asset', parentId: 'w0', symbol: 'VTI', exchange: '', displayName: '' },
    },
  };

  it('labels rows by symbol, with a name only when it says more', () => {
    expect(rowOf(tree.blocks.a1, 'a1')).toMatchObject({ label: 'TLT', name: null });
    expect(rowOf(tree.blocks.a2, 'a2')).toMatchObject({ label: 'GLD', name: 'SPDR Gold Shares' });
    expect(rowOf(tree.blocks.g, 'g')).toMatchObject({ label: 'Bonds', isAsset: false });
  });

  it('knows fixed and equal weights, not ranked ones', () => {
    const w0 = tree.blocks.w0;
    const w1 = tree.blocks.w1;
    if (w0.type !== 'weight' || w1.type !== 'weight') throw new Error('fixture');
    expect(knownWeights(w0)).toEqual([60, 40]);
    expect(knownWeights(w1)).toEqual([50, 50]);
    expect(knownWeights({ ...w1, method: 'momentum' })).toBeNull();
  });

  it('multiplies shares down through fixed parents', () => {
    expect(shareOfWhole(tree, 'w1')).toBeCloseTo(0.6);
    expect(shareOfWhole(tree, 'w0')).toBe(1);
  });

  it('gives up under a ranked parent', () => {
    const ranked: StrategyTree = {
      ...tree,
      blocks: { ...tree.blocks, w0: { ...tree.blocks.w0, method: 'momentum' } as WeightBlock },
    };
    expect(shareOfWhole(ranked, 'w1')).toBeNull();
  });
});
