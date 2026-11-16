import { toDSL, fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { Block, BlockId, StrategyTree, WeightBlock } from '@llamatrade/core/strategy/types';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { reconcileIds, useStrategyBuilderStore } from '../strategy-builder';

const parse = (dsl: string): StrategyTree => {
  const parsed = fromDSLString(dsl);
  if (!parsed) throw new Error(`failed to parse: ${dsl}`);
  return parsed.tree;
};

describe('reconcileIds', () => {
  it('preserves ids for structurally-identical trees (fresh parse ⇒ same ids)', () => {
    const dsl =
      '(strategy "S" (if (> (rsi SPY 14) 70) (weight :method equal (asset AAPL)) (else (weight :method equal (asset SHY)))))';
    const oldTree = parse(dsl);
    const newTree = parse(dsl); // fresh parse mints new ids
    const out = reconcileIds(oldTree, newTree);

    // Every reconciled id already exists in the old tree — nothing churned.
    for (const id of Object.keys(out.blocks)) {
      expect(oldTree.blocks[id]).toBeDefined();
    }
    expect(out.rootId).toBe(oldTree.rootId);

    // The else block's ifBlockId is remapped onto a surviving id.
    const elseBlock = Object.values(out.blocks).find((b) => b.type === 'else');
    expect(elseBlock && out.blocks[(elseBlock as { ifBlockId: string }).ifBlockId]?.type).toBe(
      'if'
    );
  });

  it('keeps ids for edited-in-place blocks, mints ids for added ones, and re-keys allocations', () => {
    const asset = (id: string, parentId: BlockId, symbol: string): Block => ({
      id,
      type: 'asset',
      parentId,
      symbol,
      exchange: 'NASDAQ',
      displayName: symbol,
    });
    // Distinct ids on each side simulate a fresh parse; new tree edits MSFT→GOOGL and adds TSLA.
    const oldTree: StrategyTree = {
      rootId: 'r',
      blocks: {
        r: { id: 'r', type: 'root', parentId: null, name: 'S', childIds: ['w'] },
        w: {
          id: 'w',
          type: 'weight',
          parentId: 'r',
          method: 'specified',
          allocations: { oa: 50, ob: 50 },
          childIds: ['oa', 'ob'],
        },
        oa: asset('oa', 'w', 'AAPL'),
        ob: asset('ob', 'w', 'MSFT'),
      },
    };
    const newTree: StrategyTree = {
      rootId: 'R',
      blocks: {
        R: { id: 'R', type: 'root', parentId: null, name: 'S', childIds: ['W'] },
        W: {
          id: 'W',
          type: 'weight',
          parentId: 'R',
          method: 'specified',
          allocations: { na: 40, nb: 30, nc: 30 },
          childIds: ['na', 'nb', 'nc'],
        },
        na: asset('na', 'W', 'AAPL'),
        nb: asset('nb', 'W', 'GOOGL'),
        nc: asset('nc', 'W', 'TSLA'),
      },
    };

    const out = reconcileIds(oldTree, newTree);
    const ow = out.blocks['w'] as WeightBlock;

    expect(out.rootId).toBe('r'); // root id preserved
    expect(ow.childIds).toEqual(['oa', 'ob', 'nc']); // first two reused, third new
    expect((out.blocks['ob'] as { symbol: string }).symbol).toBe('GOOGL'); // edit landed on reused id
    expect(ow.allocations).toEqual({ oa: 40, ob: 30, nc: 30 }); // allocations re-keyed onto out ids
  });
});

describe('live code⇄tree sync', () => {
  const store = useStrategyBuilderStore;

  beforeEach(() => {
    store.getState().reset();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('setViewMode(split) regenerates the code buffer from the tree', () => {
    store.getState().setViewMode('tree');
    store.getState().setViewMode('split');
    const s = store.getState();
    expect(s.viewMode).toBe('split');
    expect(s.dslCode).toBe(
      toDSL(s.tree, {
        name: s.strategyName,
        description: s.strategyDescription,
        timeframe: s.timeframe,
      })
    );
  });

  it('adopts the starter code into an empty tree so the outline matches the code', () => {
    store.getState().createNew();
    store.getState().setViewMode('code');
    const s = store.getState();
    const symbols = Object.values(s.tree.blocks)
      .filter((b) => b.type === 'asset')
      .map((b) => (b as { symbol: string }).symbol);
    expect(symbols).toEqual(['SPY']);
    expect(fromDSLString(s.dslCode)).not.toBeNull();
  });

  it('commits valid typed DSL into the tree after the debounce', () => {
    store.getState().setViewMode('split');
    store
      .getState()
      .updateDSLCode(
        '(strategy "Rot" :rebalance monthly (weight :method equal (asset SPY) (asset GLD)))'
      );
    vi.advanceTimersByTime(CODE_COMMIT_WAIT);

    const tree = store.getState().tree;
    const root = tree.blocks[tree.rootId] as { type: string; childIds: string[] };
    expect(root.type).toBe('root');
    const weight = tree.blocks[root.childIds[0]];
    expect(weight?.type).toBe('weight');
    expect(store.getState().dslParseError).toBeNull();
  });

  it('carries :benchmark through the store round-trip', () => {
    const dsl =
      '(strategy "Bench" :rebalance weekly :benchmark QQQ (weight :method equal (asset SPY) (asset BND)))';
    store.getState().setViewMode('split');
    store.getState().updateDSLCode(dsl);
    vi.advanceTimersByTime(CODE_COMMIT_WAIT);

    expect(store.getState().dslParseError).toBeNull();
    expect(store.getState().benchmark).toBe('QQQ');
    expect(store.getState().getDSLCode()).toContain(':benchmark QQQ');
  });

  it('drops :benchmark when the code no longer declares one', () => {
    store.getState().setViewMode('split');
    store
      .getState()
      .updateDSLCode(
        '(strategy "Bench" :rebalance weekly :benchmark QQQ (weight :method equal (asset SPY)))'
      );
    vi.advanceTimersByTime(CODE_COMMIT_WAIT);
    store
      .getState()
      .updateDSLCode('(strategy "Bench" :rebalance weekly (weight :method equal (asset SPY)))');
    vi.advanceTimersByTime(CODE_COMMIT_WAIT);

    expect(store.getState().benchmark).toBe('');
    expect(store.getState().getDSLCode()).not.toContain(':benchmark');
  });

  it('keeps the last good tree and surfaces an error on invalid DSL', () => {
    store.getState().setViewMode('split');
    store.getState().updateDSLCode('(strategy "Rot" (weight :method equal (asset SPY)))');
    vi.advanceTimersByTime(CODE_COMMIT_WAIT);
    const goodTree = store.getState().tree;

    store.getState().updateDSLCode('(weight :method equal (asset SPY))'); // non-strategy root ⇒ rejected
    vi.advanceTimersByTime(CODE_COMMIT_WAIT);

    expect(store.getState().tree).toBe(goodTree); // unchanged reference
    expect(store.getState().dslParseError).toBeTruthy();
  });
});

const CODE_COMMIT_WAIT = 400;

describe('applyDSL', () => {
  const store = useStrategyBuilderStore;

  beforeEach(() => {
    store.getState().reset();
    store
      .getState()
      .loadFromDSL(
        '(strategy "Radar" :rebalance monthly (weight :method momentum :lookback 90 (asset VTI) (asset QQQ)))'
      );
  });

  it('applies a proposal as one undoable edit and keeps block ids', () => {
    const before = store.getState().tree;
    const ok = store
      .getState()
      .applyDSL(
        '(strategy "Radar" :rebalance monthly (weight :method momentum :lookback 120 (asset VTI) (asset QQQ)))'
      );
    const s = store.getState();
    expect(ok).toBe(true);
    expect(Object.keys(s.tree.blocks).sort()).toEqual(Object.keys(before.blocks).sort());
    const weight = Object.values(s.tree.blocks).find((b) => b.type === 'weight') as WeightBlock;
    expect(weight.lookbackDays).toBe(120);
    expect(s.isDirty).toBe(true);
    s.undo();
    const undone = Object.values(store.getState().tree.blocks).find(
      (b) => b.type === 'weight'
    ) as WeightBlock;
    expect(undone.lookbackDays).toBe(90);
  });

  it('keeps the draft name and refuses text that does not parse', () => {
    const tree = store.getState().tree;
    expect(store.getState().applyDSL('(strategy "Other" (weight :method equal (asset SPY)))')).toBe(
      true
    );
    expect(store.getState().strategyName).toBe('Radar');
    const after = store.getState().tree;
    expect(after).not.toBe(tree);
    expect(store.getState().applyDSL('(weight :method equal')).toBe(false);
    expect(store.getState().tree).toBe(after);
  });

  it('treats a loaded draft as unsaved, with no saved version to compare against', () => {
    expect(store.getState().savedDsl).toBeNull();
    expect(store.getState().viewMode).toBe('tree');
  });
});
