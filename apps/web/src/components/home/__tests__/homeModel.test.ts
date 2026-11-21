import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import { sessionStateView, type SessionState } from '../../../lib/sessionState';
import {
  benchDayMove,
  blendEquity,
  curveWindow,
  defaultRange,
  fillDays,
  fillsOf,
  foldSessions,
  homeStage,
  marketPhase,
  nextRebalance,
  opensWords,
  rebalancesOn,
  rebalancingToday,
  sessionsLine,
  snapshotDayMove,
  splitByMode,
  todayLine,
  upcoming,
  type HomeSession,
} from '../homeModel';

const day = (s: string) => new Date(`${s}T00:00:00Z`);
const iso = (d: Date) => d.toISOString().slice(0, 10);

function session(over: Partial<HomeSession> = {}): HomeSession {
  const state: SessionState = over.state ?? 'running';
  return {
    id: 's1',
    name: 'Momentum',
    mode: 'paper',
    state,
    view: sessionStateView(state),
    rebalance: 'Monthly',
    value: 1000,
    today: 10,
    todayPct: 0.01,
    startedAt: new Date('2026-06-01T14:00:00Z'),
    stoppedAt: null,
    frozenAt: null,
    equity: [],
    curve: [],
    allocated: 1000,
    href: '/trading/s1',
    ...over,
  };
}

const ts = (iso: string) => ({
  seconds: BigInt(Math.floor(new Date(iso).getTime() / 1000)),
  nanos: 0,
});

function order(over: Partial<Record<string, unknown>> = {}): Order {
  return {
    id: 'o1',
    sessionId: 's1',
    symbol: 'TLT',
    side: OrderSide.BUY,
    status: OrderStatus.FILLED,
    quantity: { value: '42' },
    filledQuantity: { value: '42' },
    averageFillPrice: { value: '90.41' },
    filledAt: ts('2026-11-17T15:31:00Z'),
    ...over,
  } as unknown as Order;
}

describe('rebalancesOn', () => {
  it('runs monthly on the first trading day of the month', () => {
    expect(rebalancesOn('Monthly', day('2026-12-01'))).toBe(true);
    expect(rebalancesOn('Monthly', day('2026-12-02'))).toBe(false);
    // Nov 1 2026 is a Sunday, so the month starts trading on the 2nd.
    expect(rebalancesOn('Monthly', day('2026-11-02'))).toBe(true);
  });

  it('runs weekly on the first trading day of the week, after a Monday holiday too', () => {
    expect(rebalancesOn('Weekly', day('2026-11-23'))).toBe(true);
    expect(rebalancesOn('Weekly', day('2026-11-24'))).toBe(false);
    expect(rebalancesOn('Weekly', day('2026-09-08'))).toBe(true);
  });

  it('covers quarterly, annual and daily schedules and never a closed day', () => {
    expect(rebalancesOn('Quarterly', day('2027-01-04'))).toBe(true);
    expect(rebalancesOn('Quarterly', day('2026-11-02'))).toBe(false);
    expect(rebalancesOn('Annually', day('2027-01-04'))).toBe(true);
    expect(rebalancesOn('Daily', day('2026-11-18'))).toBe(true);
    expect(rebalancesOn('Daily', day('2026-11-26'))).toBe(false);
    expect(rebalancesOn('', day('2026-12-01'))).toBe(false);
  });
});

describe('upcoming', () => {
  it('lists rebalances and holidays in the next two weeks', () => {
    const rows = upcoming(
      [session(), session({ id: 's2', name: 'Sectors', rebalance: 'Weekly' })],
      day('2026-11-17')
    );
    expect(rows.map((r) => [iso(r.day), r.kind, r.sessions.map((s) => s.name).join()])).toEqual([
      ['2026-11-23', 'rebalance', 'Sectors'],
      ['2026-11-26', 'closed', ''],
      ['2026-11-27', 'early', ''],
      ['2026-11-30', 'rebalance', 'Sectors'],
      ['2026-12-01', 'rebalance', 'Momentum'],
    ]);
  });

  it('leaves out stopped, paused and daily sessions', () => {
    const rows = upcoming(
      [
        session({ state: 'stopped' }),
        session({ id: 'p', state: 'paused' }),
        session({ id: 'd', rebalance: 'Daily' }),
      ],
      day('2026-11-17')
    );
    expect(rows.filter((r) => r.kind === 'rebalance')).toEqual([]);
  });

  it('adds the first rebalance after the window when none falls inside it', () => {
    const rows = upcoming([session()], day('2026-11-02'));
    const rebalances = rows.filter((r) => r.kind === 'rebalance');
    expect(rebalances.map((r) => iso(r.day))).toEqual(['2026-12-01']);
  });

  it('keeps frozen sessions on the schedule so the wait can be shown', () => {
    const rows = upcoming([session({ state: 'frozen', rebalance: 'Weekly' })], day('2026-11-17'));
    expect(rows[0].sessions[0].state).toBe('frozen');
  });
});

describe('foldSessions', () => {
  const many = (n: number) =>
    Array.from({ length: n }, (_, i) => session({ id: `s${i}`, name: `S${i}`, value: i * 100 }));

  it('keeps every lane up to eight sessions, largest first', () => {
    const { shown, rest } = foldSessions(many(8));
    expect(shown).toHaveLength(8);
    expect(shown[0].id).toBe('s7');
    expect(rest).toEqual([]);
  });

  it('folds past eight into the five largest and the rest', () => {
    const { shown, rest } = foldSessions(many(9));
    expect(shown.map((s) => s.id)).toEqual(['s8', 's7', 's6', 's5', 's4']);
    expect(rest).toHaveLength(4);
  });

  it('never folds away a frozen session', () => {
    const list = many(9);
    list[0] = session({ id: 'cold', value: 1, state: 'frozen' });
    const { shown, rest } = foldSessions(list);
    expect(shown.map((s) => s.id)).toContain('cold');
    expect(rest.map((s) => s.id)).not.toContain('cold');
  });

  it('puts stopped sessions after open ones', () => {
    const { shown } = foldSessions([
      session({ id: 'big', value: 9000, state: 'stopped' }),
      session({ id: 'small', value: 10 }),
    ]);
    expect(shown.map((s) => s.id)).toEqual(['small', 'big']);
  });
});

describe('fills', () => {
  it('keeps filled and partial orders with their fill price, newest first', () => {
    const fills = fillsOf([
      order(),
      order({ id: 'o2', status: OrderStatus.REJECTED }),
      order({ id: 'o3', side: OrderSide.SELL, filledAt: ts('2026-11-17T16:00:00Z') }),
      order({ id: 'o4', filledAt: undefined }),
      order({
        id: 'o5',
        status: OrderStatus.PARTIAL,
        filledQuantity: { value: '0' },
        quantity: { value: '0' },
      }),
    ]);
    expect(fills.map((f) => [f.id, f.side])).toEqual([
      ['o3', 'sell'],
      ['o1', 'buy'],
    ]);
    expect(fills[1].amount).toBeCloseTo(42 * 90.41);
  });

  it('groups fills by New York day, so an evening fill stays on its day', () => {
    const fills = fillsOf([
      order(),
      order({ id: 'o2', filledAt: ts('2026-11-18T00:30:00Z') }),
      order({ id: 'o3', filledAt: ts('2026-11-18T15:00:00Z') }),
    ]);
    expect(fillDays(fills).map((d) => [iso(d.day), d.count])).toEqual([
      ['2026-11-17', 2],
      ['2026-11-18', 1],
    ]);
  });
});

describe('blendEquity and curveWindow', () => {
  const pts = (rows: [string, number][]) =>
    rows.map(([timestamp, value]) => ({ timestamp, value }));

  it('adds sessions on every date, using allocated capital before a session starts', () => {
    const series = blendEquity([
      session({
        equity: pts([
          ['2026-11-01', 100],
          ['2026-11-03', 110],
        ]),
        allocated: 100,
      }),
      session({ id: 'b', equity: pts([['2026-11-02', 50]]), allocated: 40 }),
    ]);
    expect(series.values).toEqual([140, 150, 160]);
  });

  it('is empty without any snapshots', () => {
    expect(blendEquity([session()])).toEqual({ dates: [], values: [] });
  });

  it('measures the range, its drawdown and SPY over the same dates', () => {
    const series = {
      dates: ['2026-11-01', '2026-11-02', '2026-11-03', '2026-11-04'].map((s) => new Date(s)),
      values: [100, 120, 90, 110],
    };
    const bench = pts([
      ['2026-11-01', 0],
      ['2026-11-04', 10],
    ]);
    const w = curveWindow(series, bench, 'ALL', new Date('2026-11-04T20:00:00Z'));
    expect(w.high).toBe(120);
    expect(w.low).toBe(90);
    expect(w.maxDrawdown).toBeCloseTo(-0.25);
    expect(w.accountReturn).toBeCloseTo(0.1);
    expect(w.bench?.[3]).toBeCloseTo(110);
    expect(w.benchReturn).toBeCloseTo(0.1);
  });

  it('reaches back one snapshot when a range would have only one', () => {
    const series = {
      dates: [new Date('2026-05-10'), new Date('2026-11-16')],
      values: [100, 104],
    };
    const w = curveWindow(series, [], '1M', new Date('2026-11-16T21:00:00Z'));
    expect(w.values).toEqual([100, 104]);
    expect(w.start.getTime()).toBe(series.dates[0].getTime());
    expect(w.bench).toBeNull();
    expect(w.benchReturn).toBeNull();
  });
});

describe('homeStage', () => {
  const today = day('2026-11-17');

  it('is the first visit with no sessions', () => {
    expect(homeStage([], today)).toBe('firstVisit');
  });

  it('spotlights one young open session', () => {
    expect(homeStage([session({ startedAt: new Date('2026-11-16T15:00:00Z') })], today)).toBe(
      'firstSession'
    );
  });

  it('switches to the curve after about five trading days or with more sessions', () => {
    expect(homeStage([session({ startedAt: new Date('2026-11-09T15:00:00Z') })], today)).toBe(
      'ordinary'
    );
    expect(homeStage([session(), session({ id: 'b' })], today)).toBe('ordinary');
    expect(
      homeStage([session({ startedAt: new Date('2026-11-16T15:00:00Z'), state: 'stopped' })], today)
    ).toBe('ordinary');
  });
});

describe('header lines', () => {
  it('counts sessions by state', () => {
    expect(
      sessionsLine([
        session(),
        session({ id: 'b' }),
        session({ id: 'c', state: 'stopped' }),
        session({ id: 'd', state: 'frozen' }),
      ])
    ).toBe('2 sessions running, 1 frozen, 1 stopped');
    expect(sessionsLine([session({ state: 'stopped' })])).toBe('1 session stopped');
    expect(sessionsLine([])).toBe('No sessions');
  });

  it('says how many rebalance today, and nothing on a closed day', () => {
    expect(todayLine([session()], day('2026-12-01'))).toBe('1 rebalance today');
    expect(todayLine([session()], day('2026-12-02'))).toBe('no rebalances today');
    expect(todayLine([session()], day('2026-11-26'))).toBeNull();
    expect(rebalancingToday([session({ state: 'paused' })], day('2026-12-01'))).toEqual([]);
  });

  it('splits value by account kind and skips unknown values', () => {
    expect(
      splitByMode([
        session({ mode: 'live', value: 5 }),
        session({ value: 7 }),
        session({ value: null }),
      ])
    ).toEqual({ live: 5, paper: 7 });
  });
});

describe('marketPhase', () => {
  it('is open during the regular session with today’s close', () => {
    const p = marketPhase(new Date('2026-11-17T15:42:00Z'));
    expect(p.open).toBe(true);
    expect(p.close.toISOString()).toBe('2026-11-17T21:00:00.000Z');
    expect(p.nextOpen).toBeNull();
  });

  it('after the close points back to it and forward to the next open', () => {
    const now = new Date('2026-11-17T23:00:00Z');
    const p = marketPhase(now);
    expect(p.open).toBe(false);
    expect(p.close.toISOString()).toBe('2026-11-17T21:00:00.000Z');
    expect(p.nextOpen?.toISOString()).toBe('2026-11-18T14:30:00.000Z');
    expect(opensWords(p.nextOpen as Date, now)).toBe('tomorrow at 09:30 ET');
  });

  it('skips the weekend and Thanksgiving, and knows the early close', () => {
    const sat = marketPhase(new Date('2026-11-28T15:00:00Z'));
    expect(sat.close.toISOString()).toBe('2026-11-27T18:00:00.000Z');
    expect(sat.closeClock).toBe('13:00');
    expect(sat.nextOpen?.toISOString()).toBe('2026-11-30T14:30:00.000Z');
    const thu = marketPhase(new Date('2026-11-26T15:00:00Z'));
    expect(thu.open).toBe(false);
    expect(thu.close.toISOString()).toBe('2026-11-25T21:00:00.000Z');
  });

  it('before the open looks back to yesterday and forward to today', () => {
    const now = new Date('2026-11-17T13:00:00Z');
    const p = marketPhase(now);
    expect(p.close.toISOString()).toBe('2026-11-16T21:00:00.000Z');
    expect(opensWords(p.nextOpen as Date, now)).toBe('at 09:30 ET');
  });
});

describe('the closed Home', () => {
  const pt = (iso: string, value: number) => ({ timestamp: iso, value });
  const day = new Date(Date.UTC(2026, 10, 17));

  it("reads SPY's move on the day from the percent curve", () => {
    const curve = [
      pt('2026-11-13T21:00:00Z', 1),
      pt('2026-11-16T21:00:00Z', 2),
      pt('2026-11-17T21:00:00Z', 3.02),
    ];
    expect(benchDayMove(curve, day)).toBeCloseTo(1.0302 / 1.02 - 1, 10);
  });

  it('gives no SPY figure without a point on that day or one before it', () => {
    expect(benchDayMove([pt('2026-11-16T21:00:00Z', 2)], day)).toBeNull();
    expect(benchDayMove([pt('2026-11-17T21:00:00Z', 2)], day)).toBeNull();
    expect(benchDayMove([], day)).toBeNull();
  });

  it("falls back to SPY's daily bars when they are from that day", () => {
    const bars = { at: new Date('2026-11-17T14:30:00Z'), close: 612.48, previousClose: 610 };
    expect(snapshotDayMove(bars, day)).toBeCloseTo(612.48 / 610 - 1, 10);
    expect(snapshotDayMove({ ...bars, at: new Date('2026-11-16T14:30:00Z') }, day)).toBeNull();
    expect(snapshotDayMove({ ...bars, previousClose: 0 }, day)).toBeNull();
    expect(snapshotDayMove(null, day)).toBeNull();
  });

  it('opens on the last week after the close', () => {
    expect(defaultRange({ open: false })).toBe('1W');
    expect(defaultRange({ open: true })).toBe('3M');
  });
});

describe('nextRebalance', () => {
  const today = new Date('2026-11-17T00:00:00Z');

  it('finds the first rebalance after today', () => {
    expect(nextRebalance('Weekly', today)?.toISOString().slice(0, 10)).toBe('2026-11-23');
    expect(nextRebalance('Monthly', today)?.toISOString().slice(0, 10)).toBe('2026-12-01');
  });

  it('finds no next rebalance without a schedule', () => {
    expect(nextRebalance('', today)).toBeNull();
  });
});
