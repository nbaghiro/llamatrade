import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import { describe, expect, it } from 'vitest';

import { buildSessionRow, sessionName, sortRows } from '../sessionRows';

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
        returns: { return1d: { value: '5' } },
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
    expect(row.figures.todayPct).toBeCloseTo(0.05, 9);
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
