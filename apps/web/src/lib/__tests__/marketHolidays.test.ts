import { describe, expect, it } from 'vitest';

import {
  isTradingDay,
  marketDay,
  tradingDayOnOrAfter,
  tradingDaysBetween,
} from '../marketHolidays';

const d = (s: string) => new Date(`${s}T00:00:00Z`);

describe('marketDay', () => {
  it('closes for the rule-based holidays of 2026', () => {
    const closed = [
      ['2026-01-01', "New Year's Day"],
      ['2026-01-19', 'Martin Luther King Jr. Day'],
      ['2026-02-16', "Presidents' Day"],
      ['2026-04-03', 'Good Friday'],
      ['2026-05-25', 'Memorial Day'],
      ['2026-06-19', 'Juneteenth'],
      ['2026-07-03', 'Independence Day'],
      ['2026-09-07', 'Labor Day'],
      ['2026-11-26', 'Thanksgiving'],
      ['2026-12-25', 'Christmas'],
    ];
    for (const [day, name] of closed) {
      expect(marketDay(d(day))).toEqual({ closed: true, earlyClose: false, name });
    }
  });

  it('moves a Saturday holiday to Friday but not New Year onto the year before', () => {
    expect(marketDay(d('2027-12-24')).name).toBe('Christmas');
    expect(isTradingDay(d('2021-12-31'))).toBe(true);
  });

  it('marks early closes', () => {
    expect(marketDay(d('2026-11-27'))).toEqual({
      closed: false,
      earlyClose: true,
      name: 'Day after Thanksgiving',
    });
    expect(marketDay(d('2026-12-24')).earlyClose).toBe(true);
    expect(marketDay(d('2025-07-03')).earlyClose).toBe(true);
  });

  it('treats weekends as closed with no name', () => {
    expect(marketDay(d('2026-11-14'))).toEqual({ closed: true, earlyClose: false, name: null });
    expect(isTradingDay(d('2026-11-16'))).toBe(true);
  });
});

describe('trading day arithmetic', () => {
  it('rolls forward over weekends and holidays', () => {
    expect(tradingDayOnOrAfter(d('2026-11-26')).toISOString().slice(0, 10)).toBe('2026-11-27');
    expect(tradingDayOnOrAfter(d('2026-11-14')).toISOString().slice(0, 10)).toBe('2026-11-16');
    expect(tradingDayOnOrAfter(d('2026-11-16')).toISOString().slice(0, 10)).toBe('2026-11-16');
  });

  it('counts trading days after a start and up to an end', () => {
    expect(tradingDaysBetween(d('2026-11-20'), d('2026-11-27'))).toBe(4);
    expect(tradingDaysBetween(d('2026-11-16'), d('2026-11-16'))).toBe(0);
  });
});
