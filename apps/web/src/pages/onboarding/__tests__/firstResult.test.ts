import { describe, expect, it } from 'vitest';

import type { TradeInput } from '../../../lib/backtestView';
import { heldPeriods, heldSets, switchesOf, symbolsLabel, worstDrop } from '../firstResult';

const d = (s: string) => new Date(`${s}T00:00:00Z`);
const trade = (symbol: string, entry: string, exit: string | null): TradeInput => ({
  symbol,
  side: 'BUY',
  quantity: 1,
  entryPrice: 1,
  exitPrice: 1,
  entryTime: d(entry),
  exitTime: exit ? d(exit) : null,
  pnl: 0,
  entryReason: '',
  exitReason: '',
});

describe('heldPeriods', () => {
  const trades = [
    trade('SPY', '2025-01-02', '2025-03-24'),
    trade('TLT', '2025-03-24', '2025-08-11'),
    trade('GLD', '2025-03-24', '2025-08-11'),
    trade('SPY', '2025-08-11', '2025-09-01'),
    trade('SPY', '2025-09-01', null),
  ];
  const periods = heldPeriods(trades, d('2025-12-31'));

  it('merges back-to-back trades in the same symbols into one period', () => {
    expect(
      periods.map((p) => [
        p.key,
        p.from.toISOString().slice(0, 10),
        p.to.toISOString().slice(0, 10),
      ])
    ).toEqual([
      ['SPY', '2025-01-02', '2025-03-24'],
      ['GLD · TLT', '2025-03-24', '2025-08-11'],
      ['SPY', '2025-08-11', '2025-12-31'],
    ]);
  });

  it('finds the switches after the first purchase', () => {
    expect(switchesOf(periods).map((p) => p.key)).toEqual(['GLD · TLT', 'SPY']);
  });

  it('ranks the sets by days held', () => {
    expect(heldSets(periods).map((s) => s.key)).toEqual(['SPY', 'GLD · TLT']);
  });

  it('leaves days in cash out', () => {
    const gap = heldPeriods(
      [trade('SPY', '2025-01-02', '2025-02-01'), trade('SPY', '2025-03-01', '2025-04-01')],
      d('2025-05-01')
    );
    expect(gap).toHaveLength(2);
  });

  it('is empty without trades', () => {
    expect(heldPeriods([], d('2025-05-01'))).toEqual([]);
  });
});

describe('worstDrop', () => {
  it('runs from the last peak to the deepest low', () => {
    const dates = ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04', '2025-01-05'].map(d);
    const drop = worstDrop(dates, [100, 110, 99, 88, 120]);
    expect(drop?.from).toEqual(dates[1]);
    expect(drop?.to).toEqual(dates[3]);
    expect(drop?.depth).toBeCloseTo(-0.2);
  });

  it('is null for a curve that never fell', () => {
    expect(worstDrop([d('2025-01-01'), d('2025-01-02')], [100, 101])).toBeNull();
  });
});

describe('symbolsLabel', () => {
  it.each([
    [['SPY'], 'SPY'],
    [['TLT', 'GLD'], 'TLT and GLD'],
    [['A', 'B', 'C'], 'A, B and C'],
    [['A', 'B', 'C', 'D', 'E'], 'A, B, C and 2 more'],
  ])('labels %j', (symbols, out) => {
    expect(symbolsLabel(symbols)).toBe(out);
  });
});
