import { create } from '@bufbuild/protobuf';
import { BacktestRunSchema, BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { StrategySchema, StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { PositionSchema } from '@llamatrade/core/proto/trading_pb';
import type { StrategyDeployment } from '@llamatrade/core/stores/strategies';
import { describe, expect, it } from 'vitest';

import { sessionHoldings } from '../../strategy-builder/rail/sessionHoldings';
import {
  latestRunPerVersion,
  matchesFilter,
  metaLine,
  rangeLabel,
  runFigures,
  runState,
  stateLabel,
  summaryLine,
} from '../strategyView';

const DSL = `(strategy "Radar" :rebalance monthly :benchmark SPY
  (if (> (rsi SPY 14) 70)
    (weight :method specified (asset TLT :weight 60) (asset GLD :weight 40))
    (else (weight :method equal (asset VTI) (asset QQQ)))))`;

const strategy = (
  over: Partial<{
    status: StrategyStatus;
    description: string;
    dslCode: string;
    version: number;
  }> = {}
) =>
  create(StrategySchema, {
    id: 's1',
    name: 'Radar',
    status: StrategyStatus.ACTIVE,
    dslCode: DSL,
    version: 3,
    ...over,
  });

const deployment = (status: ExecutionStatus): StrategyDeployment => ({
  allocatedCapital: 25000,
  currentValue: 26000,
  mode: ExecutionMode.PAPER,
  status,
  returnAll: 4,
  color: '',
});

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });

const run = (
  over: {
    version?: number;
    status?: BacktestStatus;
    completed?: string;
    withMetrics?: boolean;
  } = {}
) =>
  create(BacktestRunSchema, {
    id: `r-${over.version ?? 1}-${over.completed ?? 'x'}`,
    strategyId: 's1',
    strategyVersion: over.version ?? 1,
    status: over.status ?? BacktestStatus.COMPLETED,
    completedAt: ts(over.completed ?? '2026-10-01T00:00:00Z'),
    config: { startDate: ts('2024-11-01T00:00:00Z'), endDate: ts('2026-10-30T00:00:00Z') },
    results:
      over.withMetrics === false
        ? undefined
        : {
            metrics: {
              totalReturn: { value: '0.214' },
              annualizedReturn: { value: '0.102' },
              maxDrawdown: { value: '0.123' },
              sharpeRatio: { value: '0.79' },
              benchmarkReturn: { value: '0.249' },
            },
            benchmarkSymbol: 'SPY',
            equityCurve: [
              { timestamp: ts('2024-11-01T00:00:00Z'), equity: { value: '100000' } },
              { timestamp: ts('2026-10-30T00:00:00Z'), equity: { value: '121400' } },
            ],
            benchmarkEquityCurve: [
              { timestamp: ts('2024-11-01T00:00:00Z'), equity: { value: '100000' } },
              { timestamp: ts('2026-10-30T00:00:00Z'), equity: { value: '124900' } },
            ],
          },
  });

describe('runState', () => {
  it('follows the paper session when deployed', () => {
    expect(runState(strategy(), deployment(ExecutionStatus.RUNNING))).toBe('running');
    expect(runState(strategy(), deployment(ExecutionStatus.PENDING))).toBe('waiting');
    expect(runState(strategy(), deployment(ExecutionStatus.ERROR))).toBe('error');
    expect(runState(strategy(), deployment(ExecutionStatus.PAUSED))).toBe('paused');
  });

  it('falls back to the strategy status', () => {
    expect(runState(strategy({ status: StrategyStatus.DRAFT }), undefined)).toBe('draft');
    expect(runState(strategy({ status: StrategyStatus.ACTIVE }), undefined)).toBe('stopped');
    expect(runState(strategy({ status: StrategyStatus.PAUSED }), undefined)).toBe('paused');
  });

  it('says "Not running" for a strategy that never ran', () => {
    expect(stateLabel('stopped', false)).toBe('Not running');
    expect(stateLabel('stopped', true)).toBeUndefined();
  });
});

describe('matchesFilter', () => {
  it('groups session states under Running', () => {
    expect(matchesFilter('error', 'running')).toBe(true);
    expect(matchesFilter('draft', 'running')).toBe(false);
    expect(matchesFilter('draft', 'draft')).toBe(true);
    expect(matchesFilter('stopped', 'stopped')).toBe(true);
    expect(matchesFilter('running', 'all')).toBe(true);
  });
});

describe('runFigures', () => {
  it('reads a completed run, with drawdown as a negative fraction', () => {
    const f = runFigures(run());
    expect(f).not.toBeNull();
    expect(f?.totalReturn).toBeCloseTo(0.214);
    expect(f?.maxDrawdown).toBeCloseTo(-0.123);
    expect(f?.benchmarkReturn).toBeCloseTo(0.249);
    expect(f?.equity).toEqual([100000, 121400]);
    expect(f?.bench).toEqual([100000, 124900]);
    expect(f && rangeLabel(f)).toBe('Nov 2024 to Oct 2026');
  });

  it('gives nothing for a run that has not completed or has no metrics', () => {
    expect(runFigures(run({ status: BacktestStatus.FAILED }))).toBeNull();
    expect(runFigures(run({ withMetrics: false }))).toBeNull();
    expect(runFigures(null)).toBeNull();
  });
});

describe('summaryLine and metaLine', () => {
  it('prefers the description', () => {
    expect(summaryLine(strategy({ description: 'Bonds and gold when stretched.' }))).toBe(
      'Bonds and gold when stretched.'
    );
  });

  it('writes the first rules when there is no description', () => {
    expect(summaryLine(strategy({ description: '' }))).toBe(
      'If the 14-day RSI of SPY is above 70, then hold fixed weights across TLT, GLD, VTI, QQQ.'
    );
  });

  it('is empty for text that does not parse', () => {
    expect(summaryLine(strategy({ description: '', dslCode: '(nope' }))).toBe('');
  });

  it('builds the meta line', () => {
    expect(metaLine(strategy(), 25000)).toBe(
      'Version 3 · monthly · benchmark SPY · $25,000 allocated'
    );
    expect(metaLine(strategy(), null)).toBe('Version 3 · monthly · benchmark SPY');
  });
});

describe('latestRunPerVersion', () => {
  it('keeps the newest completed run of each version', () => {
    const runs = [
      run({ version: 2, completed: '2026-09-01T00:00:00Z' }),
      run({ version: 2, completed: '2026-09-20T00:00:00Z' }),
      run({ version: 3, status: BacktestStatus.FAILED }),
      run({ version: 1 }),
    ];
    const map = latestRunPerVersion(runs);
    expect([...map.keys()].sort()).toEqual([1, 2]);
    expect(map.get(2)?.id).toBe('r-2-2026-09-20T00:00:00Z');
  });
});

describe('sessionHoldings', () => {
  it('weights positions by market value and reports the latest update', () => {
    const { holdings, asOf } = sessionHoldings([
      create(PositionSchema, {
        symbol: 'TLT',
        marketValue: { value: '15000' },
        updatedAt: ts('2026-11-13T15:00:00Z'),
      }),
      create(PositionSchema, {
        symbol: 'GLD',
        marketValue: { value: '10000' },
        updatedAt: ts('2026-11-13T15:10:00Z'),
      }),
      create(PositionSchema, { symbol: 'ZERO', marketValue: { value: '0' } }),
    ]);
    expect(holdings).toEqual([
      { symbol: 'TLT', pct: 60 },
      { symbol: 'GLD', pct: 40 },
    ]);
    expect(asOf?.toISOString()).toBe('2026-11-13T15:10:00.000Z');
  });

  it('is empty with no positions', () => {
    expect(sessionHoldings([])).toEqual({ holdings: [], asOf: null });
  });
});
