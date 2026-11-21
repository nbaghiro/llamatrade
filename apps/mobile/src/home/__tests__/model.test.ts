import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  accountSplit,
  attentionItems,
  blendEquity,
  cadenceOf,
  closedRecap,
  displayName,
  fillsOn,
  homeMode,
  isQuiet,
  moneyAdded,
  nextRebalance,
  periodStart,
  plannedRebalances,
  sessionLanes,
  sessionRows,
  startsNewPeriod,
  timeline,
  todayMove,
  type FillIn,
  type SessionIn,
} from '../model.ts';

const DAY = 86_400_000;
/** Tuesday, November 17 2026, 10:42 local. */
const NOW = new Date(2026, 10, 17, 10, 42).getTime();

function session(over: Partial<SessionIn>): SessionIn {
  return {
    id: 'e1',
    strategyId: 's1',
    sessionId: 'ts1',
    sleeveId: null,
    name: 'Recession Radar (paper)',
    mode: 'paper',
    state: 'running',
    value: 31904.2,
    dayReturnPct: 0.62,
    allocated: 28000,
    equity: [],
    startedAt: new Date(2026, 5, 2).getTime(),
    endedAt: null,
    rebalance: 'monthly',
    ...over,
  };
}

function fill(over: Partial<FillIn>): FillIn {
  return { id: 'f1', t: NOW - 3600_000, symbol: 'TLT', side: 'buy', qty: 42, price: 90.41, strategyId: 's1', sessionId: 'ts1', ...over };
}

describe('names and moves', () => {
  it('drops the mode suffix', () => {
    assert.equal(displayName('Recession Radar (paper)'), 'Recession Radar');
    assert.equal(displayName('All-Weather Portfolio'), 'All-Weather Portfolio');
  });

  it('works out the dollar move from a percent', () => {
    const move = todayMove(31904.2, 0.62);
    assert.ok(move !== null && Math.abs(move - 196.6) < 0.1);
    assert.equal(todayMove(null, 1), null);
    assert.equal(todayMove(100, -100), null);
  });

  it('keeps moves under 0.25% quiet', () => {
    assert.equal(isQuiet(0.2), true);
    assert.equal(isQuiet(-0.31), false);
    assert.equal(isQuiet(null), true);
  });

  it('reads cadences', () => {
    assert.equal(cadenceOf(' Monthly '), 'monthly');
    assert.equal(cadenceOf('yearly'), 'annually');
    assert.equal(cadenceOf('on signal'), null);
  });
});

describe('sessionRows', () => {
  it('puts attention first and stopped last, with no move for stopped', () => {
    const rows = sessionRows([
      session({ id: 'a', name: 'Tech Momentum Rotation', state: 'stopped', value: 26173.3 }),
      session({ id: 'b', value: 10 }),
      session({ id: 'c', state: 'frozen', value: 5 }),
      session({ id: 'd', value: 50 }),
    ]);
    assert.deepEqual(
      rows.map((r) => r.id),
      ['c', 'd', 'b', 'a'],
    );
    assert.equal(rows[3].today, null);
  });
});

describe('accountSplit', () => {
  it('adds each account its cash', () => {
    const split = accountSplit(
      [session({ mode: 'live', value: 48000 }), session({ value: 30000 }), session({ value: 0, state: 'stopped' })],
      2000,
      210,
    );
    assert.deepEqual(split, { live: 48210, paper: 32000, liveKnown: true, total: 80210 });
  });

  it('flags a live figure without live cash', () => {
    assert.equal(accountSplit([session({ mode: 'live', value: 1 })], 0, null).liveKnown, false);
    assert.equal(accountSplit([session({})], null, null).liveKnown, true);
  });
});

describe('blendEquity', () => {
  it('sums series on every timestamp and carries values forward', () => {
    const out = blendEquity([
      [
        { t: 1, v: 10 },
        { t: 3, v: 12 },
      ],
      [
        { t: 2, v: 5 },
        { t: 3, v: 6 },
      ],
    ]);
    assert.deepEqual(out, [
      { t: 1, v: 10 },
      { t: 2, v: 15 },
      { t: 3, v: 18 },
    ]);
  });

  it('counts a baseline before a series starts', () => {
    const out = blendEquity(
      [
        [
          { t: 1, v: 10 },
          { t: 2, v: 11 },
        ],
        [{ t: 2, v: 6 }],
      ],
      [10, 5],
    );
    assert.deepEqual(out, [
      { t: 1, v: 15 },
      { t: 2, v: 17 },
    ]);
  });
});

describe('periodStart', () => {
  it('is null for All', () => {
    assert.equal(periodStart('All', NOW), null);
    assert.equal(periodStart('1M', NOW), NOW - 31 * DAY);
  });
});

describe('schedule', () => {
  it('follows the runtime period rule', () => {
    const mon = new Date(2026, 10, 16);
    const tue = new Date(2026, 10, 17);
    assert.equal(startsNewPeriod(tue, mon, 'weekly'), false);
    assert.equal(startsNewPeriod(new Date(2026, 10, 23), mon, 'weekly'), true);
    assert.equal(startsNewPeriod(tue, tue, 'daily'), false);
    assert.equal(startsNewPeriod(new Date(2027, 0, 4), new Date(2026, 11, 1), 'quarterly'), true);
  });

  it('finds the first weekday of the next month after a rebalance this month', () => {
    const day = nextRebalance('monthly', new Date(2026, 10, 2).getTime(), NOW);
    assert.equal(day, new Date(2026, 11, 1).getTime());
  });

  it('is today when the period has turned and nothing traded yet', () => {
    assert.equal(nextRebalance('monthly', new Date(2026, 9, 1).getTime(), NOW), new Date(2026, 10, 17).getTime());
  });

  it('skips the weekend for weekly', () => {
    const sat = new Date(2026, 10, 21, 9).getTime();
    assert.equal(nextRebalance('weekly', new Date(2026, 10, 16).getTime(), sat), new Date(2026, 10, 23).getTime());
  });

  it('plans two weeks ahead and ignores stopped sessions', () => {
    const planned = plannedRebalances(
      [
        session({ id: 'w', strategyId: 'sw', sessionId: 'tw', name: 'Momentum Sectors', rebalance: 'weekly' }),
        session({ id: 'x', state: 'stopped', rebalance: 'daily' }),
        session({ id: 'm', rebalance: 'monthly' }),
      ],
      [fill({ strategyId: 'sw', sessionId: 'tw', t: new Date(2026, 10, 16, 15).getTime() }), fill({ t: new Date(2026, 10, 2, 15).getTime() })],
      NOW,
    );
    assert.deepEqual(
      planned.map((p) => [p.sessionId, new Date(p.day).getDate()]),
      [
        ['w', 23],
        ['w', 30],
        ['m', 1],
      ],
    );
  });
});

describe('timeline', () => {
  it('orders today, Now, then planned', () => {
    const out = timeline(
      [fill({ id: 'b', t: NOW - 600_000 }), fill({ id: 'a', t: NOW - 3600_000 }), fill({ id: 'old', t: NOW - 2 * DAY })],
      [{ sessionId: 'e1', name: 'Recession Radar', mode: 'paper', cadence: 'monthly', day: new Date(2026, 11, 1).getTime() }],
      [session({})],
      NOW,
    );
    assert.deepEqual(
      out.map((e) => e.key),
      ['a', 'b', 'now', 'e1-' + new Date(2026, 11, 1).getTime()],
    );
    const first = out[0];
    assert.ok(first.kind === 'fill' && first.session === 'Recession Radar' && first.mode === 'paper');
  });
});

describe('lanes and fills', () => {
  it('groups fills by day and ends stopped lanes', () => {
    const lanes = sessionLanes(
      [
        session({ id: 'live', mode: 'live', strategyId: 'sl', sessionId: 'tl' }),
        session({ id: 'stop', state: 'stopped', strategyId: 'ss', sessionId: 'ts', endedAt: 5 }),
      ],
      [fill({ strategyId: 'sl', sessionId: 'tl' }), fill({ id: 'f2', strategyId: 'sl', sessionId: 'tl' })],
      [],
    );
    assert.equal(lanes[0].key, 'live');
    assert.equal(lanes[0].fillDays[0].count, 2);
    assert.equal(lanes[1].end, 5);
  });

  it('lists one day of fills for one session', () => {
    const fills = [fill({}), fill({ id: 'f2', sessionId: 'other', strategyId: 'other' }), fill({ id: 'f3', t: NOW - 2 * DAY })];
    assert.equal(fillsOn(fills, NOW).length, 2);
    assert.equal(fillsOn(fills, NOW, { sessionId: 'ts1', strategyId: 's1' }).length, 1);
  });
});

describe('attentionItems', () => {
  it('lists frozen sleeves before rejected orders, newest first', () => {
    const items = attentionItems(
      [{ id: 'sl', name: 'Momentum Sectors (paper)', executionId: 'e' }],
      [
        { id: 'o1', symbol: 'SMH', side: 'buy', quantity: 4, message: '', t: 1, sessionId: 's' },
        { id: 'o2', symbol: 'TLT', side: 'sell', quantity: 2.5, message: 'Over the limit', t: 2, sessionId: 's' },
      ],
    );
    assert.deepEqual(
      items.map((i) => i.key),
      ['f-sl', 'r-o2', 'r-o1'],
    );
    assert.equal(items[0].title, 'Momentum Sectors is frozen.');
    assert.equal(items[1].title, 'Order rejected: sell 2.50 TLT.');
    assert.equal(attentionItems(null, null).length, 0);
  });
});

describe('homeMode and recap', () => {
  it('picks the page state', () => {
    assert.equal(homeMode({ loaded: false, strategyCount: 0, sessionCount: 0, marketOpen: true }), 'loading');
    assert.equal(homeMode({ loaded: true, strategyCount: 0, sessionCount: 0, marketOpen: true }), 'first');
    assert.equal(homeMode({ loaded: true, strategyCount: 3, sessionCount: 2, marketOpen: false }), 'closed');
    assert.equal(homeMode({ loaded: true, strategyCount: null, sessionCount: 2, marketOpen: null }), 'open');
  });

  it('ranks what each running session added', () => {
    const recap = closedRecap([session({ id: 'a', dayReturnPct: 1 }), session({ id: 'b', dayReturnPct: 2 }), session({ id: 'c', state: 'stopped' })]);
    assert.deepEqual(
      recap.map((r) => r.id),
      ['b', 'a'],
    );
  });
});

describe('moneyAdded', () => {
  it('accumulates deposits and withdrawals by date', () => {
    assert.deepEqual(
      moneyAdded([
        { t: 2, signed: -100 },
        { t: 1, signed: 1000 },
        { t: 3, signed: 0 },
      ]),
      [
        { t: 1, v: 1000 },
        { t: 2, v: 900 },
      ],
    );
  });
});
