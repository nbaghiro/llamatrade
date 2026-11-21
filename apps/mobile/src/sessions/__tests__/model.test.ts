import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  countLine,
  displayName,
  groupByAccount,
  laneX,
  mixOverTime,
  needsLine,
  needsYou,
  rebalanceDays,
  sessionState,
  symbolLanes,
  todayChange,
  toRow,
  weightChange,
  type FillInput,
  type SessionInput,
} from '../model.ts';

const DAY = 86_400_000;
const T0 = new Date(2026, 5, 2, 10, 30).getTime();

function session(over: Partial<SessionInput>): SessionInput {
  return {
    id: 's1',
    name: 'Recession Radar (paper)',
    mode: 'paper',
    active: true,
    startedAt: T0,
    endedAt: null,
    sleeveId: 'sl1',
    strategyId: 'st1',
    executionId: 'e1',
    execution: 'running',
    sleeveFrozen: false,
    value: 31867.77,
    return1dPct: 0.586,
    returnAllPct: 12.4,
    version: 3,
    ...over,
  };
}

describe('displayName', () => {
  it('drops the mode suffix the session name carries', () => {
    assert.equal(displayName('Recession Radar (paper)'), 'Recession Radar');
    assert.equal(displayName('All-Weather Portfolio'), 'All-Weather Portfolio');
    assert.equal(displayName('X (Live)'), 'X');
  });
});

describe('sessionState', () => {
  it('reads a session that ended as stopped, not paused', () => {
    assert.equal(sessionState(session({ active: false, endedAt: T0 + DAY, execution: 'stopped' })), 'stopped');
    assert.equal(sessionState(session({ execution: 'stopped' })), 'stopped');
  });
  it('puts a frozen sleeve ahead of running', () => {
    assert.equal(sessionState(session({ sleeveFrozen: true })), 'frozen');
  });
  it('keeps paused, error and pending distinct', () => {
    assert.equal(sessionState(session({ execution: 'paused' })), 'paused');
    assert.equal(sessionState(session({ execution: 'error' })), 'error');
    assert.equal(sessionState(session({ execution: 'pending' })), 'waiting');
    assert.equal(sessionState(session({ execution: null })), 'running');
  });
});

describe('todayChange', () => {
  it('turns a percent return into the dollars it added', () => {
    const v = todayChange(10_100, 1);
    assert.ok(v !== null && Math.abs(v - 100) < 1e-9);
  });
  it('is null without a value or a return', () => {
    assert.equal(todayChange(null, 1), null);
    assert.equal(todayChange(100, null), null);
    assert.equal(todayChange(100, -100), null);
  });
  it('is left out for stopped sessions', () => {
    assert.equal(toRow(session({ active: false, endedAt: T0 })).today, null);
  });
});

describe('groupByAccount', () => {
  const rows = [
    toRow(session({ id: 'a', name: 'Tech Momentum Rotation (paper)', active: false, endedAt: T0, execution: 'stopped', value: 26198.65 })),
    toRow(session({ id: 'b', value: 31867.77 })),
    toRow(session({ id: 'c', name: 'All-Weather Portfolio', mode: 'live', value: 48413.97 })),
    toRow(session({ id: 'd', name: 'Momentum Sectors (paper)', value: 21916.57, sleeveFrozen: true })),
  ];
  const groups = groupByAccount(rows);
  it('puts live above paper', () => {
    assert.deepEqual(groups.map((g) => g.mode), ['live', 'paper']);
  });
  it('orders frozen, then running by value, then stopped', () => {
    assert.deepEqual(groups[1].rows.map((r) => r.id), ['d', 'b', 'a']);
  });
  it('totals only sessions that still hold money', () => {
    assert.ok(Math.abs(groups[1].total - (31867.77 + 21916.57)) < 1e-6);
    assert.equal(groups[1].counted, 2);
  });
  it('counts running and stopped for the subtitle', () => {
    assert.equal(countLine(rows), '3 running, 1 stopped');
    assert.equal(countLine([]), '');
  });
});

describe('needsYou', () => {
  const rows = [toRow(session({ id: 'm', name: 'Momentum Sectors (paper)', sleeveFrozen: true })), toRow(session({}))];
  const items = needsYou(
    rows,
    [
      { id: 'o1', side: 'buy', symbol: 'TLT', quantity: 124, message: 'over $10,000', at: T0, sessionId: 's1' },
      { id: 'o2', side: 'sell', symbol: 'GLD', quantity: 3.5, message: '', at: T0 + 60_000, sessionId: 'zz' },
    ],
    () => '10:31',
  );
  it('lists frozen sessions first, then rejected orders newest first', () => {
    assert.deepEqual(items.map((i) => i.id), ['frozen-m', 'order-o2', 'order-o1']);
    assert.equal(items[0].title, 'Momentum Sectors is frozen');
    assert.equal(items[2].title, 'Buy 124 TLT rejected');
    assert.equal(items[2].detail, 'Recession Radar · over $10,000 · 10:31');
    assert.equal(items[1].title, 'Sell 3.5 GLD rejected');
  });
  it('says how many things need you', () => {
    assert.equal(needsLine(0), '');
    assert.equal(needsLine(1), '1 thing needs you');
    assert.equal(needsLine(2), '2 things need you');
  });
});

const fills: FillInput[] = [
  { id: 'f1', symbol: 'TLT', side: 'buy', quantity: 100, price: 90, at: T0 },
  { id: 'f2', symbol: 'GLD', side: 'buy', quantity: 40, price: 200, at: T0 + 1000 },
  { id: 'f3', symbol: 'GLD', side: 'sell', quantity: 10, price: 210, at: T0 + 2 * DAY },
];

describe('rebalanceDays', () => {
  it('groups fills by the day they filled', () => {
    const days = rebalanceDays([...fills].reverse());
    assert.equal(days.length, 2);
    assert.deepEqual(days[0].fills.map((f) => f.id), ['f1', 'f2']);
    assert.equal(days[0].at, T0);
  });
});

describe('symbolLanes', () => {
  it('starts with held symbols and places marks across the range', () => {
    const lanes = symbolLanes(fills, T0, T0 + 4 * DAY, ['GLD']);
    assert.deepEqual(lanes.map((l) => l.symbol), ['GLD', 'TLT']);
    assert.equal(lanes[0].marks.length, 2);
    assert.equal(lanes[0].marks[1].side, 'sell');
    assert.ok(Math.abs(lanes[0].marks[1].x - 0.5) < 1e-6);
  });
  it('clamps to the lane and handles an empty range', () => {
    assert.equal(laneX(-5, 0, 10), 0);
    assert.equal(laneX(50, 0, 10), 1);
    assert.equal(laneX(5, 10, 10), 1);
  });
});

describe('mixOverTime', () => {
  const day = (n: number) => T0 - (T0 % 1) + n * DAY;
  const closes = {
    TLT: [0, 1, 2].map((n) => ({ t: day(n), close: 90 })),
    GLD: [0, 1, 2].map((n) => ({ t: day(n), close: n === 2 ? 210 : 200 })),
  };
  const mix = mixOverTime(20_000, fills, closes);
  it('rebuilds weights and cash from fills and closes', () => {
    assert.deepEqual(mix.symbols, ['TLT', 'GLD']);
    assert.equal(mix.days.length, 3);
    const d0 = mix.days[0];
    assert.ok(Math.abs(d0.value - 20_000) < 1e-6);
    assert.ok(Math.abs(d0.weights[0] - 0.45) < 1e-9);
    assert.ok(Math.abs(d0.weights[1] - 0.4) < 1e-9);
    assert.ok(Math.abs(d0.cash - 0.15) < 1e-9);
  });
  it('reads one day as before and after', () => {
    const change = weightChange(mix, T0 + 2 * DAY);
    assert.equal(change.length, 2);
    assert.ok(change[1].after < change[1].before);
  });
  it('is empty without fills or capital', () => {
    assert.equal(mixOverTime(0, fills, closes).days.length, 0);
    assert.equal(mixOverTime(1000, [], closes).days.length, 0);
  });
});
