import { create } from '@bufbuild/protobuf';
import { BacktestRunSchema, BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { describe, expect, it } from 'vitest';

import {
  compareSameDates,
  dailyCloses,
  gapSteps,
  maxDrawdown,
  pickSameDatesRun,
  runPoints,
  valueAt,
} from '../sameDates';

const d = (iso: string) => new Date(iso);
const days = (from: string, values: number[]) =>
  values.map((value, i) => ({ at: new Date(Date.parse(from) + i * 86_400_000), value }));
const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });

describe('dailyCloses', () => {
  it('keeps the last point of each day, in order', () => {
    const out = dailyCloses([
      { at: d('2026-06-03T15:00:00Z'), value: 3 },
      { at: d('2026-06-02T14:00:00Z'), value: 1 },
      { at: d('2026-06-02T19:00:00Z'), value: 2 },
    ]);
    expect(out.map((p) => p.value)).toEqual([2, 3]);
  });
});

describe('valueAt', () => {
  it('returns the value on or before a date', () => {
    const s = days('2026-06-01T00:00:00Z', [10, 11, 12]);
    expect(valueAt(s, d('2026-06-02T12:00:00Z'))).toBe(11);
    expect(valueAt(s, d('2026-07-01T00:00:00Z'))).toBe(12);
    expect(valueAt(s, d('2026-05-01T00:00:00Z'))).toBeNull();
  });
});

describe('compareSameDates', () => {
  it('rebases both to the first shared day and measures the gap in points', () => {
    const paper = days('2026-06-01T20:00:00Z', [100, 101, 102, 103, 104, 105]);
    const bt = days(
      '2026-01-01T00:00:00Z',
      Array.from({ length: 200 }, () => 50)
    );
    const out = compareSameDates(paper, bt);
    expect(out).not.toBeNull();
    expect(out?.dates).toHaveLength(6);
    expect(out?.paper[5]).toBeCloseTo(0.05);
    expect(out?.backtest[5]).toBeCloseTo(0);
    expect(out?.gap[5]).toBeCloseTo(5);
    expect(out?.backtestScaled[0]).toBeCloseTo(100);
  });

  it('stops at the end of the backtest and needs five shared days', () => {
    const paper = days('2026-06-01T20:00:00Z', [100, 101, 102, 103, 104, 105, 106]);
    const shortBt = days('2026-06-01T00:00:00Z', [50, 50, 50]);
    expect(compareSameDates(paper, shortBt)).toBeNull();
    const bt = days(
      '2026-05-01T00:00:00Z',
      Array.from({ length: 37 }, () => 50)
    );
    expect(compareSameDates(paper, bt)?.dates).toHaveLength(6);
  });

  it('returns null without data', () => {
    expect(compareSameDates([], days('2026-01-01T00:00:00Z', [1, 2]))).toBeNull();
  });
});

describe('gapSteps', () => {
  it('splits the gap into fill days and what moved between them', () => {
    const dates = days('2026-06-01T20:00:00Z', [0, 0, 0, 0]).map((p) => p.at);
    const gap = [-0.1, -0.1, -0.4, -0.5];
    const out = gapSteps({ dates, gap }, [
      d('2026-06-03T14:00:00Z'),
      d('2026-06-01T14:00:00Z'),
      d('2026-06-03T15:00:00Z'),
    ]);
    expect(out.steps.map((s) => s.change)).toEqual([-0.1, expect.closeTo(-0.3)]);
    expect(out.total).toBeCloseTo(-0.5);
    expect(out.between).toBeCloseTo(-0.1);
  });

  it('counts a fill on the next compared day when its own day has no close', () => {
    const dates = [d('2026-06-01T20:00:00Z'), d('2026-06-05T20:00:00Z')];
    const out = gapSteps({ dates, gap: [0, -1] }, [d('2026-06-03T14:00:00Z')]);
    expect(out.steps).toEqual([{ at: dates[1], change: -1 }]);
    expect(out.between).toBeCloseTo(0);
  });

  it('leaves out fill days outside the compared dates', () => {
    const dates = days('2026-06-01T20:00:00Z', [0, 0]).map((p) => p.at);
    expect(gapSteps({ dates, gap: [0, 1] }, [d('2025-01-01T00:00:00Z')]).steps).toEqual([]);
  });
});

describe('maxDrawdown', () => {
  it('finds the worst fall from a peak', () => {
    expect(maxDrawdown([100, 120, 90, 130, 117])).toBeCloseTo(-0.25);
    expect(maxDrawdown([1, 2, 3])).toBe(0);
    expect(maxDrawdown([])).toBe(0);
  });
});

const run = (id: string, version: number, start: string, end: string, created: string) =>
  create(BacktestRunSchema, {
    id,
    strategyVersion: version,
    status: BacktestStatus.COMPLETED,
    createdAt: ts(created),
    config: { startDate: ts(start), endDate: ts(end) },
  });

describe('pickSameDatesRun', () => {
  const s = d('2026-06-02T00:00:00Z');
  const e = d('2026-11-17T00:00:00Z');

  it('prefers the session version, then the most overlap', () => {
    const a = run('a', 1, '2024-01-01T00:00:00Z', '2026-11-01T00:00:00Z', '2026-11-02T00:00:00Z');
    const b = run('b', 2, '2026-01-01T00:00:00Z', '2026-09-01T00:00:00Z', '2026-09-02T00:00:00Z');
    const c = run('c', 2, '2025-01-01T00:00:00Z', '2026-11-10T00:00:00Z', '2026-11-11T00:00:00Z');
    expect(pickSameDatesRun([a, b, c], s, e, 2)?.id).toBe('c');
    expect(pickSameDatesRun([a, b, c], s, e, null)?.id).toBe('c');
    expect(pickSameDatesRun([a, b, c], s, e, 1)?.id).toBe('a');
  });

  it('skips runs that end before the session started or did not complete', () => {
    const early = run(
      'x',
      2,
      '2020-01-01T00:00:00Z',
      '2026-05-01T00:00:00Z',
      '2026-05-02T00:00:00Z'
    );
    const failed = run(
      'y',
      2,
      '2020-01-01T00:00:00Z',
      '2026-11-01T00:00:00Z',
      '2026-11-02T00:00:00Z'
    );
    failed.status = BacktestStatus.FAILED;
    expect(pickSameDatesRun([early, failed], s, e, 2)).toBeNull();
  });
});

describe('runPoints', () => {
  it('reads the equity curve and drops empty points', () => {
    const r = create(BacktestRunSchema, {
      results: {
        equityCurve: [
          { timestamp: ts('2026-01-01T00:00:00Z'), equity: { value: '100' } },
          { timestamp: ts('2026-01-02T00:00:00Z') },
        ],
      },
    });
    expect(runPoints(r)).toEqual([{ at: d('2026-01-01T00:00:00Z'), value: 100 }]);
    expect(runPoints(null)).toEqual([]);
  });
});
