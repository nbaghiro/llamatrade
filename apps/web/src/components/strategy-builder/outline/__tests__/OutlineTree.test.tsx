import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { StrategyTree } from '@llamatrade/core/strategy/types';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { buildOutline } from '../../../../lib/outline';
import { heldPath } from '../../../../lib/outlineTree';
import { diffStrategies } from '../../../../lib/strategyDiff';
import { OutlineTree, ROOT_ROW } from '../OutlineTree';

const BASE = `(strategy "Recession Radar"
  :rebalance daily :benchmark SPY
  (if (< (price SPY) (sma SPY 200))
      (weight :method specified (asset TLT :weight 60) (asset GLD :weight 40))
      (else (asset SPY :weight 100))))`;

const PROPOSED = `(strategy "Recession Radar"
  :rebalance daily :benchmark SPY
  (if (< (price SPY) (sma SPY 200))
      (weight :method specified (asset TLT :weight 60) (asset GLD :weight 40))
      (else (weight :method equal (asset QQQ) (asset IEF)))))`;

function treeOf(dsl: string): StrategyTree {
  const parsed = fromDSLString(dsl);
  if (!parsed) throw new Error('DSL did not parse');
  return parsed.tree;
}

const meta = { timeframe: '1D', benchmark: 'SPY' };
const none = new Set<string>();

describe('OutlineTree', () => {
  it('draws the strategy, typed rows, weight shares and the branch held today', () => {
    const tree = treeOf(BASE);
    const out = renderToStaticMarkup(
      <OutlineTree
        name="Recession Radar"
        lines={buildOutline(tree)}
        live={heldPath(tree, new Set(['TLT', 'GLD']))}
        closed={none}
        onToggle={() => undefined}
        label="Strategy outline"
      />
    );
    for (const type of ['Strategy', 'If', 'Weight', 'Asset', 'Else'])
      expect(out).toContain(`>${type}<`);
    expect(out).toContain('Recession Radar');
    expect(out).toContain('60%');
    expect(out).toContain('Live today');
    expect(out).not.toContain('>If the');
  });

  it('marks Copilot’s added rows with + and removed rows with −', () => {
    const diff = diffStrategies({ tree: treeOf(BASE), meta }, { tree: treeOf(PROPOSED), meta });
    const out = renderToStaticMarkup(
      <OutlineTree
        name="Recession Radar"
        lines={diff.lines}
        live={none}
        closed={none}
        onToggle={() => undefined}
        label="Strategy outline with the proposed change"
      />
    );
    expect(out).toContain('>+<');
    expect(out).toContain('>−<');
    expect(out).toContain('QQQ');
    expect(out).toContain('aria-label="Removed: SPY"');
    expect(out).not.toContain('Live today');
  });

  it('hides the rows under a closed row and counts them', () => {
    const tree = treeOf(BASE);
    const lines = buildOutline(tree);
    const ifKey = lines.find((l) => l.kind === 'if')?.key ?? '';
    const out = renderToStaticMarkup(
      <OutlineTree
        name="Recession Radar"
        lines={lines}
        live={none}
        closed={new Set([ifKey])}
        onToggle={() => undefined}
        label="Strategy outline"
      />
    );
    expect(out).toContain('3 hidden');
    expect(out).not.toContain('TLT');
    const all = renderToStaticMarkup(
      <OutlineTree
        name="Recession Radar"
        lines={lines}
        live={none}
        closed={new Set([ROOT_ROW])}
        onToggle={() => undefined}
        label="Strategy outline"
      />
    );
    expect(all).not.toContain('>If<');
  });
});
