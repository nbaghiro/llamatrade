import { create } from '@bufbuild/protobuf';
import { BacktestRunSchema } from '@llamatrade/core/proto/backtest_pb';
import { describe, expect, it } from 'vitest';

import type { TradeInput } from '../../../lib/backtestView';
import {
  changedLines,
  compareSettings,
  endGap,
  monthsHeldDifferently,
  orderCount,
  stretchMonths,
  symbolList,
} from '../compareView';

const ts = (iso: string) => ({ seconds: BigInt(Date.parse(iso) / 1000), nanos: 0 });
const d = (iso: string) => new Date(`${iso}T00:00:00Z`);

const run = (over: { capital?: string; commission?: string; bench?: string } = {}) =>
  create(BacktestRunSchema, {
    config: {
      startDate: ts('2021-01-04T00:00:00Z'),
      endDate: ts('2026-10-30T00:00:00Z'),
      initialCapital: { value: over.capital ?? '25000' },
      commission: { value: over.commission ?? '1' },
      slippagePercent: { value: '0.05' },
      benchmarkSymbol: over.bench ?? 'SPY',
    },
  });

const trade = (entry: string, exit: string | null): TradeInput => ({
  symbol: 'QQQ',
  side: 'BUY',
  quantity: 1,
  entryPrice: 1,
  exitPrice: 1,
  entryTime: d(entry),
  exitTime: exit ? d(exit) : null,
  pnl: 0,
  entryReason: '',
  exitReason: '',
});

describe('compareView', () => {
  it('counts an order for each entry and each exit', () => {
    expect(orderCount([trade('2024-01-02', '2024-02-01'), trade('2024-03-01', null)])).toBe(3);
    expect(orderCount([])).toBe(0);
  });

  it('lists shared settings when they match', () => {
    const s = compareSettings(run(), run());
    expect(s.identical).toBe(true);
    expect(s.differences).toEqual([]);
    expect(s.shared).toEqual([
      'Jan 4, 2021 → Oct 30, 2026',
      '$25,000',
      '$1.00 per fill',
      '0.05% slippage',
      'against SPY',
    ]);
  });

  it('names each setting that differs', () => {
    const s = compareSettings(run(), run({ capital: '10000', bench: '' }));
    expect(s.identical).toBe(false);
    expect(s.differences).toEqual([
      'Capital $25,000 and $10,000',
      'Benchmark against SPY and no benchmark',
    ]);
  });

  it('counts months where the runs held different symbols', () => {
    const dates = [d('2024-01-02'), d('2024-01-20'), d('2024-02-05'), d('2024-03-04')];
    const a = [
      { symbol: 'QQQ', days: 10, spans: [{ from: d('2024-01-01'), to: d('2024-04-01') }] },
    ];
    const b = [
      { symbol: 'QQQ', days: 5, spans: [{ from: d('2024-01-01'), to: d('2024-01-15') }] },
      { symbol: 'TLT', days: 5, spans: [{ from: d('2024-01-15'), to: d('2024-02-01') }] },
      { symbol: 'QQQ', days: 5, spans: [{ from: d('2024-02-01'), to: d('2024-04-01') }] },
    ];
    expect(monthsHeldDifferently(dates, a, b)).toEqual({ differing: 1, total: 3 });
    expect(monthsHeldDifferently([], a, b)).toEqual({ differing: 0, total: 0 });
  });

  it('names a stretch by its months', () => {
    expect(stretchMonths(d('2023-02-03'), d('2023-05-20'))).toBe('Feb to May 2023');
    expect(stretchMonths(d('2022-11-03'), d('2023-02-20'))).toBe('Nov 2022 to Feb 2023');
    expect(stretchMonths(d('2023-02-03'), d('2023-02-20'))).toBe('Feb 2023');
  });

  it('keeps only changed, non-blank lines of the code', () => {
    const lines = changedLines('a\n(rsi 65)\nc\n', 'a\n(rsi 70)\nc\n\n');
    expect(lines?.map((l) => [l.kind, l.text])).toEqual([
      ['del', '(rsi 65)'],
      ['add', '(rsi 70)'],
    ]);
    expect(changedLines(null, 'a')).toBeNull();
    expect(changedLines('a', 'a')).toEqual([]);
  });

  it('says where the first run ended, level when the gap rounds to zero', () => {
    expect(endGap(0.047)).toEqual({ text: '4.7% ahead', tone: 'gain' });
    expect(endGap(-0.012)).toEqual({ text: '1.2% behind', tone: 'loss' });
    expect(endGap(0.0001)).toEqual({ text: 'level' });
    expect(endGap(Number.NaN)).toEqual({ text: 'level' });
  });

  it('lists symbols in a sentence', () => {
    expect(symbolList([])).toBe('');
    expect(symbolList(['QQQ'])).toBe('QQQ');
    expect(symbolList(['QQQ', 'VTI'])).toBe('QQQ and VTI');
    expect(symbolList(['GLD', 'IWM', 'QQQ'])).toBe('GLD, IWM and QQQ');
  });
});
