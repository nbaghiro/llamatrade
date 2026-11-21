import { describe, expect, it } from 'vitest';

import type { HoldingLane } from '../annotations';
import {
  defensiveKind,
  defensiveStretches,
  drawdownPhrase,
  durationPhrase,
  inStocksShare,
  joinWords,
  numberWord,
  switchSentence,
} from '../resultStory';

const d = (iso: string) => new Date(`${iso}T00:00:00Z`);
const lane = (symbol: string, spans: [string, string][]): HoldingLane => ({
  symbol,
  spans: spans.map(([a, b]) => ({ from: d(a), to: d(b) })),
  days: 0,
});

const dates = Array.from({ length: 10 }, (_, i) => d(`2024-01-${String(i + 1).padStart(2, '0')}`));
const lanes = [
  lane('VTI', [
    ['2024-01-01', '2024-01-04'],
    ['2024-01-08', '2024-01-11'],
  ]),
  lane('TLT', [['2024-01-04', '2024-01-08']]),
  lane('GLD', [['2024-01-05', '2024-01-08']]),
];

describe('defensive stretches', () => {
  it('classifies funds', () => {
    expect(defensiveKind('TLT')).toBe('bonds');
    expect(defensiveKind('GLD')).toBe('gold');
    expect(defensiveKind('QQQ')).toBeNull();
  });

  it('finds the days everything held was defensive', () => {
    const s = defensiveStretches(lanes, dates);
    expect(s).toEqual([{ from: d('2024-01-04'), to: d('2024-01-07'), symbols: ['GLD', 'TLT'] }]);
  });

  it('shares days with a stock fund held', () => {
    expect(inStocksShare(lanes, dates)).toBeCloseTo(0.6);
    expect(inStocksShare(lanes, [])).toBeNull();
  });
});

describe('wording', () => {
  it('spells small numbers and joins lists', () => {
    expect(numberWord(6)).toBe('six');
    expect(numberWord(14)).toBe('14');
    expect(joinWords(['bonds'])).toBe('bonds');
    expect(joinWords(['bonds', 'gold', 'cash'])).toBe('bonds, gold and cash');
  });

  it('describes durations', () => {
    expect(durationPhrase([31, 92])).toBe('for one to three months each time');
    expect(durationPhrase([3, 60])).toBe('for three days to two months each time');
    expect(durationPhrase([14])).toBe('for two weeks');
    expect(durationPhrase([])).toBe('');
  });

  it('writes the switch sentence', () => {
    expect(switchSentence(defensiveStretches(lanes, dates))).toBe(
      'It moved into bonds and gold once, for three days.'
    );
    expect(switchSentence([])).toBeNull();
  });

  it('compares drawdowns', () => {
    expect(drawdownPhrase(-0.118, -0.245, 'SPY')).toBe("less than half of SPY's worst drawdown");
    expect(drawdownPhrase(-0.2, -0.245, 'SPY')).toBe('a smaller worst drawdown than SPY');
    expect(drawdownPhrase(-0.24, -0.245, 'SPY')).toBe('about the same worst drawdown as SPY');
    expect(drawdownPhrase(-0.3, -0.245, 'SPY')).toBe('a deeper worst drawdown than SPY');
  });
});
