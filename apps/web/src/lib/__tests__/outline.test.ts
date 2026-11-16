import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { IfBlock, StrategyTree, WeightBlock } from '@llamatrade/core/strategy/types';
import { describe, expect, it } from 'vitest';

import {
  allocationProblem,
  applyTokenEdit,
  buildOutline,
  childShare,
  isSupportedMethod,
  lineText,
  longestLookback,
  metaParts,
  partsText,
  ruleNumbers,
  strategySymbols,
  writtenScenarios,
  type OutlineLine,
  type OutlineToken,
  type TokenField,
} from '../outline';

const RADAR = `(strategy "Recession Radar"
  :rebalance monthly :benchmark SPY
  (if (> (rsi SPY 14) 70)
      (weight :method specified
        (asset TLT :weight 60)
        (asset GLD :weight 40))
      (else
        (weight :method momentum
          :lookback 90 :top 2
          (asset VTI) (asset QQQ)
          (asset IWM)))))`;

const parse = (dsl: string): StrategyTree => {
  const parsed = fromDSLString(dsl);
  if (!parsed) throw new Error(`failed to parse: ${dsl}`);
  return parsed.tree;
};

const tokenOf = (lines: OutlineLine[], field: TokenField, nth = 0): OutlineToken => {
  const found = lines
    .flatMap((l) => l.parts)
    .filter((p): p is OutlineToken => p.kind === 'token' && p.field === field);
  const tok = found[nth];
  if (!tok) throw new Error(`no token ${field}`);
  return tok;
};

describe('buildOutline', () => {
  const tree = parse(RADAR);
  const lines = buildOutline(tree);

  it('writes each rule as a numbered sentence in reading order', () => {
    const rules = lines.filter((l) => l.number !== null);
    expect(rules.map((l) => [l.number, lineText(l)])).toEqual([
      [1, 'If the 14-day RSI of SPY is above 70'],
      [2, 'hold fixed weights'],
      [3, 'Otherwise'],
      [4, 'hold the top 2, weighted by momentum over 90 days'],
    ]);
  });

  it('nests branch contents one level deeper than the rule that owns them', () => {
    const byText = (t: string) => lines.find((l) => lineText(l) === t);
    expect(byText('If the 14-day RSI of SPY is above 70')?.depth).toBe(0);
    expect(byText('hold fixed weights')?.depth).toBe(1);
    expect(byText('Otherwise')?.depth).toBe(0);
    expect(lines.find((l) => l.symbol === 'TLT')?.depth).toBe(2);
  });

  it('gives asset lines a symbol and their written share, without a number', () => {
    const assets = lines.filter((l) => l.kind === 'asset');
    expect(assets.map((a) => a.symbol)).toEqual(['TLT', 'GLD', 'VTI', 'QQQ', 'IWM']);
    expect(assets.every((a) => a.number === null)).toBe(true);
    expect(assets[0].share).toEqual({ kind: 'fixed', pct: 60 });
    expect(assets[2].share).toEqual({ kind: 'ranked', method: 'momentum' });
  });

  it('makes fixed weights editable tokens and leaves ranked weights without one', () => {
    const tlt = lines.find((l) => l.symbol === 'TLT');
    const vti = lines.find((l) => l.symbol === 'VTI');
    expect(partsText(tlt?.parts ?? [])).toBe('60%');
    expect(vti?.parts).toEqual([]);
  });

  it('collapses rules past the depth limit into one line with a count', () => {
    const deep = parse(`(strategy "Deep" :rebalance daily
      (if (> (rsi SPY 14) 70)
        (if (< (rsi QQQ 14) 30)
          (weight :method equal (asset TLT) (asset GLD))
          (else (asset SHY)))
        (else (asset SPY))))`);
    const collapsed = buildOutline(deep, { maxDepth: 2 });
    const fold = collapsed.find((l) => l.kind === 'collapsed');
    expect(fold).toBeDefined();
    expect(fold?.hiddenCount).toBeGreaterThan(0);
    expect(collapsed.some((l) => l.symbol === 'TLT')).toBe(false);

    const open = buildOutline(deep, { maxDepth: 2, expanded: new Set([fold?.blockId ?? '']) });
    expect(open.some((l) => l.kind === 'collapsed' && l.blockId === fold?.blockId)).toBe(false);
  });

  it('does not collapse a rule whose only children are assets', () => {
    const flat = parse(`(strategy "Flat" :rebalance quarterly
      (weight :method specified (asset VOO :weight 60) (asset BND :weight 40)))`);
    const out = buildOutline(flat, { maxDepth: 1 });
    expect(out.some((l) => l.kind === 'collapsed')).toBe(false);
    expect(out.filter((l) => l.kind === 'asset')).toHaveLength(2);
  });

  it('flags a weighting the engine cannot run', () => {
    const mc = parse(`(strategy "Cap" :rebalance monthly
      (weight :method market-cap (asset QQQ) (asset XLK)))`);
    const tok = tokenOf(buildOutline(mc), 'weight.method');
    expect(tok.bad).toBe(true);
    expect(tok.text).toBe('market cap');
  });

  it('writes a filter rule', () => {
    const f = parse(`(strategy "Top" :rebalance monthly
      (filter :by momentum :select (top 3) :lookback 126
        (weight :method equal (asset XLK) (asset XLE) (asset XLF) (asset XLV))))`);
    const line = buildOutline(f).find((l) => l.kind === 'filter');
    expect(line && lineText(line)).toBe('pick the top 3 by momentum over 6 months');
  });

  it('handles an empty strategy', () => {
    expect(
      buildOutline(parse('(strategy "Empty" :rebalance daily (weight :method equal))'))
    ).toEqual(expect.arrayContaining([expect.objectContaining({ kind: 'weight' })]));
  });
});

describe('metaParts', () => {
  it('reads the rebalance and the benchmark', () => {
    expect(partsText(metaParts({ timeframe: '1M', benchmark: 'SPY' }))).toBe(
      'Rebalance monthly and compare with SPY'
    );
  });

  it('says when there is no benchmark', () => {
    expect(partsText(metaParts({ timeframe: '3M', benchmark: '' }))).toBe(
      'Rebalance quarterly and compare with no benchmark'
    );
  });
});

describe('ruleNumbers', () => {
  it('skips the root and assets', () => {
    const tree = parse(RADAR);
    expect([...ruleNumbers(tree).values()]).toEqual([1, 2, 3, 4]);
  });
});

describe('childShare', () => {
  it('splits an equal weight across its children', () => {
    const tree = parse(
      '(strategy "E" :rebalance daily (weight :method equal (asset A) (asset B) (asset C) (asset D)))'
    );
    const asset = Object.values(tree.blocks).find((b) => b.type === 'asset');
    expect(childShare(tree, asset?.id ?? '')).toEqual({ kind: 'equal', pct: 25 });
  });

  it('returns none for the root', () => {
    const tree = parse(RADAR);
    expect(childShare(tree, tree.rootId)).toEqual({ kind: 'none' });
  });
});

describe('writtenScenarios', () => {
  it('lists one scenario per branch, with ranked weights left unknown', () => {
    const scenarios = writtenScenarios(parse(RADAR));
    expect(scenarios).toHaveLength(2);
    expect(scenarios[0].label).toBe('If rule 1 holds');
    expect(scenarios[0].holdings).toEqual([
      { symbol: 'TLT', pct: 60 },
      { symbol: 'GLD', pct: 40 },
    ]);
    expect(scenarios[0].rankedBy).toEqual([]);
    expect(scenarios[1].label).toBe("If rule 1 doesn't hold");
    expect(scenarios[1].holdings.map((h) => h.pct)).toEqual([null, null, null]);
    expect(scenarios[1].rankedBy).toEqual(['momentum']);
  });

  it('multiplies nested fixed and equal weights', () => {
    const tree = parse(`(strategy "Nest" :rebalance quarterly
      (weight :method specified
        (group "Stocks" :weight 60 (weight :method equal (asset VTI) (asset VXUS)))
        (asset BND :weight 40)))`);
    const [only] = writtenScenarios(tree);
    expect(only.label).toBe('Always');
    expect(only.holdings).toEqual([
      { symbol: 'BND', pct: 40 },
      { symbol: 'VTI', pct: 30 },
      { symbol: 'VXUS', pct: 30 },
    ]);
  });

  it('adds up a symbol held in two places', () => {
    const tree = parse(`(strategy "Dup" :rebalance daily
      (weight :method specified (asset SPY :weight 50) (group "More" :weight 50 (asset SPY))))`);
    expect(writtenScenarios(tree)[0].holdings).toEqual([{ symbol: 'SPY', pct: 100 }]);
  });
});

describe('longestLookback and strategySymbols', () => {
  it('finds the longest window across conditions and weights', () => {
    expect(longestLookback(parse(RADAR))).toBe(90);
  });

  it('separates held symbols from signal symbols', () => {
    expect(strategySymbols(parse(RADAR), 'SPY')).toEqual({
      held: ['GLD', 'IWM', 'QQQ', 'TLT', 'VTI'],
      signals: ['SPY'],
    });
  });
});

describe('applyTokenEdit', () => {
  const tree = parse(RADAR);
  const lines = buildOutline(tree);

  it('changes a condition threshold', () => {
    const edit = applyTokenEdit(tree, tokenOf(lines, 'cond.right.value'), '65');
    expect(edit.kind).toBe('condition');
    if (edit.kind === 'condition') {
      expect(edit.condition.right).toEqual(expect.objectContaining({ type: 'number', value: 65 }));
      expect(edit.condition.left).toEqual((tree.blocks[edit.blockId] as IfBlock).condition.left);
    }
  });

  it('changes the comparator only from its list', () => {
    const tok = tokenOf(lines, 'cond.comparator');
    expect(applyTokenEdit(tree, tok, 'lt').kind).toBe('condition');
    expect(applyTokenEdit(tree, tok, 'between').kind).toBe('invalid');
  });

  it('uppercases a signal symbol and rejects a bad one', () => {
    const tok = tokenOf(lines, 'cond.left.symbol');
    const ok = applyTokenEdit(tree, tok, ' qqq ');
    expect(
      ok.kind === 'condition' && ok.condition.left.type === 'indicator' && ok.condition.left.symbol
    ).toBe('QQQ');
    expect(applyTokenEdit(tree, tok, '1abc').kind).toBe('invalid');
  });

  it('switching to an indicator without a period drops the period', () => {
    const edit = applyTokenEdit(tree, tokenOf(lines, 'cond.left.indicator'), 'obv');
    expect(edit.kind).toBe('condition');
    if (edit.kind === 'condition' && edit.condition.left.type === 'indicator') {
      expect(edit.condition.left.indicator).toBe('obv');
      expect(edit.condition.left.period).toBeUndefined();
    }
  });

  it('changes a lookback, rejecting fractions and out-of-range values', () => {
    const tok = tokenOf(lines, 'weight.lookback');
    expect(applyTokenEdit(tree, tok, '120')).toEqual(
      expect.objectContaining({ kind: 'block', updates: { lookbackDays: 120 } })
    );
    expect(applyTokenEdit(tree, tok, '12.5').kind).toBe('invalid');
    expect(applyTokenEdit(tree, tok, '0').kind).toBe('invalid');
    expect(applyTokenEdit(tree, tok, '').kind).toBe('invalid');
  });

  it('switching to fixed weights seeds an even split', () => {
    const tok = tokenOf(lines, 'weight.method', 1);
    const edit = applyTokenEdit(tree, tok, 'specified');
    expect(edit.kind).toBe('block');
    if (edit.kind === 'block') {
      const updates = edit.updates as Partial<WeightBlock>;
      expect(Object.values(updates.allocations ?? {})).toEqual([33.33, 33.33, 33.33]);
      expect(updates.lookbackDays).toBeUndefined();
      expect(updates.top).toBeUndefined();
    }
  });

  it('refuses an unsupported weighting', () => {
    expect(applyTokenEdit(tree, tokenOf(lines, 'weight.method'), 'market_cap').kind).toBe(
      'invalid'
    );
  });

  it('edits a fixed asset weight through its parent', () => {
    const edit = applyTokenEdit(tree, tokenOf(lines, 'asset.weight'), '55');
    expect(edit.kind).toBe('allocation');
    if (edit.kind === 'allocation') {
      expect(tree.blocks[edit.weightId]?.type).toBe('weight');
      expect(edit.percent).toBe(55);
    }
    expect(applyTokenEdit(tree, tokenOf(lines, 'asset.weight'), '140').kind).toBe('invalid');
  });

  it('edits the strategy settings', () => {
    const meta = metaParts({ timeframe: '1M', benchmark: 'SPY' });
    const rebalance = meta.find(
      (p): p is OutlineToken => p.kind === 'token' && p.field === 'rebalance'
    );
    const bench = meta.find(
      (p): p is OutlineToken => p.kind === 'token' && p.field === 'benchmark'
    );
    if (!rebalance || !bench) throw new Error('missing tokens');
    expect(applyTokenEdit(tree, rebalance, '3M')).toEqual({ kind: 'timeframe', value: '3M' });
    expect(applyTokenEdit(tree, rebalance, 'hourly').kind).toBe('invalid');
    expect(applyTokenEdit(tree, bench, 'qqq')).toEqual({ kind: 'benchmark', value: 'QQQ' });
    expect(applyTokenEdit(tree, bench, '')).toEqual({ kind: 'benchmark', value: '' });
  });

  it('reports a block that no longer exists', () => {
    const tok = { ...tokenOf(lines, 'weight.lookback'), blockId: 'gone' };
    expect(applyTokenEdit(tree, tok, '30').kind).toBe('invalid');
  });
});

describe('allocationProblem and isSupportedMethod', () => {
  it('says when fixed weights do not add to 100', () => {
    const tree = parse(
      '(strategy "S" :rebalance daily (weight :method specified (asset A :weight 60) (asset B :weight 30)))'
    );
    const w = Object.values(tree.blocks).find((b) => b.type === 'weight');
    expect(allocationProblem(tree, w?.id ?? '')).toBe('These weights add up to 90%, not 100%.');
    const ok = parse(RADAR);
    const specified = Object.values(ok.blocks).find(
      (b) => b.type === 'weight' && b.method === 'specified'
    );
    expect(allocationProblem(ok, specified?.id ?? '')).toBeNull();
  });

  it('knows which methods run', () => {
    expect(isSupportedMethod('momentum')).toBe(true);
    expect(isSupportedMethod('market_cap')).toBe(false);
  });
});

const SECTORS = `(strategy "Sectors" :rebalance monthly
  (weight :method specified
    (group "Cyclical" :weight 70
      (filter :by momentum :select (top 3) :lookback 90
        (weight :method equal (asset XLK) (asset XLF) (asset XLI) (asset XLY) (asset XLC))))
    (group "Defensive" :weight 30 (asset XLV))))`;

describe('filters and groups in the outline', () => {
  const tree = parse(SECTORS);
  const lines = buildOutline(tree);

  it('writes the exact lookback when it is not a whole period', () => {
    const filter = lines.find((l) => l.kind === 'filter');
    expect(lineText(filter as OutlineLine)).toBe('pick the top 3 by momentum over 90 days');
    expect(longestLookback(tree)).toBe(90);
  });

  it('writes a whole period in months', () => {
    const t = parse(SECTORS.replace(':lookback 90', ':lookback 63'));
    const filter = buildOutline(t).find((l) => l.kind === 'filter');
    expect(lineText(filter as OutlineLine)).toBe('pick the top 3 by momentum over 3 months');
  });

  it('drops the exact lookback when a period is chosen', () => {
    const edit = applyTokenEdit(tree, tokenOf(lines, 'filter.period'), '6m');
    expect(edit.kind).toBe('filter');
    if (edit.kind === 'filter') {
      expect(edit.config.period).toBe('6m');
      expect(edit.config.lookbackDays).toBeUndefined();
    }
  });

  it('gives each pick its share of the picks, not of every candidate', () => {
    const asset = lines.find((l) => l.kind === 'asset' && l.symbol === 'XLK');
    expect(asset?.share).toEqual({ kind: 'picked', pct: 100 / 3 });
  });

  it('shows a group’s fixed weight as an editable token', () => {
    const group = lines.find((l) => l.kind === 'group');
    expect(lineText(group as OutlineLine)).toBe('the group Cyclical at 70%');
    const edit = applyTokenEdit(tree, tokenOf(lines, 'asset.weight'), '60');
    expect(edit.kind).toBe('allocation');
    if (edit.kind === 'allocation') expect(edit.percent).toBe(60);
  });

  it('shows a group’s equal share as plain text', () => {
    const t = parse(`(strategy "Eq" :rebalance monthly
      (weight :method equal (group "A" (asset SPY)) (group "B" (asset TLT))))`);
    const group = buildOutline(t).find((l) => l.kind === 'group');
    expect(group?.parts.map((p) => p.kind)).toEqual(['text', 'token', 'text']);
    expect(lineText(group as OutlineLine)).toBe('the group A at 50%');
  });
});

describe('momentum conditions', () => {
  it('reads a momentum comparison as momentum', () => {
    const tree = parse(`(strategy "D" :rebalance monthly
      (if (> (momentum SPY 252) 0) (asset SPY) (else (asset BND))))`);
    const rule = buildOutline(tree).find((l) => l.kind === 'if');
    expect(lineText(rule as OutlineLine)).toBe('If the 252-day momentum of SPY is above 0');
  });
});
