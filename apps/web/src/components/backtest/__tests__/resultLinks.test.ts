import { create } from '@bufbuild/protobuf';
import { BacktestRunSchema, BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { describe, expect, it } from 'vitest';

import { costsLabel, previousVersionRun, resultMetaLine, untestedRange } from '../resultLinks';

const ts = (iso: string) => ({ seconds: BigInt(Date.parse(iso) / 1000), nanos: 0 });

const run = (
  id: string,
  version: number,
  start: string,
  end: string,
  status = BacktestStatus.COMPLETED,
  completed = '2026-11-01T12:00:00Z'
) =>
  create(BacktestRunSchema, {
    id,
    strategyId: 's1',
    strategyVersion: version,
    status,
    completedAt: ts(completed),
    config: {
      startDate: ts(`${start}T00:00:00Z`),
      endDate: ts(`${end}T00:00:00Z`),
      initialCapital: { value: '25000' },
      benchmarkSymbol: 'SPY',
    },
  });

describe('previousVersionRun', () => {
  it('picks the latest completed run of the newest earlier version', () => {
    const current = run('c', 3, '2021-01-04', '2026-10-30');
    const runs = [
      run('a', 1, '2021-01-04', '2026-10-30'),
      run('b-old', 2, '2021-01-04', '2026-10-30', BacktestStatus.COMPLETED, '2026-09-01T00:00:00Z'),
      run('b-new', 2, '2021-01-04', '2026-10-30', BacktestStatus.COMPLETED, '2026-10-01T00:00:00Z'),
      run('b-failed', 2, '2021-01-04', '2026-10-30', BacktestStatus.FAILED),
      current,
    ];
    expect(previousVersionRun(runs, current)?.id).toBe('b-new');
    expect(previousVersionRun([current], current)).toBeNull();
  });
});

describe('untestedRange', () => {
  const today = new Date('2026-10-30T00:00:00Z');
  it('skips ranges this version already ran on', () => {
    const current = run('c', 3, '2021-10-30', '2026-10-30');
    expect(untestedRange([], current, today)?.id).toBe('fall-2022');
    const more = [run('x', 3, '2021-11-01', '2023-06-30')];
    expect(untestedRange(more, current, today)?.id).toBe('mar-2020');
  });
  it('ignores other versions and returns null when all are tested', () => {
    const current = run('c', 3, '2021-10-30', '2026-10-30');
    const all = [
      run('x', 3, '2021-11-01', '2023-06-30'),
      run('y', 3, '2020-01-02', '2021-12-31'),
      run('z', 3, '2016-01-04', '2026-10-30'),
    ];
    expect(untestedRange(all, current, today)).toBeNull();
    expect(untestedRange([run('v2', 2, '2021-11-01', '2023-06-30')], current, today)?.id).toBe(
      'fall-2022'
    );
  });
});

describe('meta line', () => {
  it('names the range, capital, benchmark and finish', () => {
    const line = resultMetaLine(run('c', 3, '2021-01-04', '2026-10-30'), true);
    expect(line).toMatch(/^Jan 4, 2021 → Oct 30, 2026 · \$25,000 · against SPY · finished /);
    expect(resultMetaLine(run('c', 3, '2016-01-04', '2026-10-30'), false)).toBe(
      'Jan 4, 2016 → Oct 30, 2026, the earliest Alpaca history · $25,000 · against SPY'
    );
  });
  it('states costs only when the run carries them', () => {
    const r = run('c', 3, '2021-01-04', '2026-10-30');
    expect(costsLabel(r)).toBe('');
    const priced = create(BacktestRunSchema, {
      config: { commission: { value: '1' }, slippagePercent: { value: '0.0005' } },
    });
    expect(costsLabel(priced)).toBe('$1.00 per fill, 0.05% slippage');
  });
});
