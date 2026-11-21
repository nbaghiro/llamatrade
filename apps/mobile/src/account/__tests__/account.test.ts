import assert from 'node:assert/strict';
import { test } from 'node:test';

import { accountHealth, healthSummary, problemText } from '../health.ts';
import { heldPeriods, holdingLanes, maxDrawdown, switchSentence, symbolsLabel } from '../firstResult.ts';
import { cellState, emailSummary, toggledPreferences, type Routing } from '../notificationModel.ts';
import { monthForecast, resetLabel, usageRow } from '../usage.ts';

const d = (s: string) => new Date(`${s}T12:00:00Z`);

test('health: rejected paper keys name the running paper sessions', () => {
  const h = accountHealth(
    [{ isPaper: true, isActive: true, apiKeyPrefix: 'PK1' }],
    { at: d('2026-11-17'), valid: false, isPaper: true, message: 'Unauthorized.' },
    [
      { name: 'Recession Radar', kind: 'paper', running: true, nextRun: null },
      { name: 'Momentum Sectors', kind: 'paper', running: true, nextRun: null },
      { name: 'Tech Momentum Rotation', kind: 'paper', running: false, nextRun: null },
    ],
  );
  assert.equal(h.problems.length, 1);
  const t = problemText(h.problems[0]);
  assert.equal(t.short, 'Paper keys rejected');
  assert.match(t.affects, /^Recession Radar and Momentum Sectors can't place orders/);
  assert.equal(healthSummary(h).tone, 'risk');
});

test('health: paper only reads as connected, with live not connected', () => {
  const h = accountHealth([{ isPaper: true, isActive: true, apiKeyPrefix: 'PK1' }], null, []);
  const s = healthSummary(h);
  assert.equal(s.tone, 'ok');
  assert.equal(s.title, 'Alpaca paper connected');
  assert.equal(healthSummary(accountHealth([], null, [])).tone, 'none');
});

test('first result: held periods, lanes and the switch sentence come from the trades', () => {
  const trades = [
    { symbol: 'SPY', entryTime: d('2024-11-01'), exitTime: d('2025-03-24') },
    { symbol: 'TLT', entryTime: d('2025-03-24'), exitTime: d('2025-08-11') },
    { symbol: 'GLD', entryTime: d('2025-03-24'), exitTime: d('2025-08-11') },
    { symbol: 'SPY', entryTime: d('2025-08-11'), exitTime: d('2026-02-09') },
    { symbol: 'TLT', entryTime: d('2026-02-09'), exitTime: null },
    { symbol: 'GLD', entryTime: d('2026-02-09'), exitTime: null },
  ];
  const periods = heldPeriods(trades, d('2026-10-30'));
  assert.deepEqual(periods.map((p) => p.key), ['SPY', 'GLD · TLT', 'SPY', 'GLD · TLT']);
  const lanes = holdingLanes(periods, d('2024-11-01'), d('2026-10-30'));
  assert.equal(lanes.length, 2);
  assert.equal(lanes.find((l) => l.key === 'SPY')?.spans.length, 2);
  assert.ok(lanes.every((l) => l.spans.every((s) => s.from >= 0 && s.to <= 1 && s.from < s.to)));
  assert.equal(switchSentence(periods), 'Switched into GLD and TLT twice: Mar 24, 2025 and Feb 9, 2026.');
  assert.equal(switchSentence(periods.slice(0, 1)), null);
});

test('first result: max drawdown and symbol labels', () => {
  assert.equal(maxDrawdown([100, 120, 90, 130]), -0.25);
  assert.equal(maxDrawdown([1, 2, 3]), 0);
  assert.equal(symbolsLabel(['BIL', 'BND', 'GLD', 'SPY', 'TLT']), 'BIL, BND, GLD and 2 more');
  assert.equal(symbolsLabel(['A', 'B', 'C']), 'A, B and C');
});

const R: Routing = {
  email: 1,
  webhook: 4,
  reach: new Map([
    [1, [1, 4]],
    [11, [4]],
    [14, [1, 4]],
    [27, [1, 4]],
  ]),
  alwaysEmail: new Set([1]),
};

test('notifications: locked, unavailable and toggled cells', () => {
  assert.equal(cellState(R, [], 1, 1), 'locked');
  assert.equal(cellState(R, [], 1, 11), 'unavailable');
  assert.equal(cellState(R, [], 4, 11), 'on');
  const off = toggledPreferences(R, [], 1, 14);
  assert.deepEqual(off.find((p) => p.channel === 1), { channel: 1, enabled: true, categories: [1, 27] });
  assert.equal(cellState(R, off, 1, 14), 'off');
  const back = toggledPreferences(R, off, 1, 14);
  assert.deepEqual(back.find((p) => p.channel === 1), { channel: 1, enabled: true, categories: [] });
});

test('notifications: email summary', () => {
  assert.equal(emailSummary(R, []), 'Email on');
  assert.equal(emailSummary(R, [{ channel: 1, enabled: false, categories: [] }]), 'Email off');
  assert.equal(emailSummary(R, [{ channel: 1, enabled: true, categories: [14] }]), 'Email for 1 of 2');
});

test('usage: forecast is arithmetic on the month so far', () => {
  const now = new Date(2026, 10, 17, 12, 0);
  assert.equal(monthForecast(0, now), null);
  assert.equal(monthForecast(5, new Date(2026, 10, 1, 9)), null);
  assert.equal(monthForecast(212, now), Math.round((212 / 16.5) * 30));
  const row = usageRow({ label: 'Backtests', used: 212, limit: 500, monthly: true }, now);
  assert.equal(row.figure, '212 of 500');
  assert.equal(row.forecastNote, 'About 385 by Nov 30');
  assert.ok(row.forecastFraction !== null && row.forecastFraction > row.fraction);
  assert.equal(row.willPass, false);
  const strat = usageRow({ label: 'Strategies', used: 6, limit: 10, monthly: false }, now);
  assert.equal(strat.forecastNote, null);
  assert.equal(usageRow({ label: 'Live', used: 0, limit: 0, monthly: false }, now).figure, 'Not included');
  assert.equal(resetLabel(now), 'Dec 1');
});

test('first result: rotation strategies get symbol lanes and a count', async () => {
  const { resultLanes, resultSentence } = await import('../firstResult.ts');
  const syms = ['XLB', 'XLE', 'XLF', 'XLI', 'XLK'];
  const periods = Array.from({ length: 12 }, (_, i) => ({
    key: `${syms[i % 5]} · XLY`,
    symbols: [syms[i % 5], 'XLY'],
    from: new Date(Date.UTC(2025, i, 1)),
    to: new Date(Date.UTC(2025, i + 1, 1)),
  }));
  const { lanes, bySymbol } = resultLanes(periods, new Date(Date.UTC(2025, 0, 1)), new Date(Date.UTC(2026, 0, 1)));
  assert.equal(bySymbol, true);
  assert.equal(lanes[0].key, 'XLY');
  assert.equal(lanes[0].spans.length, 1);
  assert.equal(resultSentence(periods), 'Changed its holdings 11 times over the run. The lanes show its most-held symbols.');
});
