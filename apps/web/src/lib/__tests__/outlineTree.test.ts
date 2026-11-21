import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { StrategyTree } from '@llamatrade/core/strategy/types';
import { describe, expect, it } from 'vitest';

import { buildOutline } from '../outline';
import { ancestors, collapse, guidesOf, heldPath, phraseParts, withKids } from '../outlineTree';

const RADAR = `(strategy "Recession Radar"
  :rebalance daily :benchmark SPY
  (if (< (price SPY) (sma SPY 200))
      (group "Defensive" (weight :method specified (asset TLT :weight 60) (asset GLD :weight 40)))
      (else (asset SPY :weight 100))))`;

function treeOf(dsl: string): StrategyTree {
  const parsed = fromDSLString(dsl);
  if (!parsed) throw new Error('DSL did not parse');
  return parsed.tree;
}

const rows = [
  { id: 'a', depth: 0 },
  { id: 'b', depth: 1 },
  { id: 'c', depth: 2 },
  { id: 'd', depth: 2 },
  { id: 'e', depth: 1 },
];

describe('withKids and collapse', () => {
  it('marks rows with children', () => {
    expect(withKids(rows).map((r) => r.kids)).toEqual([true, true, false, false, false]);
  });

  it('drops rows under a closed row and counts them', () => {
    const shown = collapse(withKids(rows), new Set(['b']));
    expect(shown.map((r) => r.id)).toEqual(['a', 'b', 'e']);
    expect(shown[1].hidden).toBe(2);
  });

  it('ignores a closed leaf', () => {
    expect(collapse(withKids(rows), new Set(['c'])).map((r) => r.hidden)).toEqual([0, 0, 0, 0, 0]);
  });
});

describe('guidesOf', () => {
  it('draws an elbow into each row and a line past it while a sibling follows', () => {
    const g = guidesOf(rows.map((r) => ({ ...r, live: false })));
    expect(g[0]).toEqual([]);
    expect(g[1][0]).toMatchObject({ elbow: true, down: true });
    expect(g[2][0]).toMatchObject({ elbow: false, down: true });
    expect(g[3][1]).toMatchObject({ elbow: true, down: false });
    expect(g[4][0]).toMatchObject({ elbow: true, down: false });
  });

  it('inks only the live path', () => {
    const live = rows.map((r) => ({ ...r, live: ['a', 'b', 'd'].includes(r.id) }));
    const g = guidesOf(live);
    expect(g[1][0]).toMatchObject({ liveAcross: true, liveUp: true });
    expect(g[2][1]).toMatchObject({ liveAcross: false, liveDown: true });
    expect(g[3][1]).toMatchObject({ liveAcross: true });
    expect(g[4][0].liveAcross).toBe(false);
  });
});

describe('ancestors', () => {
  it('collects a row and every row above it', () => {
    expect([...ancestors(rows, 'd')].sort()).toEqual(['a', 'b', 'd']);
    expect(ancestors(rows, 'missing').size).toBe(0);
  });
});

describe('heldPath', () => {
  const tree = treeOf(RADAR);
  const idOf = (symbol: string) =>
    Object.values(tree.blocks).find((b) => b.type === 'asset' && b.symbol === symbol)?.id;
  const kindIn = (path: Set<string>, kind: string) =>
    Object.values(tree.blocks).some((b) => b.type === kind && path.has(b.id));

  it('lights the branch whose holdings the session holds', () => {
    const path = heldPath(tree, new Set(['TLT', 'GLD']));
    expect(path.has(idOf('TLT') ?? '')).toBe(true);
    expect(kindIn(path, 'if')).toBe(true);
    expect(kindIn(path, 'else')).toBe(false);
  });

  it('lights the otherwise when it covers more of the holdings', () => {
    const path = heldPath(tree, new Set(['SPY']));
    expect(kindIn(path, 'else')).toBe(true);
    expect(kindIn(path, 'if')).toBe(false);
  });

  it('is empty with nothing held', () => {
    expect(heldPath(tree, new Set()).size).toBe(0);
    expect(heldPath(tree, new Set(['QQQ'])).size).toBe(0);
  });
});

describe('phraseParts', () => {
  it('drops the words the type label already says', () => {
    const lines = buildOutline(treeOf(RADAR));
    const text = (kind: (typeof lines)[number]['kind']) => {
      const line = lines.find((l) => l.kind === kind);
      return line
        ? phraseParts(kind, line.parts)
            .map((p) => p.text)
            .join('')
        : '';
    };
    expect(text('if').startsWith('If')).toBe(false);
    expect(text('group')).toBe('Defensive at 100%');
    expect(text('weight')).toBe('fixed weights');
    expect(text('else')).toBe('Otherwise');
  });
});
