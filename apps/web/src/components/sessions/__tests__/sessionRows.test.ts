import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import { describe, expect, it } from 'vitest';

import {
  buildSessionRow,
  nextRebalanceCell,
  railFacts,
  sessionName,
  sortRows,
  statusSentence,
} from '../sessionRows';

type Session = Parameters<typeof buildSessionRow>[0];
type Ctx = Parameters<typeof buildSessionRow>[1];

const session = (over: Record<string, unknown>) =>
  ({
    id: 's1',
    name: 'Core Four (paper)',
    strategyId: 'st1',
    sleeveId: 'sl1',
    isActive: true,
    ...over,
  }) as unknown as Session;

const ctx = (over: Partial<Record<keyof Ctx, unknown[]>> = {}) =>
  ({
    executions: [{ id: 'e1', sleeveId: 'sl1', status: ExecutionStatus.RUNNING, version: 2 }],
    sleeves: [{ id: 'sl1', status: SleeveStatus.ACTIVE, cash: { balance: { value: '500' } } }],
    performance: [
      {
        executionId: 'e1',
        currentValue: { value: '10500' },
        allocatedCapital: { value: '10000' },
        returns: { return1d: { value: '0.05' } },
      },
    ],
    strategies: [{ id: 'st1', name: 'Core Four', version: 3, rebalance: 'quarterly' }],
    orders: [{ sessionId: 's1' }, { sessionId: 's2' }],
    ...over,
  }) as unknown as Ctx;

describe('buildSessionRow', () => {
  it('joins execution, sleeve, performance and strategy', () => {
    const row = buildSessionRow(session({}), ctx());
    expect(row).toMatchObject({
      name: 'Core Four',
      version: 2,
      rebalance: 'Quarterly',
      state: 'running',
      orders: 1,
    });
    expect(row.figures.equity).toBe(10500);
    expect(row.figures.total).toBe(500);
    expect(row.figures.today).toBeCloseTo(500, 6);
  });

  it('marks a frozen sleeve and leaves figures empty without performance', () => {
    const row = buildSessionRow(
      session({}),
      ctx({ sleeves: [{ id: 'sl1', status: SleeveStatus.FROZEN }], performance: [] })
    );
    expect(row.state).toBe('frozen');
    expect(row.view.attention).toBe(true);
    expect(row.figures.equity).toBeNull();
  });

  it('reads a stopped session from ended_at and falls back to the session name', () => {
    const row = buildSessionRow(
      session({ isActive: false, endedAt: { seconds: 1n } }),
      ctx({ strategies: [] })
    );
    expect(row.state).toBe('stopped');
    expect(row.name).toBe('Core Four');
    expect(sessionName(session({ name: 'Plain' }))).toBe('Plain');
  });

  it('sorts attention first and stopped last', () => {
    const a = buildSessionRow(
      session({ id: 'a', isActive: false, endedAt: { seconds: 1n } }),
      ctx()
    );
    const b = buildSessionRow(
      session({ id: 'b' }),
      ctx({ sleeves: [{ id: 'sl1', status: SleeveStatus.FROZEN }] })
    );
    const c = buildSessionRow(session({ id: 'c' }), ctx());
    expect(sortRows([a, c, b]).map((r) => r.session.id)).toEqual(['b', 'c', 'a']);
  });
});

describe('nextRebalanceCell', () => {
  const today = new Date(Date.UTC(2026, 10, 13));
  it('dates a running session and words the other states', () => {
    expect(nextRebalanceCell(buildSessionRow(session({}), ctx()), today)).toBe('Jan 4');
    const cell = (over: Parameters<typeof ctx>[0], s: Record<string, unknown> = {}) =>
      nextRebalanceCell(buildSessionRow(session(s), ctx(over)), today);
    expect(cell({ sleeves: [{ id: 'sl1', status: SleeveStatus.FROZEN }] })).toBe('Held');
    expect(
      cell({ executions: [{ id: 'e1', sleeveId: 'sl1', status: ExecutionStatus.PAUSED }] })
    ).toBe('·');
    expect(cell({}, { isActive: false, endedAt: { seconds: 1n } })).toBe('·');
    expect(cell({ strategies: [{ id: 'st1', name: 'D', version: 1, rebalance: 'daily' }] })).toBe(
      'Each trading day'
    );
  });
});

describe('railFacts', () => {
  it('reports open schedules and frozen sessions in amber', () => {
    const frozen = buildSessionRow(
      session({ id: 'b' }),
      ctx({ sleeves: [{ id: 'sl1', status: SleeveStatus.FROZEN }] })
    );
    const running = buildSessionRow(session({ id: 'a' }), ctx());
    const facts = railFacts(
      [frozen, running],
      'Market open · 10:42 ET',
      true,
      new Date(Date.UTC(2026, 10, 13))
    );
    expect(facts.map((f) => f.value)).toEqual([
      'Open · 10:42 ET',
      'IEX · daily bars',
      'Jan 4 · Core Four',
      '1 session frozen',
    ]);
    expect(facts[3].attention).toBe(true);
  });

  it('names the soonest rebalance, or counts the sessions sharing it', () => {
    const today = new Date(Date.UTC(2026, 10, 13));
    const monthly = (id: string) =>
      buildSessionRow(
        session({ id }),
        ctx({ strategies: [{ id: 'st1', name: 'Core Four', version: 3, rebalance: 'monthly' }] })
      );
    const quarterly = buildSessionRow(session({ id: 'q' }), ctx());
    expect(railFacts([quarterly, monthly('m1')], 'Market open', true, today)[2].value).toBe(
      'Dec 1 · Core Four'
    );
    expect(railFacts([monthly('m1'), monthly('m2')], 'Market open', true, today)[2].value).toBe(
      'Dec 1 · 2 sessions'
    );
  });

  it("doesn't claim anything about sessions that couldn't be loaded", () => {
    expect(
      railFacts(null, 'Market open', true)
        .map((f) => f.value)
        .slice(2)
    ).toEqual(['Not available', 'Not available']);
  });

  it("doesn't claim reconciliation it can't see", () => {
    expect(railFacts([], 'Market closed · opens Mon 9:30 ET', false).map((f) => f.value)).toEqual([
      'Closed · opens Mon 9:30 ET',
      'IEX · daily bars',
      'No open sessions',
      'Not available',
    ]);
  });
});

describe('statusSentence', () => {
  const nov2 = new Date(2026, 10, 2);

  it('names up to three holdings and the schedule', () => {
    expect(
      statusSentence({
        holdings: [
          { symbol: 'SMH', value: 12150 },
          { symbol: 'QQQ', value: 12379 },
        ],
        rebalance: 'Monthly',
        open: true,
        lastOrder: nov2,
      })
    ).toBe(
      'Holding QQQ and SMH. It rebalances monthly, and nothing trades in between. The last orders were placed on Nov 2.'
    );
  });

  it('summarises many holdings and a fresh session', () => {
    const holdings = ['A', 'B', 'C', 'D'].map((symbol, i) => ({ symbol, value: 10 + i }));
    expect(statusSentence({ holdings, rebalance: '', open: true, lastOrder: null })).toBe(
      'Holding 4 positions, the largest D. It trades only when it rebalances. No orders have been placed yet.'
    );
    expect(
      statusSentence({ holdings: [], rebalance: 'Monthly', open: false, lastOrder: null })
    ).toBe('No positions are held.');
  });
});
