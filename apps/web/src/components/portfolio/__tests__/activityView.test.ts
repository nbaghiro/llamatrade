import { describe, expect, it } from 'vitest';

import {
  accountsByRow,
  depositEntry,
  monthBounds,
  monthKey,
  monthsWithEntries,
  OTHER_LANE,
  rowAccount,
  statementRows,
  totals,
  UNALLOCATED_LANE,
  withdrawalEntry,
  type ActivityInput,
} from '../activityView';
import { fillsByLedgerId, lastMonth, ledgerFillId, type SleeveFill } from '../history';

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

  it('puts a row on the sleeve the ledger booked it to, ahead of the matches', () => {
    const two = [...sleeves, { sleeveId: 'aw', name: 'All-Weather Portfolio' }];
    const out = statementRows(
      [
        row({ id: 'buy', sleeveId: 'aw' }),
        row({ id: 'alloc', kind: 'allocation', sublabel: 'Manual', sleeveId: 'aw' }),
        row({ id: 'div', kind: 'dividend', symbol: 'LQD', sleeveId: 'rr' }),
        row({ id: 'fee', kind: 'fee', label: 'Fee', sleeveId: 'aw' }),
        row({ id: 'gone', kind: 'dividend', symbol: 'LQD', sleeveId: 'closed' }),
        row({ id: 'dep', kind: 'deposit', sleeveId: 'unalloc', account: 'live' }),
      ],
      fills,
      two
    );
    const by = Object.fromEntries(out.map((r) => [r.row.id, r]));
    expect(by.buy.lane).toBe('aw');
    expect(by.alloc).toMatchObject({ lane: 'aw', entry: 'Allocated from unallocated' });
    expect(by.div.lane).toBe('rr');
    expect(by.fee.lane).toBe('aw');
    expect(by.gone.lane).toBe(OTHER_LANE);
    expect(by.dep).toMatchObject({
      lane: UNALLOCATED_LANE,
      entry: 'Live deposit, to unallocated',
    });
  });

  it('names the account on a withdrawal the ledger booked', () => {
    const out = statementRows(
      [
        row({ id: 'wl', kind: 'withdrawal', account: 'live' }),
        row({ id: 'wu', kind: 'withdrawal' }),
      ],
      fills,
      sleeves
    );
    expect(out.map((r) => [r.lane, r.tag, r.entry])).toEqual([
      [UNALLOCATED_LANE, 'OUT', 'Live withdrawal, from unallocated'],
      [UNALLOCATED_LANE, 'OUT', 'Withdrawn from unallocated'],
    ]);
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

describe('ledger fill ids', () => {
  it('matches the portfolio service id for a client order id', async () => {
    expect(await ledgerFillId('lt-demo-aw-017')).toBe('5470935e-8da9-a0c3-ff94-c552e2f4a0f1');
  });

  it('ties a fill row to its order exactly, ahead of the time match', async () => {
    const byId = await fillsByLedgerId([
      { ...fills[0], sleeveId: 'aw', clientOrderId: 'lt-demo-aw-017' },
      { ...fills[0], id: 'no-coid' },
    ]);
    expect([...byId.keys()]).toEqual(['5470935e-8da9-a0c3-ff94-c552e2f4a0f1']);
    const out = statementRows(
      [row({ id: '5470935e-8da9-a0c3-ff94-c552e2f4a0f1' })],
      fills,
      [...sleeves, { sleeveId: 'aw', name: 'All-Weather Portfolio' }],
      byId
    );
    expect(out[0].lane).toBe('aw');
  });
});

describe('deposit accounts', () => {
  const t = (min: number) => new Date(at.getTime() + min * 60_000);
  const both = [
    { sleeveId: 'rr', name: 'Recession Radar', live: false },
    { sleeveId: 'aw', name: 'All-Weather Portfolio', live: true },
  ];

  it('takes the account of the allocation that follows a deposit of the same amount', () => {
    const rows = [
      row({ id: 'd1', kind: 'deposit', amount: 45140, at: t(0) }),
      row({
        id: 'a1',
        kind: 'allocation',
        sublabel: 'All-Weather Portfolio',
        amount: 45140,
        at: t(3),
      }),
      row({ id: 'd2', kind: 'deposit', amount: 28385, at: t(100) }),
      row({ id: 'a2', kind: 'allocation', sublabel: 'Recession Radar', amount: 28385, at: t(103) }),
      row({ id: 'd3', kind: 'deposit', amount: 5000, at: t(200) }),
    ];
    const out = accountsByRow(rows, both);
    expect(out.get('d1')).toBe('live');
    expect(out.get('d2')).toBe('paper');
    expect(out.has('d3')).toBe(false);
  });

  it('leaves a deposit unnamed when the allocation is late, different or unknown', () => {
    const rows = [
      row({ id: 'late', kind: 'deposit', amount: 100, at: t(0) }),
      row({ id: 'x', kind: 'allocation', sublabel: 'Recession Radar', amount: 100, at: t(45) }),
      row({ id: 'diff', kind: 'deposit', amount: 200, at: t(60) }),
      row({ id: 'y', kind: 'allocation', sublabel: 'Recession Radar', amount: 150, at: t(61) }),
      row({ id: 'who', kind: 'deposit', amount: 300, at: t(120) }),
      row({ id: 'z', kind: 'allocation', sublabel: 'Manual', amount: 300, at: t(121) }),
    ];
    expect(accountsByRow(rows, both).size).toBe(0);
  });

  it('pairs each allocation with one deposit only', () => {
    const rows = [
      row({ id: 'd1', kind: 'deposit', amount: 100, at: t(0) }),
      row({ id: 'd2', kind: 'deposit', amount: 100, at: t(1) }),
      row({ id: 'a', kind: 'allocation', sublabel: 'Recession Radar', amount: 100, at: t(2) }),
    ];
    const out = accountsByRow(rows, both);
    expect(out.get('d1')).toBe('paper');
    expect(out.has('d2')).toBe(false);
  });

  it('labels deposits by account and never calls an unknown one paper', () => {
    expect(depositEntry('live')).toBe('Live deposit, to unallocated');
    expect(depositEntry('paper')).toBe('Paper funds, to unallocated');
    expect(depositEntry(undefined)).toBe('Deposit to unallocated');
    expect(withdrawalEntry('paper')).toBe('Paper withdrawal, from unallocated');
  });

  it('takes the account the ledger names before pairing deposits', () => {
    const rows = [
      row({ id: 'd1', kind: 'deposit', amount: 100, at: t(0), account: 'live' }),
      row({ id: 'a1', kind: 'allocation', sublabel: 'Recession Radar', amount: 100, at: t(2) }),
      row({ id: 'd2', kind: 'deposit', amount: 100, at: t(5) }),
      row({ id: 'a2', kind: 'allocation', sublabel: 'Recession Radar', amount: 100, at: t(6) }),
      row({ id: 'w', kind: 'withdrawal', amount: 50, at: t(9), account: 'paper' }),
      row({ id: 'u', kind: 'withdrawal', amount: 50, at: t(9), account: null }),
    ];
    const out = accountsByRow(rows, both);
    expect(out.get('d1')).toBe('live');
    expect(out.get('d2')).toBe('paper');
    expect(out.get('w')).toBe('paper');
    expect(out.has('u')).toBe(false);
  });

  it('prefers the booked account to the sleeve lane', () => {
    const rows = statementRows([row({ id: 'b' })], fills, both);
    expect(rowAccount(rows[0], both, new Map([['b', 'live' as const]]))).toBe('live');
  });

  it('finds a row’s account from its sleeve or its deposit', () => {
    const rows = statementRows(
      [
        row({ id: 'b' }),
        row({ id: 'd', kind: 'deposit', amount: 5 }),
        row({ id: 'o', kind: 'dividend' }),
      ],
      fills,
      both
    );
    const deposits = new Map([['d', 'live' as const]]);
    expect(rows.map((r) => rowAccount(r, both, deposits))).toEqual(['paper', 'live', null]);
    expect(rows[1].entry).toBe('Deposit to unallocated');
  });
});

describe('lastMonth', () => {
  it('keeps the last 30 days and closes on the value now', () => {
    const now = new Date('2026-11-17T15:00:00Z');
    const day = 86_400_000;
    const points = [
      { t: now.getTime() - 40 * day, v: 1 },
      { t: now.getTime() - 20 * day, v: 2 },
      { t: now.getTime() - day, v: 3 },
    ];
    expect(lastMonth(points, 4, now)).toEqual([2, 3, 4]);
    expect(lastMonth([], 4, now)).toEqual([4]);
  });
});
