import { create } from '@bufbuild/protobuf';
import {
  BacktestMetricsSchema,
  BacktestRunSchema,
  BacktestStatus,
  type BacktestMetrics,
} from '@llamatrade/core/proto/backtest_pb';
import { describe, expect, it } from 'vitest';

import {
  aheadOfPrevious,
  laneSubtitle,
  newerThanTrading,
  rebalancesThrough,
  sameSettings,
  sessionBarLabel,
  versionResults,
} from '../historyLanes';
import { strategyRows } from '../historyTimeline';
import type { StrategySession } from '../strategySessions';

const ts = (iso: string) => ({ seconds: BigInt(Date.parse(iso) / 1000), nanos: 0 });

const run = (
  id: string,
  version: number,
  created: string,
  status = BacktestStatus.COMPLETED,
  start = '2021-01-04T00:00:00Z'
) =>
  create(BacktestRunSchema, {
    id,
    strategyId: 's1',
    strategyVersion: version,
    status,
    createdAt: ts(created),
    config: {
      startDate: ts(start),
      endDate: ts('2026-10-30T00:00:00Z'),
      initialCapital: { value: '25000' },
    },
  });

const metrics = (rets: Record<string, string>): Record<string, BacktestMetrics> =>
  Object.fromEntries(
    Object.entries(rets).map(([id, v]) => [
      id,
      create(BacktestMetricsSchema, { totalReturn: { value: v } }),
    ])
  );

const session = (over: Partial<StrategySession> = {}): StrategySession => ({
  strategyId: 's1',
  version: 3,
  mode: 'paper',
  active: true,
  startedAt: new Date('2026-06-02T14:00:00Z'),
  stoppedAt: null,
  href: '/trading/x',
  ...over,
});

describe('history lanes', () => {
  const runs = [
    run('a', 1, '2026-05-29T12:00:00Z'),
    run('b', 2, '2026-11-03T12:00:00Z', BacktestStatus.COMPLETED, '2023-11-01T00:00:00Z'),
    run('c', 2, '2026-11-12T12:00:00Z'),
    run('d', 3, '2026-11-16T12:00:00Z'),
  ];
  const row = strategyRows(runs)[0];
  const m = metrics({ a: '0.569', b: '0.284', c: '0.635', d: '0.712' });

  it('compares settings on dates and capital', () => {
    expect(sameSettings(runs[0], runs[2])).toBe(true);
    expect(sameSettings(runs[1], runs[2])).toBe(false);
  });

  it('keeps the newest finished run per version', () => {
    expect(versionResults(row).map((r) => r.run.id)).toEqual(['a', 'c', 'd']);
  });

  it('measures the lead over the newest earlier version on the same settings', () => {
    const ahead = aheadOfPrevious(row, m);
    expect(ahead?.version).toBe(2);
    expect(ahead?.points).toBeCloseTo(7.7, 5);
  });

  it('has no lead when no earlier version ran the same settings', () => {
    const solo = strategyRows([runs[1], runs[3]])[0];
    expect(aheadOfPrevious(solo, m)).toBeNull();
    expect(aheadOfPrevious(row, {})).toBeNull();
  });

  it('labels session bars and lane subtitles', () => {
    expect(sessionBarLabel(session())).toBe('Paper from v3');
    expect(sessionBarLabel(session({ mode: 'live', version: 2 }))).toBe('Live from v2');
    expect(sessionBarLabel(session({ active: false, stoppedAt: new Date(2026, 10, 12) }))).toBe(
      'Stopped Nov 12'
    );
    expect(laneSubtitle(row, session())).toBe('3 versions · paper session runs v3');
    expect(laneSubtitle(row, null)).toBe('3 versions · not run as a session');
    expect(laneSubtitle(row, session({ active: false, stoppedAt: new Date(2026, 10, 12) }))).toBe(
      '3 versions · session stopped Nov 12'
    );
  });

  it('flags a newer version than the session trades', () => {
    const withV4 = strategyRows([
      ...runs,
      run('e', 4, '2026-11-18T10:00:00Z', BacktestStatus.RUNNING),
    ])[0];
    const n = newerThanTrading(withV4, [session()], m);
    expect(n?.newer.run.id).toBe('e');
    expect(n?.trading?.run.id).toBe('d');
    expect(n?.points).toBeNull();

    const finished = strategyRows([...runs, run('f', 4, '2026-11-18T10:00:00Z')])[0];
    const f = newerThanTrading(finished, [session()], { ...m, ...metrics({ f: '0.727' }) });
    expect(f?.points).toBeCloseTo(1.5, 5);
  });

  it('says nothing when the session runs the newest version or is stopped', () => {
    expect(newerThanTrading(row, [session()], m)).toBeNull();
    expect(newerThanTrading(row, [session({ version: 2, active: false })], m)).toBeNull();
    expect(newerThanTrading(row, [], m)).toBeNull();
  });
});

describe('rebalancesThrough', () => {
  it('counts scheduled rebalances up to the simulated date', () => {
    const r = create(BacktestRunSchema, {
      currentDate: '2021-04-15',
      config: { startDate: ts('2021-01-04T00:00:00Z'), endDate: ts('2021-12-31T00:00:00Z') },
    });
    const c = rebalancesThrough(r, 'monthly');
    expect(c).not.toBeNull();
    expect(c?.passed).toBeLessThan(c?.total ?? 0);
    expect(c?.passed).toBeGreaterThan(0);
  });

  it('is null without a calendar schedule or a date', () => {
    const r = create(BacktestRunSchema, {
      config: { startDate: ts('2021-01-04T00:00:00Z'), endDate: ts('2021-12-31T00:00:00Z') },
    });
    expect(rebalancesThrough(r, 'monthly')).toBeNull();
    expect(
      rebalancesThrough(create(BacktestRunSchema, { currentDate: '2021-04-15' }), 'daily')
    ).toBeNull();
  });
});
