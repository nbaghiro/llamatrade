import { describe, expect, it } from 'vitest';

import {
  accountTotals,
  activityCsv,
  causeSentence,
  allocationSegments,
  amountProblem,
  dayChange,
  dayChangeFraction,
  fundsPreview,
  groupByMonth,
  hasTargets,
  parseAmount,
  quickLabel,
  statementFlow,
  weightRows,
  weightScale,
  type FlowKind,
} from '../portfolioView';

const h = (symbol: string, marketValue: number) => ({ symbol, marketValue });

describe('weightRows', () => {
  it('measures each holding against the whole sleeve, cash included, largest first', () => {
    const rows = weightRows([h('IEF', 1000), h('VTI', 3000)], 5000);
    expect(rows.map((r) => r.holding.symbol)).toEqual(['VTI', 'IEF']);
    expect(rows[0].weight).toBeCloseTo(0.6);
    expect(rows[1].weight).toBeCloseTo(0.2);
    expect(rows[0].target).toBeUndefined();
  });

  it('adds target and drift only for symbols that have a target', () => {
    const rows = weightRows([h('A', 450), h('B', 550)], 1000, { A: 0.5 });
    const a = rows.find((r) => r.holding.symbol === 'A');
    const b = rows.find((r) => r.holding.symbol === 'B');
    expect(a?.target).toBe(0.5);
    expect(a?.drift).toBeCloseTo(-0.05);
    expect(b?.drift).toBeUndefined();
    expect(hasTargets(rows)).toBe(true);
    expect(hasTargets(weightRows([h('A', 1)], 1))).toBe(false);
  });

  it('gives zero weights for an empty or non-finite sleeve value', () => {
    expect(weightRows([h('A', 100)], 0)[0].weight).toBe(0);
    expect(weightRows([h('A', 100)], Number.NaN)[0].weight).toBe(0);
  });

  it('treats a negative market value as no weight', () => {
    expect(weightRows([h('A', -50)], 100)[0].weight).toBe(0);
  });

  it('breaks weight ties by symbol so the order is stable', () => {
    const rows = weightRows([h('B', 10), h('A', 10)], 20);
    expect(rows.map((r) => r.holding.symbol)).toEqual(['A', 'B']);
  });
});

describe('weightScale', () => {
  it('leaves headroom above the largest weight or target', () => {
    expect(weightScale(weightRows([h('A', 40), h('B', 60)], 100))).toBeCloseTo(0.7);
    expect(weightScale(weightRows([h('A', 30)], 100, { A: 0.55 }))).toBeCloseTo(0.7);
  });

  it('never exceeds the full track and falls back to 1 for empty rows', () => {
    expect(weightScale(weightRows([h('A', 100)], 100))).toBe(1);
    expect(weightScale([])).toBe(1);
  });
});

describe('accountTotals', () => {
  it('adds sleeves and ledger unallocated cash so the ruled total adds up', () => {
    expect(accountTotals([35982.55, 25436.18, 24914.42], 17077.12)).toEqual({
      sleeves: 86333.15,
      unallocated: 17077.12,
      total: 103410.27,
    });
  });

  it('derives unallocated from the account summary when the ledger figure is missing', () => {
    const t = accountTotals([600, 300], null, 1000);
    expect(t).toEqual({ sleeves: 900, unallocated: 100, total: 1000 });
  });

  it('never reports a negative unallocated remainder from a stale summary', () => {
    expect(accountTotals([600, 300], null, 500)).toEqual({
      sleeves: 900,
      unallocated: 0,
      total: 900,
    });
  });

  it('clamps negative inputs and ignores non-finite values', () => {
    expect(accountTotals([-10, Number.NaN, 50], -5)).toEqual({
      sleeves: 50,
      unallocated: 0,
      total: 50,
    });
  });

  it('handles an empty account', () => {
    expect(accountTotals([], 0)).toEqual({ sleeves: 0, unallocated: 0, total: 0 });
    expect(accountTotals([], null)).toEqual({ sleeves: 0, unallocated: 0, total: 0 });
  });
});

describe('allocationSegments', () => {
  it('gives each sleeve and unallocated cash its share of the account', () => {
    const { sleeves, unallocated } = allocationSegments(
      [
        { id: 'a', value: 300 },
        { id: 'b', value: 500 },
      ],
      200
    );
    expect(sleeves.map((s) => s.share)).toEqual([0.3, 0.5]);
    expect(unallocated.share).toBeCloseTo(0.2);
    expect(sleeves.reduce((s, x) => s + x.share, unallocated.share)).toBeCloseTo(1);
  });

  it('returns zero shares for an empty account instead of dividing by zero', () => {
    const { sleeves, unallocated } = allocationSegments([{ id: 'a', value: 0 }], 0);
    expect(sleeves[0].share).toBe(0);
    expect(unallocated.share).toBe(0);
  });

  it('treats negative values as empty segments', () => {
    const { sleeves, unallocated } = allocationSegments([{ id: 'a', value: -100 }], 100);
    expect(sleeves[0].share).toBe(0);
    expect(unallocated.share).toBe(1);
  });
});

describe('dayChange', () => {
  it('backs today’s dollar change out of a value that already includes it', () => {
    expect(dayChange(110, 10)).toBeCloseTo(10);
    expect(dayChange(90, -10)).toBeCloseTo(-10);
  });

  it('is zero for a flat day, a missing return or a total loss', () => {
    expect(dayChange(1000, 0)).toBe(0);
    expect(dayChange(1000, Number.NaN)).toBe(0);
    expect(dayChange(0, -100)).toBe(0);
  });

  it('expresses the change against yesterday’s value', () => {
    expect(dayChangeFraction(103410.27, 895.4)).toBeCloseTo(895.4 / (103410.27 - 895.4));
    expect(dayChangeFraction(0, 0)).toBe(0);
  });
});

describe('fundsPreview', () => {
  const totals = { sleeves: 86333.15, unallocated: 17077.12, total: 103410.27 };

  it('credits unallocated cash and the total, leaving sleeves unchanged', () => {
    const rows = fundsPreview(totals, 25000);
    expect(rows.map((r) => [r.key, r.now, r.after])).toEqual([
      ['unallocated', 17077.12, 42077.12],
      ['sleeves', 86333.15, 86333.15],
      ['total', 103410.27, 128410.27],
    ]);
  });

  it('shows no change for an invalid amount', () => {
    for (const amount of [0, -5, Number.NaN]) {
      expect(fundsPreview(totals, amount).every((r) => r.now === r.after)).toBe(true);
    }
  });
});

describe('amount entry', () => {
  it('reads typed dollar amounts with separators and a dollar sign', () => {
    expect(parseAmount('25,000')).toBe(25000);
    expect(parseAmount(' $1,250.50 ')).toBe(1250.5);
    expect(parseAmount('100.')).toBe(100);
  });

  it('rejects empty, zero, negative, over-precise and non-numeric input', () => {
    for (const input of ['', '0', '-5', '1.234', 'abc', '1e5', '..']) {
      expect(parseAmount(input)).toBeNull();
    }
  });

  it('explains what is wrong with an amount', () => {
    expect(amountProblem(null)).toMatch(/Enter an amount/);
    expect(amountProblem(10_000_001)).toMatch(/up to/);
    expect(amountProblem(25000)).toBeNull();
  });

  it('labels quick amounts compactly', () => {
    expect(quickLabel(25000)).toBe('+25K');
    expect(quickLabel(1_000_000)).toBe('+1M');
  });
});

describe('statementFlow', () => {
  const flow = (kind: FlowKind, amount = 100) => statementFlow({ kind, amount });

  it('puts money arriving in paid in', () => {
    for (const kind of ['deposit', 'release', 'sell', 'dividend', 'interest'] as const) {
      expect(flow(kind)).toEqual({ paidIn: 100, paidOut: 0 });
    }
  });

  it('puts money leaving in paid out', () => {
    for (const kind of ['withdrawal', 'allocation', 'buy', 'fee'] as const) {
      expect(flow(kind)).toEqual({ paidIn: 0, paidOut: 100 });
    }
  });

  it('uses the magnitude whatever the sign, and leaves unknown entries out', () => {
    expect(flow('buy', -250)).toEqual({ paidIn: 0, paidOut: 250 });
    expect(flow('other')).toEqual({ paidIn: 0, paidOut: 0 });
  });
});

describe('groupByMonth', () => {
  const row = (iso: string, kind: FlowKind, amount: number) => ({
    at: new Date(iso),
    kind,
    amount,
  });
  const now = new Date(2026, 10, 16);

  it('groups newest-first rows by month and keeps their order', () => {
    const rows = [
      row('2026-11-06T14:00:00', 'dividend', 41.2),
      row('2026-11-02T14:31:00', 'buy', 9999.9),
      row('2026-10-01T13:30:00', 'allocation', 25000),
      row('2026-10-01T13:28:00', 'deposit', 25000),
    ];
    const groups = groupByMonth(rows, statementFlow, now);
    expect(groups.map((g) => [g.label, g.rows.length])).toEqual([
      ['November', 2],
      ['October', 2],
    ]);
    expect(groups[0].rows[0]).toBe(rows[0]);
    expect(groups[0].paidIn).toBeCloseTo(41.2);
    expect(groups[0].paidOut).toBeCloseTo(9999.9);
    expect(groups[1].paidIn).toBe(25000);
    expect(groups[1].paidOut).toBe(25000);
  });

  it('names the year for months outside the current year', () => {
    const groups = groupByMonth([row('2025-12-31T12:00:00', 'deposit', 1)], statementFlow, now);
    expect(groups[0].label).toBe('December 2025');
    expect(groups[0].key).toBe('2025-12');
  });

  it('keeps the same month of different years apart', () => {
    const groups = groupByMonth(
      [row('2026-11-01T12:00:00', 'deposit', 1), row('2025-11-01T12:00:00', 'deposit', 1)],
      statementFlow,
      now
    );
    expect(groups.map((g) => g.label)).toEqual(['November', 'November 2025']);
  });

  it('returns no groups for no rows', () => {
    expect(groupByMonth([], statementFlow, now)).toEqual([]);
  });
});

describe('activityCsv', () => {
  it('writes a header and one line per entry, quoting cells that need it', () => {
    const csv = activityCsv(
      [
        {
          at: new Date('2026-11-02T14:31:00Z'),
          label: 'Buy GLD',
          sublabel: '41 @ $243.90, "Radar"',
          kind: 'buy',
          amount: 9999.9,
        },
        {
          at: new Date('2026-10-01T13:28:00Z'),
          label: 'Deposit',
          sublabel: 'Paper credit',
          kind: 'deposit',
          amount: 25000,
        },
      ],
      (k) => (k === 'buy' ? 'Trades' : 'Funding')
    );
    expect(csv.split('\n')).toEqual([
      'Date,Entry,Detail,Type,Paid in,Paid out',
      '2026-11-02T14:31:00.000Z,Buy GLD,"41 @ $243.90, ""Radar""",Trades,,9999.90',
      '2026-10-01T13:28:00.000Z,Deposit,Paper credit,Funding,25000.00,',
    ]);
  });
});

describe('causeSentence', () => {
  it('drops the Connect code prefix and ends with a full stop', () => {
    expect(causeSentence('[internal] portfolio service returned 500')).toBe(
      'Portfolio service returned 500.'
    );
  });

  it('keeps existing punctuation and handles empty messages', () => {
    expect(causeSentence('[unavailable] Service is down!')).toBe('Service is down!');
    expect(causeSentence('Timed out.')).toBe('Timed out.');
    expect(causeSentence('[internal] ')).toBe('');
  });
});
