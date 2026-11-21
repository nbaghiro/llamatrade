import { create } from '@bufbuild/protobuf';
import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { StrategyExecutionSchema, StrategySchema } from '@llamatrade/core/proto/strategy_pb';
import { TradingSessionSchema } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import { buildSessionRow, type SessionRow } from '../../sessions/sessionRows';
import {
  listSummary,
  notRunningAction,
  notRunningState,
  runningFigures,
  sharedRange,
  splitByRunning,
} from '../runningModel';
import type { SameDates } from '../sameDates';
import type { BacktestCell } from '../stageModel';
import type { RunFigures } from '../strategyView';

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });

const strategy = (id: string, version = 2) =>
  create(StrategySchema, { id, name: id, version, rebalance: 'monthly', symbols: ['SPY'] });

function row(
  strategyId: string,
  over: { id?: string; mode?: ExecutionMode; ended?: string; started?: string } = {}
): SessionRow {
  const id = over.id ?? `s-${strategyId}`;
  const session = create(TradingSessionSchema, {
    id,
    strategyId,
    name: strategyId,
    mode: over.mode ?? ExecutionMode.PAPER,
    isActive: !over.ended,
    startedAt: ts(over.started ?? '2026-06-02T14:00:00Z'),
    endedAt: over.ended ? ts(over.ended) : undefined,
    sleeveId: `sl-${id}`,
  });
  const execution = create(StrategyExecutionSchema, {
    id: `e-${id}`,
    strategyId,
    sleeveId: `sl-${id}`,
    status: over.ended ? ExecutionStatus.STOPPED : ExecutionStatus.RUNNING,
    version: 2,
  });
  return buildSessionRow(session, {
    executions: [execution],
    sleeves: [],
    performance: [],
    strategies: [strategy(strategyId)],
    orders: [],
  });
}

const figures = (
  start: string,
  end: string,
  sym = 'SPY',
  bench: number | null = 0.2
): RunFigures => ({
  totalReturn: 0.1,
  cagr: 0.05,
  maxDrawdown: -0.1,
  sharpe: 1,
  benchmarkReturn: bench,
  benchmarkSymbol: sym,
  start: new Date(start),
  end: new Date(end),
  dates: [],
  equity: [],
  bench: [],
});

describe('splitByRunning', () => {
  it('puts open sessions first, live before paper, and the rest after', () => {
    const a = strategy('a');
    const b = strategy('b');
    const c = strategy('c');
    const d = strategy('d');
    const sessions = [
      row('a', { started: '2026-05-01T14:00:00Z' }),
      row('b', { mode: ExecutionMode.LIVE, started: '2026-08-01T14:00:00Z' }),
      row('c', { ended: '2026-11-12T20:00:00Z' }),
    ];
    const { running, notRunning } = splitByRunning([a, b, c, d], sessions);
    expect(running.map((r) => r.strategy.id)).toEqual(['b', 'a']);
    expect(notRunning.map((s) => s.id)).toEqual(['c', 'd']);
  });

  it('gives a strategy one item per open session', () => {
    const a = strategy('a');
    const sessions = [row('a', { id: 'p' }), row('a', { id: 'l', mode: ExecutionMode.LIVE })];
    expect(splitByRunning([a], sessions).running.map((r) => r.row.session.id)).toEqual(['l', 'p']);
  });

  it('summarises the counts', () => {
    expect(listSummary(3, 4)).toBe('3 running · 4 not running');
    expect(listSummary(0, 1)).toBe('0 running · 1 not running');
  });
});

describe('notRunningState and action', () => {
  const none: BacktestCell = { kind: 'none' };
  const current: BacktestCell = {
    kind: 'current',
    version: 2,
    figures: figures('2024-11-01', '2026-10-30'),
  };
  const stale: BacktestCell = {
    kind: 'stale',
    version: 1,
    figures: figures('2024-11-01', '2026-10-30'),
  };

  it('is stopped when a session ran it before', () => {
    const s = notRunningState(strategy('a'), current, [
      row('a', { ended: '2026-11-12T20:00:00Z' }),
    ]);
    expect(s.kind).toBe('stopped');
    if (s.kind === 'stopped') {
      expect(s.at?.toISOString()).toBe('2026-11-12T20:00:00.000Z');
      expect(s.live).toBe(false);
    }
  });

  it('is never run with a current backtest, a draft otherwise', () => {
    expect(notRunningState(strategy('a'), current, [])).toEqual({ kind: 'neverRun' });
    expect(notRunningState(strategy('a', 2), stale, [])).toEqual({ kind: 'draft', version: 2 });
    expect(notRunningState(strategy('a', 0), none, [])).toEqual({ kind: 'draft', version: 1 });
    expect(notRunningState(strategy('a'), { kind: 'loading' }, [])).toEqual({ kind: 'loading' });
  });

  it('offers one next step', () => {
    expect(notRunningAction(strategy('a'), none)).toEqual({ kind: 'first' });
    expect(notRunningAction(strategy('a', 3), stale)).toEqual({ kind: 'backtest', version: 3 });
    expect(notRunningAction(strategy('a'), current)).toBeNull();
    expect(notRunningAction(strategy('a'), { kind: 'loading' })).toBeNull();
  });
});

describe('sharedRange', () => {
  it('returns the range when every loaded run shares it by month', () => {
    const r = sharedRange([
      figures('2024-11-01', '2026-10-30'),
      null,
      figures('2024-11-04', '2026-10-28'),
    ]);
    expect(r?.benchmarkReturn).toBe(0.2);
    expect(r?.benchmarkSymbol).toBe('SPY');
  });

  it('is null when ranges or benchmarks differ, or nothing loaded', () => {
    expect(
      sharedRange([figures('2024-11-01', '2026-10-30'), figures('2023-01-01', '2026-10-30')])
    ).toBeNull();
    expect(
      sharedRange([figures('2024-11-01', '2026-10-30'), figures('2024-11-01', '2026-10-30', 'QQQ')])
    ).toBeNull();
    expect(sharedRange([null])).toBeNull();
  });
});

describe('runningFigures', () => {
  it('uses the shared days when a backtest covers them', () => {
    const same: SameDates = {
      dates: [new Date(0), new Date(1)],
      paper: [0, 0.068],
      backtest: [0, 0.073],
      gap: [0, -0.5],
      backtestScaled: [1, 1],
      start: new Date(0),
      end: new Date(1),
    };
    expect(runningFigures(row('a'), same)).toEqual({ session: 0.068, backtest: 0.073, gap: -0.5 });
  });

  it('falls back to the session figure with no backtest', () => {
    expect(runningFigures(row('a'), null)).toEqual({ session: null, backtest: null, gap: null });
  });
});
