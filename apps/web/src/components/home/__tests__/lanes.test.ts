import { describe, expect, it } from 'vitest';

import { sessionStateView, type SessionState } from '../../../lib/sessionState';
import type { Fill, HomeSession } from '../homeModel';
import {
  curvePins,
  laneEvents,
  laneFuture,
  laneSpans,
  mergedEvents,
  nextRebalance,
  type LaneWindow,
} from '../lanes';

const w: LaneWindow = {
  start: new Date('2026-08-17T00:00:00Z'),
  end: new Date('2026-11-17T15:42:00Z'),
  today: new Date('2026-11-17T00:00:00Z'),
  futureEnd: new Date('2026-12-01T00:00:00Z'),
};

function session(over: Partial<HomeSession> = {}): HomeSession {
  const state: SessionState = over.state ?? 'running';
  return {
    id: 's1',
    name: 'Momentum',
    mode: 'paper',
    state,
    view: sessionStateView(state),
    rebalance: 'Weekly',
    value: 1000,
    today: 0,
    todayPct: 0,
    startedAt: new Date('2026-09-01T14:00:00Z'),
    stoppedAt: null,
    frozenAt: null,
    equity: [],
    curve: [],
    allocated: 1000,
    href: '/trading/s1',
    ...over,
  };
}

const fill = (at: string, id = at): Fill => ({
  id,
  sessionId: 's1',
  symbol: 'TLT',
  side: 'buy',
  quantity: 1,
  price: 1,
  amount: 1,
  at: new Date(at),
});

describe('laneEvents', () => {
  it('marks the start, past fill days as rings and today as a numbered dot', () => {
    const events = laneEvents(
      session(),
      [
        fill('2026-10-05T15:00:00Z'),
        fill('2026-11-17T14:45:00Z', 'a'),
        fill('2026-11-17T15:31:00Z', 'b'),
      ],
      w
    );
    expect(events.map((e) => [e.shape, e.count ?? null])).toEqual([
      ['start', null],
      ['ring', null],
      ['dot', 2],
    ]);
    expect(events[2].at).toBe(w.end);
  });

  it('drops marks outside the window and adds the stop', () => {
    const events = laneEvents(
      session({
        startedAt: new Date('2026-01-01'),
        stoppedAt: new Date('2026-11-12T15:00:00Z'),
        state: 'stopped',
      }),
      [fill('2026-02-01T15:00:00Z')],
      w
    );
    expect(events.map((e) => e.shape)).toEqual(['stop']);
  });

  it('paints a frozen session amber', () => {
    const events = laneEvents(session({ state: 'frozen' }), [fill('2026-10-05T15:00:00Z')], w);
    expect(events.find((e) => e.shape === 'ring')?.tone).toBe('risk');
  });
});

describe('laneSpans', () => {
  it('runs from the start to the end of the past', () => {
    expect(laneSpans(session(), w)).toEqual([{ from: session().startedAt, style: 'on' }]);
  });

  it('starts at the window when the session is older', () => {
    expect(laneSpans(session({ startedAt: new Date('2026-01-01') }), w)[0].from).toBe(w.start);
  });

  it('ends at the stop, and hides a session stopped before the window', () => {
    const stoppedAt = new Date('2026-11-12T15:00:00Z');
    expect(laneSpans(session({ stoppedAt, state: 'stopped' }), w)).toEqual([
      { from: session().startedAt, to: stoppedAt, style: 'off' },
    ]);
    expect(laneSpans(session({ stoppedAt: new Date('2026-08-01'), state: 'stopped' }), w)).toEqual(
      []
    );
  });

  it('turns amber from the moment it froze', () => {
    const frozenAt = new Date('2026-11-14T15:00:00Z');
    const spans = laneSpans(session({ state: 'frozen', frozenAt }), w);
    expect(spans).toEqual([
      { from: session().startedAt, to: frozenAt, style: 'on' },
      { from: frozenAt, style: 'on', tone: 'risk' },
    ]);
  });
});

describe('laneFuture', () => {
  it('plans each weekly rebalance in the next two weeks', () => {
    const f = laneFuture(session(), w);
    expect(f.events?.map((e) => e.at.toISOString().slice(0, 10))).toEqual([
      '2026-11-23',
      '2026-11-30',
    ]);
  });

  it('notes the next date when none falls inside the column', () => {
    const f = laneFuture(session({ rebalance: 'Quarterly' }), w);
    expect(f.note).toBe('Next Jan 4');
  });

  it('says why nothing is planned', () => {
    expect(laneFuture(session({ state: 'stopped' }), w).note).toBe('Stopped');
    expect(laneFuture(session({ state: 'paused' }), w).note).toBe('Paused');
    expect(laneFuture(session({ state: 'frozen' }), w).note).toBe('Waits for review');
    expect(laneFuture(session({ rebalance: 'Daily' }), w).note).toBe('Each trading day');
  });

  it('finds no next rebalance without a schedule', () => {
    expect(nextRebalance('', w.today)).toBeNull();
  });
});

describe('mergedEvents', () => {
  it('adds dot counts on the same day and keeps one ring per day', () => {
    const at = new Date('2026-11-17T15:00:00Z');
    const ring = new Date('2026-10-05T20:00:00Z');
    const merged = mergedEvents([
      [
        { at, shape: 'dot', count: 2 },
        { at: ring, shape: 'ring' },
        { at: ring, shape: 'start' },
      ],
      [
        { at, shape: 'dot', count: 1 },
        { at: ring, shape: 'ring' },
      ],
    ]);
    expect(merged.map((e) => [e.shape, e.count ?? null])).toEqual([
      ['ring', null],
      ['dot', 3],
    ]);
  });
});

describe('curvePins', () => {
  it('pins starts and stops in the window, then today’s fills last', () => {
    const pins = curvePins(
      [
        session({ name: 'A', startedAt: new Date('2026-09-01T14:00:00Z') }),
        session({
          id: 'b',
          name: 'B',
          startedAt: new Date('2026-09-03T14:00:00Z'),
          stoppedAt: new Date('2026-11-12T15:00:00Z'),
        }),
        session({ id: 'c', name: 'C', startedAt: new Date('2026-01-01') }),
      ],
      3,
      w
    );
    expect(pins.map((p) => p.label)).toEqual([
      'A started',
      'B started',
      'B stopped Nov 12',
      'Fills today',
    ]);
    expect(pins.map((p) => p.row)).toEqual([0, 1, 0, 1]);
    expect(pins[3]).toMatchObject({ tone: 'accent', count: 3, guide: false });
  });

  it('keeps at most the most recent pins', () => {
    const many = Array.from({ length: 10 }, (_, i) =>
      session({ id: `s${i}`, name: `S${i}`, startedAt: new Date(Date.UTC(2026, 8, 1 + i * 5)) })
    );
    const pins = curvePins(many, 0, w, 4);
    expect(pins.map((p) => p.label)).toEqual([
      'S6 started',
      'S7 started',
      'S8 started',
      'S9 started',
    ]);
  });
});
