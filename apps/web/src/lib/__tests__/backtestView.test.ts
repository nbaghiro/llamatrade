import { describe, expect, it } from 'vitest';

import {
  alignTo,
  asFrequency,
  commonRange,
  drawdownOf,
  figuresFromCurve,
  gridCellKey,
  groupRebalances,
  latestTradedMonth,
  monthLabel,
  monthlyReturnsFromMap,
  namesUsed,
  parseMonthHash,
  parseRunIds,
  partialFigures,
  rangeLabel,
  rebalancesInMonth,
  recoveryDays,
  runLog,
  scheduledRebalances,
  tradesToOrders,
  type ProgressEvent,
  type TradeInput,
} from '../backtestView';

const d = (s: string) => new Date(`${s}T00:00:00Z`);

const trade = (over: Partial<TradeInput>): TradeInput => ({
  symbol: 'VTI',
  side: 'BUY',
  quantity: 10,
  entryPrice: 100,
  exitPrice: 110,
  entryTime: d('2026-08-03'),
  exitTime: null,
  pnl: 0,
  entryReason: 'Defensive',
  exitReason: '',
  ...over,
});

describe('month helpers', () => {
  it('parses month hashes and rejects anything else', () => {
    expect(parseMonthHash('#month-2026-08')).toBe('2026-08');
    expect(parseMonthHash('month-2024-11')).toBe('2024-11');
    expect(parseMonthHash('#month-2026-13')).toBeNull();
    expect(parseMonthHash('#month-2026-8')).toBeNull();
    expect(parseMonthHash('')).toBeNull();
  });

  it('maps a month to its zero-based grid cell and a label', () => {
    expect(gridCellKey('2026-08')).toBe('2026-7');
    expect(gridCellKey('2025-01')).toBe('2025-0');
    expect(monthLabel('2026-08')).toBe('Aug 2026');
  });

  it('turns the monthly_returns map into sorted grid months and drops bad keys', () => {
    expect(
      monthlyReturnsFromMap({ '2025-02': 0.01, '2024-12': -0.02, bad: 0.3, '2025-01': NaN })
    ).toEqual([
      { y: 2024, m: 11, r: -0.02 },
      { y: 2025, m: 1, r: 0.01 },
    ]);
  });

  it('labels a range in words', () => {
    expect(rangeLabel(d('2024-11-01'), d('2026-10-30'))).toBe('Nov 1, 2024 to Oct 30, 2026');
  });
});

describe('month grouping', () => {
  const trades = [
    trade({ symbol: 'TLT', entryTime: d('2026-08-03'), entryReason: 'Defensive' }),
    trade({
      symbol: 'VTI',
      entryTime: d('2026-05-01'),
      exitTime: d('2026-08-03'),
      pnl: 691.82,
      entryReason: 'Momentum',
      exitReason: 'Defensive',
    }),
    trade({ symbol: 'GLD', entryTime: d('2026-08-03'), entryReason: 'Defensive' }),
    trade({ symbol: 'QQQ', entryTime: d('2026-09-01'), entryReason: '' }),
  ];

  it('splits round trips into entry and exit orders with the opposite side on exit', () => {
    const orders = tradesToOrders(trades);
    expect(orders).toHaveLength(5);
    const exit = orders.find((o) => o.symbol === 'VTI' && o.date === '2026-08-03');
    expect(exit).toMatchObject({ side: 'SELL', price: 110, value: 1100, pnl: 691.82 });
    const entry = orders.find((o) => o.symbol === 'VTI' && o.date === '2026-05-01');
    expect(entry).toMatchObject({ side: 'BUY', pnl: null, reason: 'Momentum' });
  });

  it('falls back to the entry reason when the exit has none', () => {
    const [, exit] = tradesToOrders([
      trade({ exitTime: d('2026-09-01'), entryReason: 'Else', exitReason: '  ' }),
    ]);
    expect(exit.reason).toBe('Else');
  });

  it('groups by day newest first, sells before buys, and sums realised P&L', () => {
    const rebs = groupRebalances(tradesToOrders(trades));
    expect(rebs.map((r) => r.date)).toEqual(['2026-09-01', '2026-08-03', '2026-05-01']);
    const aug = rebs[1];
    expect(aug.orders.map((o) => `${o.side} ${o.symbol}`)).toEqual([
      'SELL VTI',
      'BUY GLD',
      'BUY TLT',
    ]);
    expect(aug.branch).toBe('Defensive');
    expect(aug.realised).toBeCloseTo(691.82);
    expect(rebs[0].branch).toBe('');
  });

  it('filters a month and finds the newest traded month', () => {
    const rebs = groupRebalances(tradesToOrders(trades));
    expect(rebalancesInMonth(rebs, '2026-08')).toHaveLength(1);
    expect(rebalancesInMonth(rebs, '2026-07')).toEqual([]);
    expect(latestTradedMonth(rebs)).toBe('2026-09');
    expect(latestTradedMonth([])).toBeNull();
  });

  it('skips trades without times', () => {
    expect(tradesToOrders([trade({ entryTime: null })])).toEqual([]);
  });
});

describe('commonRange', () => {
  it('cuts every curve to the shared dates and rebases each to 1', () => {
    const a = {
      dates: ['01', '02', '03', '04'].map((x) => d(`2025-01-${x}`)),
      values: [100, 110, 121, 133.1],
    };
    const b = {
      dates: ['02', '03', '04', '05'].map((x) => d(`2025-01-${x}`)),
      values: [50, 55, 50, 60],
    };
    const r = commonRange([a, b]);
    expect(r).not.toBeNull();
    expect(r?.dates.map((x) => x.toISOString().slice(0, 10))).toEqual([
      '2025-01-02',
      '2025-01-03',
      '2025-01-04',
    ]);
    expect(r?.series[0]).toEqual([1, 1.1, 1.21]);
    expect(r?.series[1]).toEqual([1, 1.1, 1]);
    expect(r?.start.toISOString().slice(0, 10)).toBe('2025-01-02');
    expect(r?.end.toISOString().slice(0, 10)).toBe('2025-01-04');
  });

  it('ignores non-positive points and returns null with under two shared dates', () => {
    const a = { dates: [d('2025-01-01'), d('2025-01-02')], values: [100, 0] };
    const b = { dates: [d('2025-01-01'), d('2025-01-02')], values: [100, 101] };
    expect(commonRange([a, b])).toBeNull();
    expect(commonRange([])).toBeNull();
    expect(commonRange([{ dates: [d('2025-01-01')], values: [1] }, b])).toBeNull();
  });
});

describe('figures from a curve', () => {
  it('measures drawdown from the running peak', () => {
    expect(drawdownOf([100, 120, 90, 130])).toEqual([0, 0, -0.25, 0]);
  });

  it('computes total return, CAGR, drawdown and a zero-volatility edge case', () => {
    const f = figuresFromCurve([100, 120, 90, 130]);
    expect(f?.totalReturn).toBeCloseTo(0.3);
    expect(f?.maxDrawdown).toBeCloseTo(-0.25);
    expect(f?.cagr).toBeCloseTo(1.3 ** (252 / 3) - 1, 3);
    const flat = figuresFromCurve([100, 100, 100]);
    expect(flat).toMatchObject({ totalReturn: 0, sharpe: 0, volatility: 0, maxDrawdown: 0 });
    expect(figuresFromCurve([100])).toBeNull();
  });

  it('counts trading days from the deepest low back to the peak', () => {
    expect(recoveryDays([100, 90, 80, 95, 101])).toBe(2);
    expect(recoveryDays([100, 80, 90])).toBeNull();
    expect(recoveryDays([100, 101, 102])).toBe(0);
  });
});

describe('partial metrics', () => {
  it('reads decimals and makes drawdown negative', () => {
    expect(
      partialFigures({ totalReturn: '0.041', maxDrawdown: '0.123', benchmarkReturn: '' })
    ).toEqual({
      totalReturn: 0.041,
      maxDrawdown: -0.123,
      benchmarkReturn: null,
    });
  });

  it('leaves everything null when the stream sends no partial metrics', () => {
    expect(partialFigures(null)).toEqual({
      totalReturn: null,
      maxDrawdown: null,
      benchmarkReturn: null,
    });
    expect(partialFigures({ totalReturn: 'x' }).totalReturn).toBeNull();
  });
});

describe('runLog', () => {
  const ev = (over: Partial<ProgressEvent>): ProgressEvent => ({
    phase: 'running',
    percent: 50,
    currentDate: '',
    message: '',
    atMs: 1000,
    ...over,
  });

  it('shows only queued before the worker picks the run up', () => {
    expect(runLog([ev({ phase: 'pending', atMs: 0 })], 0)).toEqual([
      { at: 0, text: 'queued', tone: 'ok' },
    ]);
  });

  it('shows a live line with the latest replayed date while running', () => {
    const lines = runLog(
      [
        ev({ atMs: 300 }),
        ev({ currentDate: '2025-01-02', atMs: 900 }),
        ev({ currentDate: '2025-06-30', atMs: 2210 }),
      ],
      0
    );
    expect(lines.map((l) => l.text)).toEqual([
      'queued',
      'started on a worker',
      'replaying through 2025-06-30',
    ]);
    expect(lines[2]).toMatchObject({ at: 2.21, tone: 'now' });
  });

  it('closes with completed and the last replayed date', () => {
    const lines = runLog(
      [ev({ currentDate: '2026-10-30', atMs: 3500 }), ev({ phase: 'completed', atMs: 3800 })],
      0
    );
    expect(lines.map((l) => l.text)).toEqual([
      'queued',
      'started on a worker',
      'replayed through 2026-10-30',
      'completed',
    ]);
  });

  it('reports a failure with its message and a cancel as a note', () => {
    const failed = runLog([ev({ phase: 'failed', message: 'Unsupported weighting', atMs: 10 })], 0);
    expect(failed.map((l) => l.text)).toEqual(['queued', 'failed: Unsupported weighting']);
    expect(failed[1].tone).toBe('bad');
    const cancelled = runLog([ev({ atMs: 5 }), ev({ phase: 'cancelled', atMs: 9 })], 0);
    expect(cancelled[cancelled.length - 1]).toMatchObject({ text: 'cancelled', tone: 'note' });
  });
});

describe('scheduled rebalances', () => {
  it('counts monthly and quarterly schedules and how many have passed', () => {
    expect(
      scheduledRebalances(d('2024-11-01'), d('2026-10-30'), 'monthly', d('2026-01-14'))
    ).toEqual({
      total: 24,
      done: 15,
    });
    expect(scheduledRebalances(d('2024-11-01'), d('2026-10-30'), 'quarterly')).toEqual({
      total: 8,
      done: 0,
    });
    expect(
      scheduledRebalances(d('2024-11-01'), d('2026-10-30'), 'monthly', d('2030-01-01'))?.done
    ).toBe(24);
  });

  it('returns null for daily and weekly schedules or a reversed range', () => {
    expect(scheduledRebalances(d('2024-11-01'), d('2026-10-30'), 'daily')).toBeNull();
    expect(scheduledRebalances(d('2024-11-01'), d('2026-10-30'), null)).toBeNull();
    expect(scheduledRebalances(d('2026-11-01'), d('2024-10-30'), 'monthly')).toBeNull();
  });

  it('reads the strategy rebalance field', () => {
    expect(asFrequency(' Monthly ')).toBe('monthly');
    expect(asFrequency('hourly')).toBeNull();
    expect(asFrequency(undefined)).toBeNull();
  });
});

describe('names used and run ids', () => {
  it('finds called indicators in vocabulary order', () => {
    const dsl = '(if (> (rsi SPY 14) 70) (weight :method momentum (asset VTI)))';
    expect(namesUsed(dsl, ['momentum', 'rsi', 'sma'])).toEqual(['rsi']);
    expect(namesUsed('(williams-r SPY 14)', ['williams-r'])).toEqual(['williams-r']);
  });

  it('parses compare ids without blanks or repeats', () => {
    expect(parseRunIds('a, b,,a,c')).toEqual(['a', 'b', 'c']);
    expect(parseRunIds(null)).toEqual([]);
  });
});

describe('alignTo', () => {
  it('carries the last benchmark value over missing days and leaves the head empty', () => {
    const dates = ['01', '02', '03', '04'].map((x) => d(`2025-01-${x}`));
    const bench = { dates: [d('2025-01-02'), d('2025-01-04')], values: [10, 12] };
    expect(alignTo(dates, bench)).toEqual([null, 10, 10, 12]);
  });
});
