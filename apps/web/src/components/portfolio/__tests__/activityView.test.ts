import { describe, expect, it } from 'vitest';

import {
  monthBounds,
  monthKey,
  monthsWithEntries,
  OTHER_LANE,
  statementRows,
  totals,
  UNALLOCATED_LANE,
  type ActivityInput,
} from '../activityView';
import type { SleeveFill } from '../history';

const at = new Date('2026-11-17T15:31:00Z');
const row = (over: Partial<ActivityInput>): ActivityInput => ({
  id: 'r',
  kind: 'buy',
  label: 'Buy TLT',
  sublabel: '',
  symbol: 'TLT',
  qty: 42,
  price: 90.41,
  amount: 3797.22,
  at,
  ...over,
});
const fills: SleeveFill[] = [
  { id: 'f', at, sleeveId: 'rr', symbol: 'TLT', side: 'buy', qty: 42, price: 90.41 },
];
const sleeves = [{ sleeveId: 'rr', name: 'Recession Radar' }];

describe('statementRows', () => {
  it('puts each row on the lane it belongs to', () => {
    const out = statementRows(
      [
        row({ id: 'buy' }),
        row({ id: 'sell', kind: 'sell', qty: 9, symbol: 'GLD' }),
        row({ id: 'alloc', kind: 'allocation', sublabel: 'Recession Radar', amount: 3000 }),
        row({ id: 'manual', kind: 'allocation', sublabel: 'Manual', amount: 5000 }),
        row({ id: 'dep', kind: 'deposit', amount: 100_000 }),
        row({ id: 'div', kind: 'dividend', symbol: 'LQD', amount: 48 }),
      ],
      fills,
      sleeves
    );
    const by = Object.fromEntries(out.map((r) => [r.row.id, r]));
    expect(by.buy).toMatchObject({
      lane: 'rr',
      tag: 'BUY',
      entry: '42 TLT at $90.41',
      paidOut: 3797.22,
    });
    expect(by.sell.lane).toBe(OTHER_LANE);
    expect(by.alloc).toMatchObject({ lane: 'rr', tag: 'IN', entry: 'Allocated from unallocated' });
    expect(by.manual).toMatchObject({
      lane: OTHER_LANE,
      entry: 'Allocated from unallocated to Manual',
    });
    expect(by.dep).toMatchObject({ lane: UNALLOCATED_LANE, paidIn: 100_000 });
    expect(by.div).toMatchObject({ tag: 'DIV', entry: 'Dividend from LQD', paidIn: 48 });
  });
});

describe('months', () => {
  it('lists months with entries newest first and bounds them', () => {
    const rows = [
      { at: new Date(2026, 10, 3) },
      { at: new Date(2026, 9, 30) },
      { at: new Date(2026, 10, 1) },
    ];
    expect(monthsWithEntries(rows)).toEqual(['2026-11', '2026-10']);
    expect(monthKey(new Date(2026, 0, 31))).toBe('2026-01');
    const b = monthBounds('2026-02');
    expect(b.start).toEqual(new Date(2026, 1, 1));
    expect(b.end.getDate()).toBe(28);
  });

  it('sums the in and out columns', () => {
    expect(
      totals([
        { paidIn: 1, paidOut: 0 },
        { paidIn: 2, paidOut: 3 },
      ])
    ).toEqual({ paidIn: 3, paidOut: 3 });
  });
});
