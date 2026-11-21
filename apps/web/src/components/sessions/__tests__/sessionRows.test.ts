import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import { describe, expect, it } from 'vitest';

import {
  buildSessionRow,
  dayLabel,
  isDaily,
  marketNotes,
  nextDailyRun,
  nextRun,
  relativeDay,
  sessionName,
  sortRows,
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

describe('next runs and market notes', () => {
  // 10:42 ET on Tue Nov 17 2026 (EST, UTC-5).
  const morning = new Date('2026-11-17T15:42:00Z');
  const evening = new Date('2026-11-17T22:00:00Z');
  const utc = (s: string) => new Date(`${s}T00:00:00Z`);

  it('runs a daily schedule today before the close, else the next trading day', () => {
    expect(nextDailyRun(morning)).toEqual(utc('2026-11-17'));
    expect(nextDailyRun(evening)).toEqual(utc('2026-11-18'));
  });

  it('skips Thanksgiving and the weekend for a daily run', () => {
    expect(nextDailyRun(new Date('2026-11-25T22:00:00Z'))).toEqual(utc('2026-11-27'));
    expect(nextDailyRun(new Date('2026-11-27T19:00:00Z'))).toEqual(utc('2026-11-30'));
  });

  it('uses the period schedule for anything but daily', () => {
    expect(nextRun('Monthly', morning)).toEqual(utc('2026-12-01'));
    expect(nextRun('Daily', morning)).toEqual(utc('2026-11-17'));
    expect(nextRun('', morning)).toBeNull();
    expect(isDaily(' daily ')).toBe(true);
  });

  it('names today and tomorrow', () => {
    const today = utc('2026-11-17');
    expect(relativeDay(today, today)).toBe('today');
    expect(relativeDay(utc('2026-11-18'), today)).toBe('tomorrow');
    expect(relativeDay(utc('2026-12-01'), today)).toBe('Dec 1');
  });

  it('lists weekday closures and early closes in a window', () => {
    const notes = marketNotes(utc('2026-11-17'), utc('2026-12-01'));
    expect(notes.map((n) => [dayLabel(n.at), n.text])).toEqual([
      ['Nov 26', 'Market closed, Thanksgiving'],
      ['Nov 27', 'Market closes 13:00, Day after Thanksgiving'],
    ]);
    expect(marketNotes(utc('2026-12-02'), utc('2026-12-10'))).toEqual([]);
  });
});
