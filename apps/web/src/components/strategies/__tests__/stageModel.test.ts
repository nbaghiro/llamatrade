import { create } from '@bufbuild/protobuf';
import { BacktestRunSchema, BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { StrategyExecutionSchema, StrategySchema } from '@llamatrade/core/proto/strategy_pb';
import { TradingSessionSchema } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import { buildSessionRow, type SessionRow } from '../../sessions/sessionRows';
import {
  backtestCell,
  nextStage,
  pickSession,
  stageRow,
  strategySub,
  trackSummary,
} from '../stageModel';

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });
const TODAY = new Date(Date.UTC(2026, 10, 17));

const strategy = (version = 2, rebalance = 'monthly') =>
  create(StrategySchema, { id: 'st1', name: 'Radar', version, rebalance, symbols: ['TLT', 'GLD'] });

const run = (version: number) =>
  create(BacktestRunSchema, {
    id: `r${version}`,
    strategyId: 'st1',
    strategyVersion: version,
    status: BacktestStatus.COMPLETED,
    config: { startDate: ts('2024-11-01T00:00:00Z'), endDate: ts('2026-10-30T00:00:00Z') },
    results: {
      metrics: { totalReturn: { value: '0.2' }, sharpeRatio: { value: '1.1' } },
      equityCurve: [],
    },
  });

function row(
  over: {
    id?: string;
    mode?: ExecutionMode;
    active?: boolean;
    ended?: string;
    started?: string;
  } = {}
): SessionRow {
  const id = over.id ?? 's1';
  const session = create(TradingSessionSchema, {
    id,
    strategyId: 'st1',
    name: 'Radar (paper)',
    mode: over.mode ?? ExecutionMode.PAPER,
    isActive: over.active ?? true,
    startedAt: ts(over.started ?? '2026-06-02T14:00:00Z'),
    endedAt: over.ended ? ts(over.ended) : undefined,
    sleeveId: `sl-${id}`,
  });
  const execution = create(StrategyExecutionSchema, {
    id: `e-${id}`,
    strategyId: 'st1',
    sleeveId: `sl-${id}`,
    status: over.ended ? ExecutionStatus.STOPPED : ExecutionStatus.RUNNING,
    version: 2,
  });
  return buildSessionRow(session, {
    executions: [execution],
    sleeves: [],
    performance: [],
    strategies: [strategy()],
    orders: [],
  });
}

describe('backtestCell', () => {
  it('tells a run of this version from one of an older version', () => {
    expect(backtestCell(strategy(2), undefined).kind).toBe('loading');
    expect(backtestCell(strategy(2), null).kind).toBe('none');
    expect(backtestCell(strategy(2), run(2))).toMatchObject({ kind: 'current', version: 2 });
    expect(backtestCell(strategy(3), run(2))).toMatchObject({ kind: 'stale', version: 2 });
  });

  it('treats a failed run as no backtest', () => {
    const failed = run(2);
    failed.status = BacktestStatus.FAILED;
    expect(backtestCell(strategy(2), failed).kind).toBe('none');
  });
});

describe('pickSession', () => {
  it('prefers an open session, then the newest', () => {
    const old = row({
      id: 'a',
      started: '2026-01-01T00:00:00Z',
      active: false,
      ended: '2026-02-01T00:00:00Z',
    });
    const open = row({ id: 'b', started: '2025-01-01T00:00:00Z' });
    const newer = row({
      id: 'c',
      started: '2026-03-01T00:00:00Z',
      active: false,
      ended: '2026-04-01T00:00:00Z',
    });
    expect(pickSession([old, open, newer])?.session.id).toBe('b');
    expect(pickSession([old, newer])?.session.id).toBe('c');
    expect(pickSession([])).toBeNull();
  });
});

describe('stageRow', () => {
  it('puts a strategy with no backtest at draft, with a first backtest next', () => {
    const r = stageRow(strategy(), null, [], TODAY);
    expect(r.stage).toBe('draft');
    expect(r.next).toEqual({ kind: 'firstBacktest' });
    expect(nextStage(r)).toBe('backtested');
  });

  it('asks for a backtest of the new version when the rules changed since the last run', () => {
    const r = stageRow(strategy(3), run(2), [], TODAY);
    expect(r.stage).toBe('draft');
    expect(r.next).toEqual({ kind: 'backtest', version: 3 });
  });

  it('offers paper once the current version is backtested', () => {
    const r = stageRow(strategy(2), run(2), [], TODAY);
    expect(r.stage).toBe('backtested');
    expect(r.next).toEqual({ kind: 'start' });
    expect(nextStage(r)).toBe('paper');
  });

  it('shows the next rebalance for a running paper session', () => {
    const r = stageRow(strategy(), run(2), [row()], TODAY);
    expect(r.stage).toBe('paper');
    expect(r.next).toEqual({ kind: 'rebalance', at: new Date(Date.UTC(2026, 11, 1)) });
    expect(nextStage(r)).toBeNull();
  });

  it('offers a restart for a stopped session', () => {
    const r = stageRow(
      strategy(),
      run(2),
      [row({ active: false, ended: '2026-11-12T20:00:00Z' })],
      TODAY
    );
    expect(r.stage).toBe('paper');
    expect(r.next).toEqual({ kind: 'restart', mode: 'paper' });
  });

  it('ranks a live session above paper', () => {
    const r = stageRow(
      strategy(),
      run(2),
      [row(), row({ id: 'l', mode: ExecutionMode.LIVE })],
      TODAY
    );
    expect(r.stage).toBe('live');
    expect(r.paper?.session.id).toBe('s1');
    expect(r.live?.session.id).toBe('l');
  });

  it('ignores sessions of other strategies', () => {
    const other = row();
    other.session.strategyId = 'st2';
    expect(stageRow(strategy(), null, [other], TODAY).paper).toBeNull();
  });
});

describe('trackSummary', () => {
  it('counts live, paper, stopped and never run', () => {
    const rows = [
      stageRow(strategy(), null, [row({ id: 'l', mode: ExecutionMode.LIVE })], TODAY),
      stageRow(strategy(), null, [row()], TODAY),
      stageRow(strategy(), null, [row({ active: false, ended: '2026-11-12T20:00:00Z' })], TODAY),
      stageRow(strategy(), null, [], TODAY),
    ];
    expect(trackSummary(rows)).toBe('4 strategies · 1 live, 1 in paper, 1 stopped, 1 not run yet');
    expect(trackSummary([])).toBe('0 strategies');
  });
});

describe('strategySub', () => {
  it('capitalises the schedule and shortens long symbol lists', () => {
    expect(strategySub({ rebalance: 'quarterly', symbols: ['VTI', 'GLD'] })).toBe(
      'Quarterly · VTI GLD'
    );
    expect(strategySub({ rebalance: '', symbols: ['A', 'B', 'C', 'D', 'E', 'F'] })).toBe(
      'A B C +3'
    );
  });
});
