import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { StrategyTree } from '@llamatrade/core/strategy/types';
import { describe, expect, it } from 'vitest';

import { lineText } from '../outline';
import {
  diffCode,
  diffPartsText,
  diffStrategies,
  fieldLabel,
  hasChanges,
  matchBlocks,
  suggestNote,
  type DiffToken,
  type StrategySide,
} from '../strategyDiff';

const parse = (dsl: string): StrategyTree => {
  const parsed = fromDSLString(dsl);
  if (!parsed) throw new Error(`failed to parse: ${dsl}`);
  return parsed.tree;
};

const radar = ({
  threshold = 70,
  lookback = 90,
  gld = true,
  extra = '',
} = {}) => `(strategy "Recession Radar"
  :rebalance monthly :benchmark SPY
  (if (> (rsi SPY 14) ${threshold})
      (weight :method specified
        (asset TLT :weight ${gld ? 60 : 100})
        ${gld ? '(asset GLD :weight 40)' : ''})
      (else
        (weight :method momentum
          :lookback ${lookback} :top 2
          (asset VTI) (asset QQQ)
          (asset IWM)${extra}))))`;

const side = (
  dsl: string,
  meta = { timeframe: '1M', benchmark: 'SPY' },
  name?: string
): StrategySide => ({
  tree: parse(dsl),
  meta,
  name,
});

describe('matchBlocks', () => {
  it('pairs every block of two parses of the same text', () => {
    const a = parse(radar());
    const b = parse(radar());
    const match = matchBlocks(a, b);
    expect(match.size).toBe(Object.keys(b.blocks).length);
    for (const [afterId, beforeId] of match) {
      expect(b.blocks[afterId].type).toBe(a.blocks[beforeId].type);
    }
  });

  it('matches assets by symbol even when one is inserted before them', () => {
    const a = parse(
      '(strategy "S" :rebalance daily (weight :method equal (asset VTI) (asset BND)))'
    );
    const b = parse(
      '(strategy "S" :rebalance daily (weight :method equal (asset GLD) (asset VTI) (asset BND)))'
    );
    const match = matchBlocks(a, b);
    const gld = Object.values(b.blocks).find((x) => x.type === 'asset' && x.symbol === 'GLD');
    const vti = Object.values(b.blocks).find((x) => x.type === 'asset' && x.symbol === 'VTI');
    expect(match.has(gld?.id ?? '')).toBe(false);
    const vtiBefore = a.blocks[match.get(vti?.id ?? '') ?? ''];
    expect(vtiBefore?.type === 'asset' && vtiBefore.symbol).toBe('VTI');
  });
});

describe('diffStrategies', () => {
  it('reports nothing for identical versions', () => {
    const diff = diffStrategies(side(radar()), side(radar()));
    expect(diff.changes).toEqual([]);
    expect(hasChanges(diff)).toBe(false);
    expect(diff.lines.every((l) => l.status === 'same')).toBe(true);
  });

  it('strikes the old value of a changed lookback and says it in words', () => {
    const diff = diffStrategies(side(radar()), side(radar({ lookback: 120 })));
    expect(diff.changes).toEqual(['Rule 4: lookback from 90 days to 120 days']);
    const line = diff.lines.find((l) => l.number === 4);
    expect(line?.status).toBe('changed');
    const tok = line?.parts.find(
      (p): p is DiffToken => p.kind === 'token' && p.field === 'weight.lookback'
    );
    expect(tok?.was).toBe('90');
    expect(tok?.text).toBe('120');
  });

  it('describes a changed threshold', () => {
    const diff = diffStrategies(side(radar({ threshold: 75 })), side(radar({ threshold: 70 })));
    expect(diff.changes).toEqual(['Rule 1: threshold from 75 to 70']);
  });

  it('places a removed holding where it was and names its rule', () => {
    const diff = diffStrategies(side(radar()), side(radar({ gld: false })));
    expect(diff.changes).toContain('Removed GLD from rule 2');
    expect(diff.changes).toContain('TLT in rule 2: weight from 60% to 100%');
    const idx = diff.lines.findIndex((l) => l.status === 'removed');
    expect(diff.lines[idx].symbol).toBe('GLD');
    expect(diff.lines[idx - 1].symbol).toBe('TLT');
  });

  it('reports an added holding', () => {
    const diff = diffStrategies(side(radar()), side(radar({ extra: ' (asset DIA)' })));
    expect(diff.changes).toEqual(['Added DIA to rule 4']);
    expect(diff.lines.find((l) => l.symbol === 'DIA')?.status).toBe('added');
  });

  it('reports a whole added rule once, not each line inside it', () => {
    const before = side('(strategy "S" :rebalance daily (weight :method equal (asset SPY)))');
    const after = side(`(strategy "S" :rebalance daily
      (weight :method equal (asset SPY)
        (weight :method specified (asset TLT :weight 50) (asset GLD :weight 50))))`);
    const diff = diffStrategies(before, after);
    expect(diff.changes).toEqual(['Added rule 2: hold fixed weights']);
    expect(diff.lines.filter((l) => l.status === 'added')).toHaveLength(3);
  });

  it('reports a whole removed rule once', () => {
    const before = side(`(strategy "S" :rebalance daily
      (weight :method equal (asset SPY)
        (weight :method specified (asset TLT :weight 50) (asset GLD :weight 50))))`);
    const after = side('(strategy "S" :rebalance daily (weight :method equal (asset SPY)))');
    const diff = diffStrategies(before, after);
    expect(diff.changes).toEqual(['Removed rule 2: hold fixed weights']);
    expect(diff.lines.filter((l) => l.status === 'removed').map((l) => l.symbol ?? l.kind)).toEqual(
      ['weight', 'TLT', 'GLD']
    );
    const keys = diff.lines.map((l) => l.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('keeps the old sentence when a rule changes shape', () => {
    const before = side(
      '(strategy "S" :rebalance daily (weight :method equal (asset A) (asset B)))'
    );
    const after = side(
      '(strategy "S" :rebalance daily (weight :method momentum :lookback 60 (asset A) (asset B)))'
    );
    const diff = diffStrategies(before, after);
    const line = diff.lines.find((l) => l.kind === 'weight');
    expect(line?.status).toBe('changed');
    expect(line?.wasParts && diffPartsText(line.wasParts)).toBe('hold at equal weight');
    expect(diff.changes[0]).toBe(
      'Rule 1 now reads “hold weighted by momentum over 60 days”, was “hold at equal weight”'
    );
  });

  it('compares the strategy settings and the name', () => {
    const diff = diffStrategies(
      side(radar(), { timeframe: '1M', benchmark: 'SPY' }, 'Radar'),
      side(radar(), { timeframe: '3M', benchmark: 'QQQ' }, 'Recession Radar')
    );
    expect(diff.name).toEqual({ from: 'Radar', to: 'Recession Radar' });
    expect(diff.changes).toEqual([
      'Renamed from “Radar” to “Recession Radar”',
      'Rebalance from monthly to quarterly',
      'Benchmark from SPY to QQQ',
    ]);
    const rebalance = diff.meta.find(
      (p): p is DiffToken => p.kind === 'token' && p.field === 'rebalance'
    );
    expect(rebalance?.was).toBe('monthly');
  });

  it('handles an empty older version', () => {
    const before = side('(strategy "S" :rebalance daily (weight :method equal))');
    const after = side('(strategy "S" :rebalance daily (weight :method equal (asset SPY)))');
    expect(diffStrategies(before, after).changes).toEqual(['Added SPY to rule 1']);
  });

  it('keeps the reading order of the newer version', () => {
    const diff = diffStrategies(side(radar()), side(radar({ lookback: 120 })));
    expect(
      diff.lines.map((l) => (l.kind === 'asset' ? l.symbol : lineText({ ...l, parts: l.parts })))
    ).toEqual([
      'If the 14-day RSI of SPY is above 70',
      'hold fixed weights',
      'TLT',
      'GLD',
      'Otherwise',
      'hold the top 2, weighted by momentum over 120 days',
      'VTI',
      'QQQ',
      'IWM',
    ]);
  });
});

describe('suggestNote and fieldLabel', () => {
  it('uses the only change as the note', () => {
    const diff = diffStrategies(side(radar()), side(radar({ lookback: 120 })));
    expect(suggestNote(diff)).toBe('Rule 4: lookback from 90 days to 120 days');
  });

  it('counts further changes', () => {
    const diff = diffStrategies(side(radar()), side(radar({ lookback: 120, threshold: 65 })));
    expect(suggestNote(diff)).toBe('Rule 1: threshold from 70 to 65, and 1 more change');
  });

  it('is empty with no changes', () => {
    expect(suggestNote(diffStrategies(side(radar()), side(radar())))).toBe('');
  });

  it('labels condition fields by side', () => {
    expect(fieldLabel('cond.right.value')).toBe('threshold');
    expect(fieldLabel('cond.left.period')).toBe('period');
    expect(fieldLabel('cond.comparator')).toBe('comparison');
    expect(fieldLabel('weight.top')).toBe('number held');
  });
});

describe('diffCode', () => {
  it('marks unchanged, deleted and added lines with their numbers', () => {
    expect(diffCode('a\nb\nc', 'a\nx\nc')).toEqual([
      { kind: 'same', text: 'a', oldLine: 1, newLine: 1 },
      { kind: 'del', text: 'b', oldLine: 2 },
      { kind: 'add', text: 'x', newLine: 2 },
      { kind: 'same', text: 'c', oldLine: 3, newLine: 3 },
    ]);
  });

  it('handles empty sides', () => {
    expect(diffCode('', 'a')).toEqual([{ kind: 'add', text: 'a', newLine: 1 }]);
    expect(diffCode('a', '')).toEqual([{ kind: 'del', text: 'a', oldLine: 1 }]);
    expect(diffCode('', '')).toEqual([]);
  });

  it('is all same for identical text', () => {
    expect(diffCode('x\ny', 'x\ny').every((l) => l.kind === 'same')).toBe(true);
  });
});
