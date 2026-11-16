import { describe, expect, it } from 'vitest';

import { asSentence, formatMoney, formatNumber, formatPct, pnlTone } from '../format';

const MINUS = '−';

describe('formatMoney', () => {
  it('formats with grouping and two decimals', () => {
    expect(formatMoney(103410.27)).toBe('$103,410.27');
  });

  it('uses a true minus sign before the dollar sign', () => {
    expect(formatMoney(-84.12)).toBe(`${MINUS}$84.12`);
  });

  it('signs positive values on request only', () => {
    expect(formatMoney(895.4, { signed: true })).toBe('+$895.40');
    expect(formatMoney(895.4)).toBe('$895.40');
  });

  it('drops the sign when the value rounds to zero', () => {
    expect(formatMoney(-0.001, { signed: true })).toBe('$0.00');
    expect(formatMoney(0, { signed: true })).toBe('$0.00');
  });

  it('respects the decimal places', () => {
    expect(formatMoney(1234.5, { dp: 0 })).toBe('$1,235');
  });

  it('shows a dash for non-finite input', () => {
    expect(formatMoney(Number.NaN)).toBe('—');
    expect(formatMoney(Number.POSITIVE_INFINITY)).toBe('—');
  });
});

describe('formatPct', () => {
  it('treats input as a fraction', () => {
    expect(formatPct(0.0087)).toBe('0.87%');
    expect(formatPct(-0.214, { dp: 1, signed: true })).toBe(`${MINUS}21.4%`);
    expect(formatPct(0.214, { dp: 1, signed: true })).toBe('+21.4%');
  });

  it('does not sign a value that rounds to zero', () => {
    expect(formatPct(-0.00001, { signed: true })).toBe('0.00%');
  });
});

describe('formatNumber', () => {
  it('formats plain numbers', () => {
    expect(formatNumber(1234.567, { dp: 1 })).toBe('1,234.6');
    expect(formatNumber(-3, { dp: 0 })).toBe(`${MINUS}3`);
  });
});

describe('pnlTone', () => {
  it('classifies at display precision', () => {
    expect(pnlTone(1)).toBe('gain');
    expect(pnlTone(-1)).toBe('loss');
    expect(pnlTone(0)).toBe('flat');
    expect(pnlTone(-0.004)).toBe('flat');
    expect(pnlTone(0.004, 3)).toBe('gain');
    expect(pnlTone(Number.NaN)).toBe('flat');
  });
});

describe('asSentence', () => {
  it('closes a message with a full stop only when it needs one', () => {
    expect(asSentence('Position would exceed max size: $14,697.60 > $10,000.00')).toBe(
      'Position would exceed max size: $14,697.60 > $10,000.00.'
    );
    expect(asSentence('Market is closed. ')).toBe('Market is closed.');
    expect(asSentence('')).toBe('');
    expect(asSentence(undefined)).toBe('');
    expect(asSentence(null)).toBe('');
  });
});
