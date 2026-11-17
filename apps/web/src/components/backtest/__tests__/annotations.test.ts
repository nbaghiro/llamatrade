import { create } from '@bufbuild/protobuf';
import { BacktestRunSchema, BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { describe, expect, it } from 'vitest';

import type { TradeInput } from '../../../lib/backtestView';
import {
  differingStretches,
  foldLanes,
  heldStretches,
  holdingLanes,
  rebalanceMarks,
  scheduleDates,
  scheduleFor,
  stretchLabel,
  thinMarks,
  toLog,
  worstStretch,
} from '../annotations';
import { inFlight, strategyRows, timelineWindow } from '../historyTimeline';

const d = (iso: string) => new Date(`${iso}T00:00:00Z`);

function trade(symbol: string, entry: string, exit: string | null): TradeInput {
  return {
    symbol,
    side: 'BUY',
    quantity: 10,
    entryPrice: 100,
    exitPrice: 101,
    entryTime: d(entry),
    exitTime: exit ? d(exit) : null,
    pnl: 10,
    entryReason: '',
    exitReason: '',
  };
}

describe('holding lanes', () => {
  const start = d('2025-01-01');
  const end = d('2025-12-31');

  it('merges stretches a weekend apart and runs open trades to the end', () => {
    const lanes = holdingLanes(
      [
        trade('TLT', '2025-02-03', '2025-02-28'),
        trade('TLT', '2025-03-03', '2025-03-31'),
        trade('VTI', '2025-06-02', null),
      ],
      start,
      end
    );
    expect(lanes.map((l) => l.symbol)).toEqual(['VTI', 'TLT']);
    expect(lanes[1].spans).toHaveLength(1);
    expect(lanes[1].spans[0].to).toEqual(d('2025-03-31'));
    expect(lanes[0].spans[0].to).toEqual(end);
  });

  it('clips to the window and drops trades outside it', () => {
    const lanes = holdingLanes(
      [trade('GLD', '2024-11-01', '2025-01-15'), trade('QQQ', '2024-01-01', '2024-02-01')],
      start,
      end
    );
    expect(lanes.map((l) => l.symbol)).toEqual(['GLD']);
    expect(lanes[0].spans[0].from).toEqual(start);
  });

  it('ignores trades without an entry date', () => {
    expect(
      holdingLanes([{ ...trade('X', '2025-01-02', null), entryTime: null }], start, end)
    ).toEqual([]);
  });

  it('folds lanes past the limit into one', () => {
    const lanes = ['A', 'B', 'C', 'D'].map((symbol, i) => ({
      symbol,
      spans: [{ from: d(`2025-0${i + 1}-01`), to: d(`2025-0${i + 1}-10`) }],
      days: 10 - i,
    }));
    const folded = foldLanes(lanes, 3);
    expect(folded.map((l) => l.symbol)).toEqual(['A', 'B', '2 more']);
    expect(folded[2].spans).toHaveLength(2);
    expect(foldLanes(lanes, 4)).toHaveLength(4);
  });
});

describe('rebalance marks', () => {
  it('marks a switch only when the held symbols change', () => {
    const marks = rebalanceMarks([
      trade('VTI', '2025-01-02', '2025-02-03'),
      trade('VTI', '2025-02-03', '2025-03-03'),
      trade('TLT', '2025-03-03', null),
    ]);
    expect(marks.map((m) => [m.at.toISOString().slice(0, 10), m.switched, m.orders])).toEqual([
      ['2025-01-02', true, 1],
      ['2025-02-03', false, 2],
      ['2025-03-03', true, 2],
    ]);
  });

  it('combines marks that would overlap', () => {
    const marks = Array.from({ length: 10 }, (_, i) => ({
      at: d(`2025-01-${String(i + 1).padStart(2, '0')}`),
      switched: i === 3,
      orders: 1,
    }));
    const thin = thinMarks(marks, d('2025-01-01'), d('2025-01-10'), 2);
    expect(thin.thinned).toBe(true);
    expect(thin.marks).toHaveLength(2);
    expect(thin.marks[0].switched).toBe(true);
    expect(thin.marks.reduce((s, m) => s + m.orders, 0)).toBe(10);
    expect(thinMarks(marks, d('2025-01-01'), d('2025-01-10'), 20).thinned).toBe(false);
  });
});

describe('worst stretch', () => {
  const dates = ['01', '02', '03', '04', '05', '06'].map((x) => d(`2025-01-${x}`));

  it('finds the peak, trough and recovery', () => {
    const w = worstStretch(dates, [100, 110, 99, 88, 105, 111]);
    expect(w?.peak).toEqual(dates[1]);
    expect(w?.trough).toEqual(dates[3]);
    expect(w?.recovered).toEqual(dates[5]);
    expect(w?.depth).toBeCloseTo(-0.2);
    expect(stretchLabel(w as NonNullable<typeof w>)).toBe('−20.0% · Jan 2, 2025 to Jan 6, 2025');
  });

  it('says when it never recovered, and is null for a curve that only rises', () => {
    const w = worstStretch(dates, [100, 110, 99, 88, 90, 95]);
    expect(w?.recovered).toBeNull();
    expect(stretchLabel(w as NonNullable<typeof w>)).toContain('not recovered');
    expect(worstStretch(dates, [1, 2, 3, 4, 5, 6])).toBeNull();
    expect(worstStretch([], [])).toBeNull();
  });
});

describe('schedule and scale', () => {
  it('puts monthly rebalances on the first weekday of each month', () => {
    const dates = scheduleDates(d('2025-01-01'), d('2025-03-31'), 1).map((x) =>
      x.toISOString().slice(0, 10)
    );
    expect(dates).toEqual(['2025-01-01', '2025-02-03', '2025-03-03']);
    expect(scheduleDates(d('2025-01-01'), d('2024-01-01'), 1)).toEqual([]);
  });

  it('has no calendar schedule for daily or weekly runs', () => {
    expect(scheduleFor(d('2025-01-01'), d('2025-12-31'), 'quarterly')).toHaveLength(4);
    expect(scheduleFor(d('2025-01-01'), d('2025-12-31'), 'weekly')).toEqual([]);
    expect(scheduleFor(null, d('2025-12-31'), 'monthly')).toEqual([]);
  });

  it('breaks the log line at values it cannot take', () => {
    const out = toLog([Math.E, 0, -1]);
    expect(out[0]).toBeCloseTo(1);
    expect(Number.isNaN(out[1]) && Number.isNaN(out[2])).toBe(true);
  });
});

describe('history timeline', () => {
  const ts = (iso: string) => ({ seconds: BigInt(Date.parse(iso) / 1000), nanos: 0 });
  const run = (id: string, strategyId: string, at: string, status: BacktestStatus, v = 1) =>
    create(BacktestRunSchema, { id, strategyId, strategyVersion: v, status, createdAt: ts(at) });

  const runs = [
    run('a1', 'a', '2026-10-01T10:00:00Z', BacktestStatus.COMPLETED, 1),
    run('a2', 'a', '2026-11-01T10:00:00Z', BacktestStatus.FAILED, 2),
    run('b1', 'b', '2026-11-10T10:00:00Z', BacktestStatus.RUNNING),
    create(BacktestRunSchema, { id: 'x', strategyId: 'c' }),
  ];

  it('groups runs by strategy, newest strategy first, skipping runs without a date', () => {
    const rows = strategyRows(runs);
    expect(rows.map((r) => r.strategyId)).toEqual(['b', 'a']);
    expect(rows[1].latest.run.id).toBe('a2');
    expect(rows[1].latestCompleted?.run.id).toBe('a1');
    expect(rows[1].versions).toBe(2);
    expect(rows[0].latestCompleted).toBeNull();
  });

  it('spans the first run through today', () => {
    const win = timelineWindow(strategyRows(runs), new Date('2026-11-16T00:00:00Z'));
    expect(win?.start.getTime() ?? Infinity).toBeLessThan(Date.parse('2026-10-01T10:00:00Z'));
    expect(win?.end.getTime() ?? 0).toBeGreaterThan(Date.parse('2026-11-16T00:00:00Z'));
    expect(timelineWindow([], new Date())).toBeNull();
  });

  it('lists runs in flight', () => {
    expect(inFlight(runs).map((r) => r.id)).toEqual(['b1']);
  });
});

describe('comparing what two runs held', () => {
  const dates = ['02', '03', '06', '07', '08', '09'].map((x) => d(`2025-01-${x}`));
  const start = dates[0];
  const end = d('2025-01-10');
  const aLanes = holdingLanes([trade('QQQ', '2025-01-02', null)], start, end);
  const bLanes = holdingLanes(
    [trade('QQQ', '2025-01-02', '2025-01-06'), trade('IWM', '2025-01-06', '2025-01-08')],
    start,
    end
  );

  it('splits a run into stretches of the same symbols', () => {
    expect(heldStretches(bLanes, dates).map((s) => s.symbols.join(' '))).toEqual([
      'QQQ',
      'IWM',
      '',
    ]);
  });

  it('finds where they differed and what it was worth to the first', () => {
    const a = [1, 1.01, 1.03, 1.05, 1.05, 1.06];
    const b = [1, 1.01, 1.01, 1.02, 1.02, 1.02];
    const out = differingStretches(dates, a, b, aLanes, bLanes);
    expect(out).toHaveLength(1);
    expect(out[0].from).toEqual(d('2025-01-06'));
    expect(out[0].to).toEqual(d('2025-01-09'));
    expect(out[0].days).toBe(4);
    expect(out[0].gained).toBeCloseTo(1.06 / 1.02 / (1.01 / 1.01) - 1);
  });

  it('finds nothing when both held the same', () => {
    expect(
      differingStretches(dates, [1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1], aLanes, aLanes)
    ).toEqual([]);
  });
});
