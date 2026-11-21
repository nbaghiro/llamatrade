import { describe, expect, it } from 'vitest';

import { groupRebalances, tradesToOrders, type TradeInput } from '../../../lib/backtestView';
import {
  changesLine,
  monthDetailTitle,
  monthGroups,
  periodReturn,
  reasonsOf,
  shareChanges,
  sliceYear,
  switchDays,
  yearCounts,
  yearMonths,
} from '../yearView';

const d = (iso: string) => new Date(`${iso}T00:00:00Z`);

const trade = (
  symbol: string,
  entry: string,
  exit: string | null,
  quantity: number,
  reason = ''
): TradeInput => ({
  symbol,
  side: 'BUY',
  quantity,
  entryPrice: 100,
  exitPrice: exit ? 110 : 0,
  entryTime: d(entry),
  exitTime: exit ? d(exit) : null,
  pnl: exit ? quantity * 10 : 0,
  entryReason: reason,
  exitReason: '',
});

// TLT held Jan 3 to Mar 1, then VTI from Mar 1: Mar 1 switches. Feb 1 resizes TLT.
const trades: TradeInput[] = [
  trade('TLT', '2022-01-03', '2022-03-01', 10, 'RSI above 70'),
  trade('TLT', '2022-02-01', '2022-03-01', 2, 'Resize'),
  trade('VTI', '2022-03-01', null, 5, 'Back to momentum'),
];

describe('yearView', () => {
  it('lists twelve months of a year', () => {
    expect(yearMonths('2022')).toHaveLength(12);
    expect(yearMonths('2022')[11]).toBe('2022-12');
  });

  it('measures a period from the last close before it', () => {
    const dates = [d('2021-12-31'), d('2022-01-03'), d('2022-12-30'), d('2023-01-03')];
    expect(periodReturn(dates, [100, 101, 110, 120], d('2022-01-01'), d('2022-12-31'))).toBeCloseTo(
      0.1
    );
    expect(
      periodReturn(dates.slice(1), [101, 110, 120], d('2022-01-01'), d('2022-12-31'))
    ).toBeCloseTo(110 / 101 - 1);
    expect(
      periodReturn(dates, [100, null, null, 120], d('2022-01-01'), d('2022-12-31'))
    ).toBeNull();
    expect(periodReturn([], [], d('2022-01-01'), d('2022-12-31'))).toBeNull();
  });

  it('nets shares per symbol, sold first', () => {
    const orders = tradesToOrders(trades).filter((o) => o.date === '2022-03-01');
    expect(shareChanges(orders)).toEqual([
      { symbol: 'TLT', shares: -12 },
      { symbol: 'VTI', shares: 5 },
    ]);
    expect(changesLine(shareChanges(orders))).toBe('Sell 12 TLT · buy 5 VTI');
    expect(changesLine([], 3)).toBe('');
    expect(
      changesLine(
        ['A', 'B', 'C', 'D'].map((symbol) => ({ symbol, shares: 1 })),
        2
      )
    ).toBe('Buy 1 A · buy 1 B · 2 more');
  });

  it('groups a year by month with switch or resize', () => {
    const switches = switchDays(trades);
    expect([...switches].sort()).toEqual(['2022-01-03', '2022-03-01']);
    const groups = monthGroups(groupRebalances(tradesToOrders(trades)), '2022', switches);
    expect(groups.map((g) => g.kind).slice(0, 4)).toEqual(['switch', 'resize', 'switch', null]);
    expect(groups[2].orders).toBe(3);
    expect(groups[2].realised).toBe(120);
    expect(monthDetailTitle(groups[1])).toBe('Feb 1, 2022');
    expect(monthDetailTitle(groups[3])).toBe('Apr 2022');
    expect(reasonsOf(groups[2].rebalances)).toEqual(['RSI above 70', 'Resize', 'Back to momentum']);
  });

  it('says how the year traded', () => {
    expect(yearCounts(3, 9, 48)).toBe('Three switches and nine resizes, 48 orders.');
    expect(yearCounts(0, 1, 2)).toBe('One resize, 2 orders.');
    expect(yearCounts(12, 0, 30)).toBe('12 switches, 30 orders.');
    expect(yearCounts(0, 0, 0)).toBe('No orders this year.');
  });

  it('cuts a curve to one year', () => {
    const full = {
      dates: [d('2021-12-31'), d('2022-01-03'), d('2022-06-01')],
      values: [1, 2, 3],
      bench: [4, 5, 6],
    };
    expect(sliceYear(full, '2022')).toEqual({
      dates: full.dates.slice(1),
      values: [2, 3],
      bench: [5, 6],
    });
    expect(sliceYear(full, '2021')).toBeNull();
  });
});
