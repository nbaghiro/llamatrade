import {
  compact,
  dateShort,
  money,
  moneyShort,
  num,
  pct,
  qty,
  signedFraction,
  signedMoney,
  timeAgo,
} from '@llamatrade/core/format';
import { describe, it, expect } from 'vitest';


// Guards the P0 dedup that replaced the dashboard/strategyRow Intl formatters
// with these hand-rolled (Hermes-parity) equivalents.

describe('num', () => {
  it('parses proto Decimal strings and passes through numbers', () => {
    expect(num({ value: '102913.23' })).toBe(102913.23);
    expect(num(42)).toBe(42);
  });
  it('returns 0 for empty/undefined/non-finite (the guard the inline copies lacked)', () => {
    expect(num(undefined)).toBe(0);
    expect(num(null)).toBe(0);
    expect(num({ value: '' })).toBe(0);
    expect(num({ value: 'abc' })).toBe(0);
    expect(num(NaN)).toBe(0);
    expect(num(Infinity)).toBe(0);
  });
});

describe('money / signedMoney / moneyShort', () => {
  it('groups thousands and uses a typographic minus', () => {
    expect(money(1234)).toBe('$1,234');
    expect(money(102913, 0)).toBe('$102,913');
    expect(money(-50)).toBe('−$50');
    expect(money(1234.5, 2)).toBe('$1,234.50');
  });
  it('signedMoney always carries a leading sign', () => {
    expect(signedMoney(2603)).toBe('+$2,603');
    expect(signedMoney(-207)).toBe('−$207');
  });
  it('moneyShort renders compact dollars', () => {
    expect(moneyShort(0)).toBe('$0');
    expect(moneyShort(500)).toBe('$500');
    expect(moneyShort(1234)).toBe('$1.2k');
    expect(moneyShort(50000)).toBe('$50k');
  });
});

describe('qty', () => {
  it('groups and trims trailing zeros up to 2 decimals', () => {
    expect(qty(1234)).toBe('1,234');
    expect(qty(1234.5)).toBe('1,234.5');
    expect(qty(1234.567)).toBe('1,234.57');
    expect(qty(0)).toBe('0');
    expect(qty(-12.5)).toBe('−12.5');
  });
});

describe('pct / signedFraction', () => {
  it('pct formats an already-percent value with a forced sign', () => {
    expect(pct(3.06)).toBe('+3.06%');
    expect(pct(-0.24)).toBe('−0.24%');
  });
  it('signedFraction turns a fraction into a signed percent', () => {
    expect(signedFraction(0.124)).toBe('+12.4%');
    expect(signedFraction(-0.05)).toBe('−5.0%');
  });
});

describe('compact', () => {
  it('renders K/M/B/T magnitudes, trimming trailing zeros', () => {
    expect(compact(999)).toBe('999');
    expect(compact(1200)).toBe('1.2K');
    expect(compact(1_000_000)).toBe('1M');
    expect(compact(77_620_000)).toBe('77.62M');
    expect(compact(1_500_000_000)).toBe('1.5B');
  });
});

describe('dateShort / timeAgo', () => {
  it('dateShort renders a hand-rolled Mon D', () => {
    expect(dateShort(new Date(2026, 6, 16))).toBe('Jul 16');
    expect(dateShort(null)).toBe('');
  });
  it('timeAgo buckets recent times and falls back to a date past a week', () => {
    expect(timeAgo(null)).toBe('');
    expect(timeAgo(new Date(Date.now() - 30_000))).toBe('now');
    expect(timeAgo(new Date(Date.now() - 5 * 60_000))).toBe('5m');
    expect(timeAgo(new Date(Date.now() - 3 * 3_600_000))).toBe('3h');
    expect(timeAgo(new Date(Date.now() - 2 * 86_400_000))).toBe('2d');
    expect(timeAgo(new Date(2020, 0, 5))).toBe('Jan 5');
  });
});
