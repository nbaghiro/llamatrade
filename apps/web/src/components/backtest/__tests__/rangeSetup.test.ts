import { create } from '@bufbuild/protobuf';
import { BacktestRunSchema, BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { describe, expect, it } from 'vitest';

import { curatedRanges } from '../../../lib/backtestRanges';
import { durationLabel, estimateSeconds, testedOn } from '../rangeSetup';

const ts = (iso: string) => ({ seconds: BigInt(Date.parse(iso) / 1000), nanos: 0 });

const run = (id: string, version: number, start: string, end: string, secs: number) =>
  create(BacktestRunSchema, {
    id,
    strategyId: 's1',
    strategyVersion: version,
    status: BacktestStatus.COMPLETED,
    startedAt: ts('2026-11-01T12:00:00Z'),
    completedAt: ts(new Date(Date.parse('2026-11-01T12:00:00Z') + secs * 1000).toISOString()),
    config: { startDate: ts(`${start}T00:00:00Z`), endDate: ts(`${end}T00:00:00Z`) },
  });

describe('estimateSeconds', () => {
  it('scales the median pace of past runs to the range', () => {
    const runs = [
      run('a', 1, '2025-01-01', '2025-01-11', 10),
      run('b', 1, '2025-01-01', '2025-01-11', 20),
      run('c', 1, '2025-01-01', '2025-01-11', 40),
    ];
    expect(estimateSeconds(runs, 100)).toBe(200);
    expect(estimateSeconds([], 100)).toBeNull();
  });
  it('words the estimate', () => {
    expect(durationLabel(19)).toBe('About 20 seconds');
    expect(durationLabel(1)).toBe('About 5 seconds');
    expect(durationLabel(200)).toBe('About 3 minutes');
  });
});

describe('testedOn', () => {
  it('picks the latest version run per range and leaves the rest untested', () => {
    const ranges = curatedRanges(new Date('2026-10-30T00:00:00Z'));
    const rows = testedOn(
      [
        run('v2', 2, '2021-10-30', '2026-10-30', 10),
        run('v3', 3, '2021-11-01', '2026-10-29', 10),
        run('other', 3, '2020-01-02', '2020-06-30', 10),
      ],
      's1',
      ranges
    );
    expect(rows.map((r) => r.run?.id ?? null)).toEqual(['v3', null, null, null]);
  });
});
