import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  compareSameDates,
  dailyCloses,
  gapLabel,
  listSummary,
  pickSameDatesRun,
  shortDate,
  sortNotRunning,
  stageLine,
  stageOf,
  valueAt,
  type SessionFact,
} from '../model.ts';
import { groupByCategory, templateMeta } from '../templates.ts';

const t = (s: string) => Date.parse(`${s}T16:00:00Z`);

const session = (over: Partial<SessionFact>): SessionFact => ({
  strategyId: 's1',
  state: 'running',
  mode: 'paper',
  startedAt: t('2026-06-02'),
  endedAt: null,
  ...over,
});

test('stageOf: an open session means running', () => {
  assert.deepEqual(stageOf('s1', [session({})], true), { kind: 'running' });
  assert.deepEqual(stageOf('s1', [session({ state: 'frozen' })], false), { kind: 'running' });
});

test('stageOf: a stopped session is stopped, never paused, with its end date', () => {
  const stage = stageOf('s1', [session({ state: 'stopped', endedAt: t('2026-11-12') })], true);
  assert.deepEqual(stage, { kind: 'stopped', at: t('2026-11-12'), mode: 'paper' });
  assert.equal(stageLine(stage, 2026), 'Stopped Nov 12');
});

test('stageOf: a backtest with no session is never run; neither is a draft', () => {
  assert.deepEqual(stageOf('s2', [session({})], true), { kind: 'neverRun' });
  assert.deepEqual(stageOf('s2', [], false), { kind: 'draft' });
  assert.equal(stageLine({ kind: 'neverRun' }), 'Never run');
});

test('stageOf picks the latest of several stopped sessions', () => {
  const stage = stageOf('s1', [
    session({ state: 'stopped', endedAt: t('2026-03-01') }),
    session({ state: 'stopped', endedAt: t('2026-11-12'), mode: 'live' }),
  ], true);
  assert.deepEqual(stage, { kind: 'stopped', at: t('2026-11-12'), mode: 'live' });
});

test('listSummary and shortDate', () => {
  assert.equal(listSummary(3, 4), '3 running · 4 not running');
  assert.equal(listSummary(0, 2), '2 not running');
  assert.equal(listSummary(1, 0), '1 running');
  assert.equal(listSummary(0, 0), '');
  assert.equal(shortDate(t('2025-11-12'), 2026), 'Nov 12, 2025');
});

test('sortNotRunning puts stopped first, then never run, then drafts', () => {
  const items = [
    { id: 'a', stage: { kind: 'draft' } as const },
    { id: 'b', stage: { kind: 'neverRun' } as const },
    { id: 'c', stage: { kind: 'stopped', at: null, mode: 'paper' } as const },
  ];
  assert.deepEqual(sortNotRunning(items).map((i) => i.id), ['c', 'b', 'a']);
});

test('dailyCloses keeps the last point of each day; valueAt finds on or before', () => {
  const pts = [
    { at: Date.parse('2026-06-02T14:00:00Z'), value: 1 },
    { at: Date.parse('2026-06-02T20:00:00Z'), value: 2 },
    { at: Date.parse('2026-06-03T20:00:00Z'), value: 3 },
  ];
  assert.deepEqual(dailyCloses(pts).map((p) => p.value), [2, 3]);
  assert.equal(valueAt(dailyCloses(pts), Date.parse('2026-06-02T23:00:00Z')), 2);
  assert.equal(valueAt(dailyCloses(pts), Date.parse('2026-06-01T00:00:00Z')), null);
});

test('compareSameDates rebases both from the first shared day', () => {
  const days = ['2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05', '2026-06-08', '2026-06-09'];
  const sessionPts = days.map((d, i) => ({ at: t(d), value: 100 + i }));
  const btPts = days.map((d, i) => ({ at: t(d), value: 200 + 4 * i }));
  const same = compareSameDates(sessionPts, btPts);
  assert.ok(same);
  assert.equal(same.dates.length, 6);
  assert.ok(Math.abs(same.session[5] - 0.05) < 1e-9);
  assert.ok(Math.abs(same.backtest[5] - 0.1) < 1e-9);
  assert.ok(Math.abs(same.backtestScaled[5] - 110) < 1e-9);
  assert.equal(compareSameDates(sessionPts.slice(0, 4), btPts), null);
});

test('pickSameDatesRun prefers the session version, then overlap, then newest', () => {
  const runs = [
    { id: 'old', completed: true, start: t('2026-01-01'), end: t('2026-11-01'), version: 2, createdAt: 1 },
    { id: 'v3', completed: true, start: t('2026-05-01'), end: t('2026-08-01'), version: 3, createdAt: 2 },
    { id: 'failed', completed: false, start: t('2026-01-01'), end: t('2026-11-01'), version: 3, createdAt: 3 },
  ];
  assert.equal(pickSameDatesRun(runs, t('2026-06-02'), t('2026-11-17'), 3)?.id, 'v3');
  assert.equal(pickSameDatesRun(runs, t('2026-06-02'), t('2026-11-17'), null)?.id, 'old');
  assert.equal(pickSameDatesRun(runs, t('2026-11-15'), t('2026-11-17'), 3), null);
});

test('gapLabel signs points', () => {
  assert.equal(gapLabel(12.4, 13.1), '−0.7 pts');
  assert.equal(gapLabel(5, 4), '+1.0 pts');
  assert.equal(gapLabel(5, 5.01), '0.0 pts');
});

test('groupByCategory orders by the enum and puts unknown categories last', () => {
  const groups = groupByCategory([
    { id: '1', name: 'Zeta', category: 5, difficulty: 3 },
    { id: '2', name: 'Alpha', category: 5, difficulty: 1 },
    { id: '3', name: 'Mystery', category: 42, difficulty: 0 },
    { id: '4', name: 'Classic', category: 1, difficulty: 1 },
  ]);
  assert.deepEqual(groups.map((g) => g.label), ['Buy and hold', 'Trend', 'Other']);
  assert.deepEqual(groups[1].templates.map((t) => t.name), ['Alpha', 'Zeta']);
  assert.equal(templateMeta({ category: 5, difficulty: 3 }), 'Trend · Advanced');
  assert.equal(templateMeta({ category: 0, difficulty: 0 }), '');
});
