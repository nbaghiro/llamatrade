import assert from 'node:assert/strict';
import { test } from 'node:test';

import { indicatorSeries, rsi, sma, ema, thresholdCounts } from '../indicators.ts';
import { changeSummary, changesBetween, formatValue, readStrategy, replaceValue, stepValue, type Piece } from '../sentences.ts';
import { children, headOf, keyword, readCode } from '../sexpr.ts';

const RADAR = `(strategy "Recession Radar"
  :rebalance monthly
  :benchmark SPY
  (if (> (rsi SPY 14) 70)
    (group "Defensive"
      (weight :method specified
        (asset TLT :weight 60)
        (asset GLD :weight 40)))
    (else
      (group "Risk on"
        (filter :by momentum :select (top 2) :lookback 90
          (weight :method equal
            (asset VTI)
            (asset QQQ)
            (asset IWM)))))))`;

const words = (pieces: Piece[]) => pieces.map((p) => (p.t === 'value' ? `[${p.value.text}]${p.value.suffix}` : p.text)).join('');

test('readCode keeps positions and handles comments and strings', () => {
  const [form] = readCode('(a "x \\" y" ; note\n (b 1))');
  assert.equal(form.kind, 'list');
  if (form.kind !== 'list') return;
  assert.equal(headOf(form), 'a');
  assert.equal(form.items[1].kind === 'string' && form.items[1].text, 'x " y');
  assert.equal(form.items.length, 3);
  const b = form.items[2];
  assert.equal(headOf(b), 'b');
  assert.equal(form.end, '(a "x \\" y" ; note\n (b 1))'.length);
});

test('readCode tolerates unclosed code', () => {
  const [form] = readCode('(strategy "A" (weight');
  assert.equal(form.kind === 'list' && form.items.length, 3);
});

test('keyword and children skip keyword pairs', () => {
  const [form] = readCode('(weight :method equal (asset A) (asset B))');
  if (form.kind !== 'list') throw new Error('not a list');
  assert.equal(keyword(form, 'method')?.kind === 'atom' && (keyword(form, 'method') as { text: string }).text, 'equal');
  assert.equal(children(form).length, 2);
});

test('readStrategy reads Recession Radar as sentences', () => {
  const read = readStrategy(RADAR);
  assert.ok(read);
  assert.equal(read.name, 'Recession Radar');
  assert.deepEqual(read.sentences.map(words), [
    'Rebalances [monthly] against SPY.',
    "When SPY's [14]-day RSI is above [70], hold TLT [60]% and GLD [40]%.",
    'Otherwise hold the top [2] of VTI, QQQ and IWM by momentum over [90] days.',
  ]);
  assert.deepEqual(read.symbols.sort(), ['GLD', 'IWM', 'QQQ', 'SPY', 'TLT', 'VTI']);
});

test('threshold values know the indicator they are compared with', () => {
  const read = readStrategy(RADAR);
  assert.ok(read);
  const threshold = read.values.find((v) => v.label === 'RSI threshold');
  assert.ok(threshold);
  assert.deepEqual(threshold.against, { name: 'rsi', symbol: 'SPY', period: 14 });
  assert.equal(threshold.min, 0);
  assert.equal(threshold.max, 100);
  assert.equal(read.values[0].kind, 'choice');
  assert.equal(read.values[0].label, 'Rebalance');
});

test('replaceValue edits one value and keeps the rest of the code', () => {
  const read = readStrategy(RADAR);
  assert.ok(read);
  const threshold = read.values.find((v) => v.label === 'RSI threshold');
  assert.ok(threshold);
  const next = replaceValue(RADAR, threshold, '72');
  assert.ok(next.includes('(> (rsi SPY 14) 72)'));
  assert.equal(next.length, RADAR.length);
  const again = readStrategy(next);
  assert.ok(again);
  const changes = changesBetween(read.values, again.values);
  assert.deepEqual(changes, [{ label: 'RSI threshold', from: '70', to: '72' }]);
  assert.equal(changeSummary(changes), 'RSI threshold 70 to 72');
});

test('other block shapes read plainly', () => {
  const parity = readStrategy('(strategy "Risk Parity" :rebalance monthly :benchmark SPY (weight :method inverse-volatility :lookback 60 (asset SPY) (asset TLT)))');
  assert.ok(parity);
  assert.deepEqual(parity.sentences.map(words), ['Rebalances [monthly] against SPY.', 'Hold SPY and TLT weighted by inverse volatility over [60] days.']);
  const pullback = readStrategy('(strategy "P" (if (< (rsi SPY 5) 25) (asset SPY) (else (asset BIL))))');
  assert.ok(pullback);
  assert.deepEqual(pullback.sentences.map(words), ["When SPY's [5]-day RSI is below [25], hold SPY.", 'Otherwise hold BIL.']);
  const many = readStrategy('(strategy "M" (filter :by momentum :select (top 3) :lookback 90 (weight :method equal (asset A) (asset B) (asset C) (asset D) (asset E) (asset F))))');
  assert.ok(many);
  assert.equal(words(many.sentences[0]), 'Hold the top [3] of A, B, C, D and 2 more by momentum over [90] days.');
  assert.equal(many.symbols.length, 6);
});

test('readStrategy returns null for code that is not a strategy', () => {
  assert.equal(readStrategy('(weight :method equal)'), null);
  assert.equal(readStrategy(''), null);
});

test('stepValue clamps and formatValue trims', () => {
  const v = { min: 0, max: 100, step: 1 };
  assert.equal(stepValue(v, 70, 1), 71);
  assert.equal(stepValue(v, 100, 1), 100);
  assert.equal(stepValue(v, 0, -1), 0);
  assert.equal(stepValue({ min: 0, max: 10, step: 0.5 }, 7.5, 1), 8);
  assert.equal(formatValue(72, 1), '72');
  assert.equal(formatValue(7.5, 0.5), '7.5');
  assert.equal(formatValue(8, 0.5), '8');
});

test('rsi is 100 on a rising series and 50 on a flat one', () => {
  const rising = Array.from({ length: 20 }, (_, i) => 100 + i);
  const r = rsi(rising, 14);
  assert.equal(r[13], null);
  assert.equal(r[14], 100);
  const flat = rsi(Array.from({ length: 20 }, () => 5), 14);
  assert.equal(flat[19], 50);
  assert.deepEqual(rsi([1, 2], 14), [null, null]);
});

test('rsi matches a hand-worked value', () => {
  const r = rsi([1, 2, 1, 2], 2);
  assert.equal(r[2], 50);
  assert.ok(Math.abs((r[3] ?? 0) - 75) < 1e-9);
});

test('sma and ema', () => {
  assert.deepEqual(sma([1, 2, 3, 4], 2), [null, 1.5, 2.5, 3.5]);
  const e = ema([1, 2, 3, 4], 2);
  assert.equal(e[1], 1.5);
  assert.ok(Math.abs((e[3] ?? 0) - (4 * (2 / 3) + (3 * (2 / 3) + 1.5 / 3) / 3)) < 1e-9);
  assert.equal(indicatorSeries('volatility', [1, 2], 2), null);
  assert.deepEqual(indicatorSeries('price', [1, 2], null), [1, 2]);
});

test('thresholdCounts counts days above and upward crossings', () => {
  assert.deepEqual(thresholdCounts([null, 60, 75, 65, 80, 81], 70), { above: 3, crossings: 2, days: 5 });
});
