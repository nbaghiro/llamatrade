import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { describe, expect, it } from 'vitest';

import { backtestLine, holidayNote } from '../deployNotes';

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });
const run = (over: Record<string, unknown>) =>
  ({
    id: 'b',
    strategyId: 'dm',
    strategyVersion: 1,
    completedAt: ts('2026-11-01T00:00:00Z'),
    config: { startDate: ts('2016-01-04T00:00:00Z'), endDate: ts('2026-10-30T00:00:00Z') },
    results: { metrics: { annualizedReturn: { value: '0.081' }, maxDrawdown: { value: '0.196' } } },
    ...over,
  }) as unknown as BacktestRun;

describe('backtestLine', () => {
  it('describes the backtest of the version being started', () => {
    expect(backtestLine([run({})], 'dm', 1)).toBe(
      'Backtest of version 1, Jan 2016 to Oct 2026: 8.1% a year, largest drawdown −19.6%.'
    );
  });

  it('says when the version being started has no backtest', () => {
    expect(backtestLine([run({})], 'dm', 2)).toMatch(
      /^Backtest of version 1, .*Version 2 hasn't been backtested yet\.$/
    );
  });

  it('prefers the newest run of the same version', () => {
    const older = run({ id: 'a', completedAt: ts('2026-01-01T00:00:00Z') });
    const v2 = run({ id: 'c', strategyVersion: 2 });
    expect(backtestLine([older, v2, run({})], 'dm', 1)).toMatch(/^Backtest of version 1/);
  });

  it('is null without a completed run for the strategy', () => {
    expect(backtestLine([run({ results: undefined })], 'dm', 1)).toBeNull();
    expect(backtestLine([run({})], 'other', 1)).toBeNull();
  });
});

describe('holidayNote', () => {
  const utc = (s: string) => new Date(`${s}T00:00:00Z`);
  it('names the holiday that moved a first-of-period run', () => {
    expect(holidayNote(utc('2027-01-04'))).toBe(
      "Jan 1 is New Year's Day, so this one runs on Mon, Jan 4."
    );
    expect(holidayNote(utc('2026-09-08'))).toBe(
      'Sep 7 is Labor Day, so this one runs on Tue, Sep 8.'
    );
  });

  it('is null after an ordinary weekend', () => {
    expect(holidayNote(utc('2026-12-01'))).toBeNull();
    expect(holidayNote(utc('2026-11-02'))).toBeNull();
  });
});
