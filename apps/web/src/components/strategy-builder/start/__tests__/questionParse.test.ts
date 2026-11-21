import { describe, expect, it } from 'vitest';

import { parseProseQuestions, readDraftQuestions, splitAlternatives } from '../questionParse';

describe('splitAlternatives', () => {
  it('splits comma and or lists', () => {
    expect(splitAlternatives('60% TLT and 40% GLD, equal, or by inverse volatility.')).toEqual([
      '60% TLT and 40% GLD',
      'equal',
      'by inverse volatility',
    ]);
    expect(splitAlternatives('RSI above 70 or RSI above 80?')).toEqual([
      'RSI above 70',
      'RSI above 80',
    ]);
  });

  it('keeps text without alternatives whole', () => {
    expect(splitAlternatives('VTI, QQQ, SMH and IWM')).toEqual(['VTI, QQQ, SMH and IWM']);
  });
});

describe('parseProseQuestions', () => {
  it('reads numbered questions with bullet options and a marked pick', () => {
    const reply = [
      'A few parts of this could mean more than one rule.',
      '',
      '1. **Which stock ETFs should it rank?**',
      '   - VTI QQQ SMH IWM',
      '   - Sector ETFs: XLK XLF XLI XLY XLV',
      '2. What should count as overbought?',
      '   RSI compares recent gains with recent losses.',
      '   - SPY over 10% above its 200-day average',
      "   - SPY's 14-day RSI above 70 (my pick)",
      '3) How should bonds and gold be split? 60% TLT and 40% GLD, equal, or by inverse volatility.',
    ].join('\n');
    const ask = parseProseQuestions(reply);
    expect(ask?.intro).toBe('A few parts of this could mean more than one rule.');
    expect(ask?.questions.map((q) => q.label)).toEqual([
      'Which stock ETFs should it rank?',
      'What should count as overbought?',
      'How should bonds and gold be split?',
    ]);
    expect(ask?.questions[0].preset).toBe('VTI QQQ SMH IWM');
    expect(ask?.questions[1].preset).toBe("SPY's 14-day RSI above 70");
    expect(ask?.questions[1].help).toBe('RSI compares recent gains with recent losses');
    expect(ask?.questions[2].options).toEqual([
      '60% TLT and 40% GLD',
      'equal',
      'by inverse volatility',
    ]);
  });

  it('reads an "Options:" line and drops questions without two options', () => {
    const reply = [
      '1. How often should it rebalance?',
      'Options: monthly or quarterly',
      '2. Anything else you want?',
    ].join('\n');
    const ask = parseProseQuestions(reply);
    expect(ask?.questions).toHaveLength(1);
    expect(ask?.questions[0].options).toEqual(['monthly', 'quarterly']);
  });

  it('returns null for a reply with no questions', () => {
    expect(parseProseQuestions('Here is the draft. It holds SPY.')).toBeNull();
    expect(parseProseQuestions('')).toBeNull();
  });
});

describe('readDraftQuestions', () => {
  it('prefers the structured block when there is one', () => {
    const reply = [
      'Two things to check.',
      '```draft-questions',
      '{"questions":[{"id":"top","label":"How many to hold?","options":["2","3"],"default":"3"}]}',
      '```',
    ].join('\n');
    const ask = readDraftQuestions(reply);
    expect(ask?.questions[0]).toMatchObject({ id: 'top', preset: '3' });
  });

  it('falls back to prose', () => {
    expect(readDraftQuestions('1. Which? A or B')?.questions[0].options).toEqual(['A', 'B']);
  });
});
