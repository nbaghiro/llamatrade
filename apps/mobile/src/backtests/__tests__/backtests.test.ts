import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  cagr,
  isoDay,
  lanesOf,
  presetRange,
  progressFraction,
  rebalanceCount,
  resultSentence,
  runTitle,
  splitRuns,
  totalReturn,
  worstStretch,
  type RunListItem,
} from '../model.ts';

const t = (s: string) => Date.parse(`${s}T00:00:00Z`);

test('totalReturn', () => {
  assert.equal(totalReturn([{ at: 1, value: 100 }, { at: 2, value: 150 }]), 0.5);
  assert.equal(totalReturn([{ at: 1, value: 100 }]), null);
  assert.equal(totalReturn([{ at: 1, value: 0 }, { at: 2, value: 1 }]), null);
});

test('worstStretch finds the deepest fall and its recovery', () => {
  const pts = [100, 110, 99, 105, 88, 112, 111].map((value, i) => ({ at: i, value }));
  const s = worstStretch(pts);
  assert.ok(s);
  assert.equal(s.from, 1);
  assert.equal(s.to, 4);
  assert.ok(Math.abs(s.depth - (88 / 110 - 1)) < 1e-12);
  assert.equal(s.recovered, 5);
  assert.equal(worstStretch([1, 2, 3].map((value, i) => ({ at: i, value }))), null);
  const never = worstStretch([10, 5, 6].map((value, i) => ({ at: i, value })));
  assert.equal(never?.recovered, null);
});

test('cagr over two years', () => {
  const g = cagr(0.21, t('2024-01-01'), t('2026-01-01'));
  assert.ok(g !== null && Math.abs(g - 0.1) < 0.001);
  assert.equal(cagr(0.1, t('2026-01-01'), t('2026-01-10')), null);
});

test('resultSentence compares with the benchmark', () => {
  assert.equal(
    resultSentence(0.712, 0.886, -0.118, -0.245, 'SPY'),
    '17.4 points less than SPY, with less than half of its worst drawdown.',
  );
  assert.equal(resultSentence(0.2, 0.1, -0.2, -0.1, 'SPY'), '10.0 points more than SPY, with a deeper worst drawdown.');
  assert.equal(resultSentence(0.2, 0.2, null, null, 'QQQ'), 'Level with QQQ.');
  assert.equal(resultSentence(0.2, null, -0.1, -0.2, 'SPY'), null);
});

test('presetRange and isoDay', () => {
  const today = t('2026-11-17');
  assert.equal(isoDay(presetRange('5Y', today).start), '2021-11-17');
  assert.equal(isoDay(presetRange('1Y', today).start), '2025-11-17');
  assert.equal(isoDay(presetRange('Max', today).start), '2016-11-17');
  assert.equal(isoDay(presetRange('Max', today, t('2019-03-01')).start), '2019-03-01');
});

test('rebalanceCount by cadence', () => {
  assert.equal(rebalanceCount('monthly', t('2021-01-04'), t('2026-10-30')), 69);
  assert.equal(rebalanceCount('quarterly', t('2021-01-04'), t('2022-01-04')), 4);
  assert.equal(rebalanceCount('weekly', t('2026-01-01'), t('2026-01-29')), 4);
  assert.equal(rebalanceCount('hourly', t('2026-01-01'), t('2026-01-29')), null);
  assert.equal(rebalanceCount('monthly', t('2026-01-01'), t('2025-01-01')), 0);
});

test('progressFraction clamps', () => {
  assert.equal(progressFraction(57), 0.57);
  assert.equal(progressFraction(140), 1);
  assert.equal(progressFraction(Number.NaN), 0);
});

test('splitRuns keeps running apart and picks the newest completed', () => {
  const run = (id: string, at: number, state: RunListItem['state']): RunListItem => ({ id, strategyId: 's', name: 'R', version: 1, at, ret: null, sharpe: null, state });
  const out = splitRuns([run('a', 1, 'completed'), run('b', 3, 'failed'), run('c', 4, 'running'), run('d', 2, 'completed')]);
  assert.deepEqual(out.running.map((r) => r.id), ['c']);
  assert.equal(out.latest?.id, 'd');
  assert.deepEqual(out.earlier.map((r) => r.id), ['b', 'a']);
  assert.equal(splitRuns([]).latest, null);
});

test('runTitle', () => {
  assert.equal(runTitle('Recession Radar', 3), 'Recession Radar v3');
  assert.equal(runTitle('Draft', 0), 'Draft');
});

test('lanesOf places spans across the run, longest held first', () => {
  const lanes = lanesOf(
    [
      { symbol: 'TLT', from: 10, to: 20 },
      { symbol: 'VTI', from: 0, to: 60 },
      { symbol: 'TLT', from: 70, to: 120 },
      { symbol: 'GLD', from: 200, to: 300 },
    ],
    0,
    100,
  );
  assert.deepEqual(lanes.map((l) => l.symbol), ['VTI', 'TLT']);
  assert.deepEqual(lanes[1].spans, [{ from: 0.1, to: 0.2 }, { from: 0.7, to: 1 }]);
  assert.deepEqual(lanesOf([], 5, 5), []);
});
