import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { describe, expect, it } from 'vitest';

import { codeFragments } from '../rules/codeFragments';
import {
  OUTLINE_FIRST_RULES,
  ruleSentence,
  sentenceText,
  summaryParts,
  type SentenceTerm,
} from '../rules/ruleSentence';

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
        (weight :method equal
          (asset VTI)
          (asset QQQ)
          (asset IWM))))))`;

const SECTORS = `(strategy "Momentum Sectors"
  :rebalance weekly
  :benchmark SPY
  (filter :by momentum :select (top 3) :lookback 90
    (weight :method equal
      (asset XLK) (asset XLC) (asset XLY) (asset XLF) (asset XLI))))`;

const NESTED = `(strategy "Nested"
  :rebalance daily
  :benchmark SPY
  (if (< (price SPY) (sma SPY 200))
    (asset SHY)
    (else
      (if (> (rsi QQQ 14) 50)
        (asset QQQ)
        (else
          (asset IWM))))))`;

const parse = (code: string) => {
  const p = fromDSLString(code);
  if (!p) throw new Error('parse failed');
  return p;
};
const terms = (parts: ReturnType<typeof ruleSentence>['parts']) =>
  parts.filter((p): p is SentenceTerm => p.kind === 'term');

describe('ruleSentence', () => {
  it('reads a single if/else as one sentence with the values as terms', () => {
    const p = parse(RADAR);
    const s = ruleSentence(p.tree, p.metadata.timeframe ?? '1M');
    expect(sentenceText(s.parts)).toBe(
      "On the first trading day of each month, if SPY's 14-day RSI is above 70, hold TLT at 60% and GLD at 40%. Otherwise, hold VTI, QQQ and IWM in equal weights."
    );
    const t = terms(s.parts);
    expect(t.map((x) => x.text)).toEqual([
      'On the first trading day of each month',
      "SPY's 14-day RSI",
      '70',
      'TLT at 60%',
      'GLD at 40%',
      'VTI, QQQ and IWM',
    ]);
    const threshold = t[2].target;
    expect(threshold.kind).toBe('condition');
    if (threshold.kind === 'condition') {
      expect(threshold.part).toBe('threshold');
      expect(threshold.rule).toBe(1);
    }
    expect(new Set(t.map((x) => x.id)).size).toBe(t.length);
    expect(s.outlineFirst).toBe(false);
  });

  it('folds a long list of funds into a count and names the ranking', () => {
    const p = parse(SECTORS);
    const s = ruleSentence(p.tree, p.metadata.timeframe ?? '1W');
    expect(sentenceText(s.parts)).toBe(
      'Each week, hold the top 3 of 5 funds ranked by 90-day return.'
    );
    const fold = terms(s.parts).find((x) => x.text === '5 funds');
    expect(fold?.target.kind).toBe('fold');
    if (fold?.target.kind === 'fold') {
      expect(fold.target.rules.map((r) => r.text)).toEqual(['XLK', 'XLC', 'XLY', 'XLF', 'XLI']);
    }
  });

  it('folds a nested rule into a clickable summary instead of spelling it out', () => {
    const p = parse(NESTED);
    const s = ruleSentence(p.tree, p.metadata.timeframe ?? '1D');
    expect(sentenceText(s.parts)).toBe(
      'Each trading day, if SPY is below its 200-day average, hold SHY. Otherwise, follow 3 rules.'
    );
    const fold = terms(s.parts).find((x) => x.target.kind === 'fold');
    expect(fold?.target.kind === 'fold' && fold.target.rules.map((r) => r.number)).toEqual([
      2, 3, 4,
    ]);
  });

  it('opens in outline past the rule limit', () => {
    const many = Array.from(
      { length: OUTLINE_FIRST_RULES },
      (_, i) => `(if (> (rsi SPY 14) ${50 + i}) (asset SPY) (else (asset BIL)))`
    ).join(' ');
    const p = parse(`(strategy "Many" :rebalance daily :benchmark SPY (group "All" ${many}))`);
    const s = ruleSentence(p.tree, '1D');
    expect(s.ruleCount).toBeGreaterThan(OUTLINE_FIRST_RULES);
    expect(s.outlineFirst).toBe(true);
    expect(sentenceText(s.parts).length).toBeLessThan(80);
  });

  it('drops the rebalance lead for a summary line', () => {
    const p = parse(RADAR);
    const s = ruleSentence(p.tree, '1M');
    expect(sentenceText(summaryParts(s)).startsWith("if SPY's 14-day RSI")).toBe(true);
  });

  it('says so when there is nothing to hold', () => {
    const p = parse('(strategy "Empty" :rebalance daily :benchmark SPY (group "None"))');
    expect(sentenceText(ruleSentence(p.tree, '1D').parts)).toMatch(/hold/);
  });
});

describe('codeFragments', () => {
  it('maps each block to the head of its written form', () => {
    const p = parse(RADAR);
    const frags = codeFragments(RADAR, p.tree);
    const values = [...frags.values()];
    expect(values).toContain('(if (> (rsi SPY 14) 70) …)');
    expect(values).toContain('(asset TLT :weight 60)');
    expect(values).toContain('(weight :method equal …)');
  });

  it('returns nothing when the code and tree disagree', () => {
    const p = parse(RADAR);
    expect(codeFragments('(strategy "x")', p.tree).size).toBe(0);
  });
});
