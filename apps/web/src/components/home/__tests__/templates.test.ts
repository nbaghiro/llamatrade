import { TemplateDifficulty } from '@llamatrade/core/proto/strategy_pb';
import { describe, expect, it } from 'vitest';

import {
  PREFERRED_TEMPLATE_ID,
  outlineOf,
  parseSexpr,
  rankTemplates,
  symbolsOf,
  templateMeta,
} from '../templates';

const CLASSIC = `(strategy "Classic 60/40"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Equities" :weight 60
      (weight :method equal
        (asset VTI)
        (asset VEA)
        (asset VWO)))
    (group "Bonds" :weight 40
      (weight :method equal
        (asset BND)
        (asset BNDX)))))`;

const RADAR = `(strategy "Recession Radar"
  :rebalance monthly :benchmark SPY
  (if (> (rsi SPY 14) 70)
      (weight :method specified (asset TLT :weight 60) (asset GLD :weight 40))
      (weight :method equal (asset XLK) (asset SMH))))`;

describe('parseSexpr', () => {
  it('reads nested lists and keeps quoted strings whole', () => {
    expect(parseSexpr('(a "b c" (d e))')).toEqual(['a', '"b c"', ['d', 'e']]);
  });

  it('returns null for empty input and survives unbalanced input', () => {
    expect(parseSexpr('')).toBeNull();
    expect(parseSexpr('(a (b')).toEqual(['a', ['b']]);
  });
});

describe('outlineOf', () => {
  it('reads rebalance, benchmark, symbols and nested weights', () => {
    const o = outlineOf(CLASSIC);
    expect(o.rebalance).toBe('monthly');
    expect(o.benchmark).toBe('SPY');
    expect(o.symbols).toEqual(['VTI', 'VEA', 'VWO', 'BND', 'BNDX']);
    expect(o.lines.slice(0, 4)).toEqual([
      { depth: 0, text: 'Set weights' },
      { depth: 1, text: 'Equities', weight: '60%' },
      { depth: 2, text: 'Equal weights' },
      { depth: 3, text: 'VTI', weight: undefined },
    ]);
  });

  it('writes a condition as If and Otherwise branches', () => {
    const lines = outlineOf(RADAR).lines.map((l) => [l.depth, l.text, l.weight]);
    expect(lines).toEqual([
      [0, 'If (> (rsi SPY 14) 70)', undefined],
      [1, 'Set weights', undefined],
      [2, 'TLT', '60%'],
      [2, 'GLD', '40%'],
      [0, 'Otherwise', undefined],
      [1, 'Equal weights', undefined],
      [2, 'XLK', undefined],
      [2, 'SMH', undefined],
    ]);
  });

  it('is empty for text that is not a strategy', () => {
    expect(outlineOf('not a strategy')).toEqual({
      rebalance: null,
      benchmark: null,
      symbols: [],
      lines: [],
    });
  });
});

describe('templateMeta', () => {
  it('names two holdings and counts more', () => {
    expect(
      templateMeta({ configSexpr: '(strategy "x" :rebalance quarterly (asset SPY) (asset AGG))' })
    ).toBe('Quarterly · SPY and AGG');
    expect(templateMeta({ configSexpr: CLASSIC })).toBe('Monthly · 5 symbols');
    expect(templateMeta({ configSexpr: '(strategy "x")' })).toBe('');
  });

  it('counts each symbol once', () => {
    expect(symbolsOf('(asset spy) (asset SPY) (asset QQQ)')).toEqual(['SPY', 'QQQ']);
  });
});

describe('rankTemplates', () => {
  it('puts the preferred template first, then beginner ones, keeping catalogue order', () => {
    const list = [
      { id: 'adv', difficulty: TemplateDifficulty.ADVANCED },
      { id: 'b1', difficulty: TemplateDifficulty.BEGINNER },
      { id: PREFERRED_TEMPLATE_ID, difficulty: TemplateDifficulty.BEGINNER },
      { id: 'mid', difficulty: TemplateDifficulty.INTERMEDIATE },
      { id: 'b2', difficulty: TemplateDifficulty.BEGINNER },
    ];
    expect(rankTemplates(list).map((t) => t.id)).toEqual([
      PREFERRED_TEMPLATE_ID,
      'b1',
      'b2',
      'adv',
      'mid',
    ]);
  });
});
