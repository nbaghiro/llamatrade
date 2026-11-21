import { describe, expect, it } from 'vitest';

import { sessionStateView } from '../../../lib/sessionState';
import type { Fill, HomeSession } from '../homeModel';
import { drawdownOf, indexOnDay, lineAlong, monthOf, perfWindow } from '../perfModel';

const at = (d: string) => new Date(`${d}T21:00:00Z`);
const dates = ['2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13', '2026-11-16'].map(at);

function session(over: Partial<HomeSession> = {}): HomeSession {
  return {
    id: 's1',
    name: 'Radar',
    mode: 'paper',
    state: 'running',
    view: sessionStateView('running'),
    rebalance: 'Monthly',
    value: 1000,
    today: 10,
    todayPct: 0.01,
    startedAt: null,
    stoppedAt: null,
    frozenAt: null,
    equity: [],
    curve: [],
    allocated: 1000,
    href: '/trading/s1',
    ...over,
  };
}

const fill = (id: string, when: string, sessionId = 's1'): Fill => ({
  id,
  sessionId,
  symbol: 'TLT',
  side: 'buy',
  quantity: 1,
  price: 90,
  amount: 90,
  at: new Date(when),
});

describe('drawdownOf', () => {
  it('measures each point against the highest before it', () => {
    const dd = drawdownOf([0, 10, 0, 21]);
    expect(dd[0]).toBe(0);
    expect(dd[1]).toBe(0);
    expect(dd[2]).toBeCloseTo(-9.09, 2);
    expect(dd[3]).toBe(0);
  });
});

describe('indexOnDay', () => {
  it('finds the last snapshot on or before the day', () => {
    expect(indexOnDay(dates, new Date('2026-11-12T15:00:00Z'))).toBe(2);
    expect(indexOnDay(dates, new Date('2026-11-15T15:00:00Z'))).toBe(3);
    expect(indexOnDay(dates, new Date('2026-11-01T15:00:00Z'))).toBe(-1);
  });
});

describe('lineAlong', () => {
  it('reads points on the chart dates, null before they start, rebased to their first value', () => {
    const line = lineAlong(dates, [
      { timestamp: at('2026-11-12').toISOString(), value: 200 },
      { timestamp: at('2026-11-16').toISOString(), value: 210 },
    ]);
    expect(line.slice(0, 4)).toEqual([null, null, 0, 0]);
    expect(line[4]).toBeCloseTo(5, 6);
  });
});

describe('perfWindow', () => {
  const series = { dates, values: [100, 104, 102, 98, 101] };
  const bench = dates.map((d, i) => ({ timestamp: d.toISOString(), value: [0, 1, 2, 3, 4][i] }));
  const end = new Date('2026-11-16T22:00:00Z');

  it('turns values into returns and finds the worst drop', () => {
    const p = perfWindow(series, bench, [], [], '1M', end);
    expect(p?.acc[4]).toBeCloseTo(1, 6);
    expect(p?.spy?.[4]).toBeCloseTo(4, 6);
    expect(p?.worst).toBe(3);
    expect(p?.accDrawdown[3]).toBeCloseTo((98 / 104 - 1) * 100, 6);
  });

  it('groups fills into one dot per session and day', () => {
    const p = perfWindow(
      series,
      bench,
      [],
      [
        fill('a', '2026-11-12T15:00:00Z'),
        fill('b', '2026-11-12T15:01:00Z'),
        fill('c', '2026-11-12T15:02:00Z', 's2'),
        fill('d', '2026-10-01T15:00:00Z'),
      ],
      '1M',
      end
    );
    expect(p?.fills).toBe(3);
    expect(p?.dots).toEqual([
      { index: 2, sessionId: 's1', fills: 2 },
      { index: 2, sessionId: 's2', fills: 1 },
    ]);
  });

  it('numbers session starts and stops inside the range in date order', () => {
    const p = perfWindow(
      series,
      bench,
      [
        session({ stoppedAt: new Date('2026-11-13T18:00:00Z'), name: 'Tech' }),
        session({ id: 's2', startedAt: new Date('2026-11-11T15:00:00Z') }),
        session({ id: 's3', startedAt: new Date('2026-01-05T15:00:00Z') }),
      ],
      [],
      '1M',
      end
    );
    expect(p?.changes.map((c) => [c.label, c.index])).toEqual([
      ['Radar started', 1],
      ['Tech stopped', 3],
    ]);
  });

  it('is null with under two snapshots', () => {
    expect(perfWindow({ dates: [dates[0]], values: [1] }, [], [], [], '1M', end)).toBeNull();
  });
});

describe('monthOf', () => {
  const end = new Date('2026-11-16T22:00:00Z');

  it('returns the past month with SPY on the same dates', () => {
    const m = monthOf(
      dates.map((d, i) => ({ timestamp: d.toISOString(), value: 100 + i })),
      dates.map((d, i) => ({ timestamp: d.toISOString(), value: i })),
      end
    );
    expect(m.ret).toBeCloseTo(4, 6);
    expect(m.spy?.length).toBe(5);
  });

  it('has no return without recent history', () => {
    const old = [at('2026-06-01'), at('2026-06-02')];
    const m = monthOf(
      old.map((d) => ({ timestamp: d.toISOString(), value: 100 })),
      [],
      end
    );
    expect(m.ret).toBeNull();
    expect(monthOf([], [], end).ret).toBeNull();
  });
});
