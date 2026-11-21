import { describe, expect, it } from 'vitest';

import { fillNote, type HistoryEntry } from '../fillNotes';
import type { SleeveFill } from '../history';

const at = new Date('2026-11-17T15:31:07Z');
const fill = (over: Partial<SleeveFill>): SleeveFill => ({
  id: 'f',
  at,
  sleeveId: 'rr',
  symbol: 'TLT',
  side: 'buy',
  qty: 42,
  price: 90.41,
  ...over,
});
const sale: HistoryEntry = {
  sleeveId: 'rr',
  side: 'sell',
  qty: 9,
  price: 247.86,
  realizedPnl: 299.34,
  at: new Date('2026-11-17T15:31:08Z'),
};

describe('fillNote', () => {
  it('calls a buy a new lot when a lot of its size opened at its time', () => {
    const lots = [{ symbol: 'TLT', qty: 42, avgPrice: 90.41, openedAt: at }];
    expect(fillNote(fill({}), lots, [])).toEqual({ kind: 'newLot' });
  });

  it('says nothing for a buy whose lot it cannot find', () => {
    const lots = [{ symbol: 'TLT', qty: 163, avgPrice: 93, openedAt: new Date('2026-06-02') }];
    expect(fillNote(fill({}), lots, [])).toEqual({ kind: 'none' });
  });

  it('shows the realized gain the ledger booked for a sale', () => {
    const f = fill({ side: 'sell', symbol: 'GLD', qty: 9 });
    expect(fillNote(f, [], [sale])).toEqual({ kind: 'realized', amount: 299.34 });
  });

  it('ignores another sleeve, another size or another time', () => {
    const f = fill({ side: 'sell', symbol: 'GLD', qty: 9 });
    expect(fillNote(f, [], [{ ...sale, sleeveId: 'aw' }])).toEqual({ kind: 'none' });
    expect(fillNote(f, [], [{ ...sale, qty: 10 }])).toEqual({ kind: 'none' });
    expect(fillNote(f, [], [{ ...sale, at: new Date('2026-11-17T17:00:00Z') }])).toEqual({
      kind: 'none',
    });
    expect(fillNote(f, [], [{ ...sale, realizedPnl: null }])).toEqual({ kind: 'none' });
  });

  it('matches on the fill price when the ledger sends no time', () => {
    const f = fill({ side: 'sell', symbol: 'GLD', qty: 9, price: 247.86 });
    expect(fillNote(f, [], [{ ...sale, at: null }])).toEqual({ kind: 'realized', amount: 299.34 });
    expect(fillNote(f, [], [{ ...sale, at: null, price: 250 }])).toEqual({ kind: 'none' });
  });
});
