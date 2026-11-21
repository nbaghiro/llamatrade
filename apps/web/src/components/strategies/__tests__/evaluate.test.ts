import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { Block, IfBlock, StrategyTree } from '@llamatrade/core/strategy/types';
import { describe, expect, it } from 'vitest';

import { holdingsWhen } from '../../../lib/outline';
import {
  conditionHistory,
  countAtRebalances,
  isReadable,
  latestReading,
  readableSymbols,
  todaysChoices,
  type DailySeries,
} from '../rules/evaluate';
import { lastChange } from '../rules/valueHistory';

const tree = (code: string): StrategyTree => {
  const p = fromDSLString(code);
  if (!p) throw new Error('parse failed');
  return p.tree;
};
const firstIf = (t: StrategyTree) =>
  Object.values(t.blocks).find((b): b is IfBlock => b.type === 'if') as IfBlock;

const days = (n: number) =>
  Array.from({ length: n }, (_, i) => new Date(Date.UTC(2026, 0, 1) + i * 86_400_000));

const PRICE_RULE = `(strategy "P" :rebalance daily :benchmark SPY
  (if (> (price SPY) 100) (asset SPY) (else (asset BIL))))`;

describe('evaluate', () => {
  it('reads a price against a threshold day by day', () => {
    const t = tree(PRICE_RULE);
    const bars = new Map<string, DailySeries>([
      ['SPY', { dates: days(4), closes: [99, 101, 102, 98] }],
    ]);
    const h = conditionHistory(firstIf(t).condition, bars);
    expect(h?.held).toEqual([false, true, true, false]);
    const r = h ? latestReading(h) : null;
    expect(r).toMatchObject({ value: 98, against: 100, holds: false });
  });

  it('compares two series on shared days', () => {
    const t = tree(`(strategy "S" :rebalance daily :benchmark SPY
      (if (> (price SPY) (sma SPY 2)) (asset SPY) (else (asset BIL))))`);
    const bars = new Map<string, DailySeries>([
      ['SPY', { dates: days(4), closes: [10, 12, 11, 13] }],
    ]);
    const h = conditionHistory(firstIf(t).condition, bars);
    expect(h?.right.slice(1)).toEqual([11, 11.5, 12]);
    expect(h?.held).toEqual([false, true, false, true]);
  });

  it('counts rebalances held and finds the last switch', () => {
    const t = tree(PRICE_RULE);
    const bars = new Map<string, DailySeries>([
      ['SPY', { dates: days(6), closes: [99, 101, 102, 98, 97, 103] }],
    ]);
    const h = conditionHistory(firstIf(t).condition, bars);
    if (!h) throw new Error('no history');
    const c = countAtRebalances(h, [0, 2, 4, 5]);
    expect(c.held).toBe(2);
    expect(c.total).toBe(4);
    expect(c.lastSwitch?.value).toBe(103);
    expect(countAtRebalances(h, [0, 2, 4, 5], days(6)[3]).total).toBe(2);
  });

  it('leaves conditions it cannot read as unknown', () => {
    const t = tree(`(strategy "M" :rebalance monthly :benchmark SPY
      (if (> (return SPY 126) 0) (asset SPY) (else (asset BND))))`);
    expect(isReadable(firstIf(t).condition)).toBe(false);
    expect(readableSymbols(t)).toEqual([]);
    expect(todaysChoices(t, new Map())).toBeNull();
  });

  it('turns today’s side into holdings', () => {
    const t = tree(`(strategy "R" :rebalance daily :benchmark SPY
      (if (> (rsi SPY 14) 70)
        (weight :method specified (asset TLT :weight 60) (asset GLD :weight 40))
        (else (asset VTI))))`);
    const ifb = firstIf(t);
    const choices = todaysChoices(
      t,
      new Map([[ifb.id, { value: 73.8, against: 70, holds: true, asOf: new Date() }]])
    );
    expect(choices).not.toBeNull();
    const h = holdingsWhen(t, choices ?? new Map());
    expect(h.holdings).toEqual([
      { symbol: 'TLT', pct: 60 },
      { symbol: 'GLD', pct: 40 },
    ]);
  });
});

describe('lastChange', () => {
  const v = (n: number, threshold: number) => ({
    version: n,
    tree: tree(`(strategy "R" :rebalance daily :benchmark SPY
      (if (> (rsi SPY 14) ${threshold}) (asset TLT) (else (asset VTI))))`),
  });
  const threshold = (b: Block) =>
    b.type === 'if' && b.condition.right.type === 'number' ? String(b.condition.right.value) : null;

  it('finds the version that set the value and what it was', () => {
    const versions = [v(3, 70), v(2, 65), v(1, 65)];
    const id = firstIf(versions[0].tree).id;
    expect(lastChange(versions, id, threshold)).toEqual({ version: 3, was: '65' });
  });

  it('walks past versions that kept the value', () => {
    const versions = [v(3, 70), v(2, 70), v(1, 60)];
    const id = firstIf(versions[0].tree).id;
    expect(lastChange(versions, id, threshold)).toEqual({ version: 2, was: '60' });
  });

  it('is null when the value never changed or there is one version', () => {
    const versions = [v(2, 70), v(1, 70)];
    const id = firstIf(versions[0].tree).id;
    expect(lastChange(versions, id, threshold)).toBeNull();
    expect(lastChange([v(1, 70)], id, threshold)).toBeNull();
  });
});
