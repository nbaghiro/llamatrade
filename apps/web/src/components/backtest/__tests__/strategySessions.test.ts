import { create } from '@bufbuild/protobuf';
import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { StrategyExecutionSchema } from '@llamatrade/core/proto/strategy_pb';
import { TradingSessionSchema } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import {
  latestSession,
  openSessionLabel,
  sessionForVersion,
  strategySessions,
} from '../strategySessions';

const ts = (iso: string) => ({ seconds: BigInt(Date.parse(iso) / 1000), nanos: 0 });

const exec = (
  id: string,
  version: number,
  mode: ExecutionMode,
  status: ExecutionStatus,
  started: string,
  sleeveId = ''
) =>
  create(StrategyExecutionSchema, {
    id,
    strategyId: 's1',
    version,
    mode,
    status,
    startedAt: ts(started),
    sleeveId,
  });

describe('strategySessions', () => {
  const executions = [
    exec('e1', 2, ExecutionMode.PAPER, ExecutionStatus.STOPPED, '2026-03-01T14:00:00Z'),
    exec('e2', 3, ExecutionMode.PAPER, ExecutionStatus.RUNNING, '2026-06-02T14:00:00Z', 'sl-2'),
    exec('e3', 3, ExecutionMode.LIVE, ExecutionStatus.RUNNING, '2026-08-04T14:00:00Z'),
  ];
  const sessions = [
    create(TradingSessionSchema, {
      id: 'sess-paper',
      strategyId: 's1',
      mode: ExecutionMode.PAPER,
      sleeveId: 'sl-2',
      startedAt: ts('2026-06-02T14:00:00Z'),
    }),
    create(TradingSessionSchema, {
      id: 'sess-live',
      strategyId: 's1',
      mode: ExecutionMode.LIVE,
      startedAt: ts('2026-08-04T14:00:00Z'),
    }),
  ];

  it('links sessions by sleeve, then by strategy, mode and start, newest first', () => {
    const list = strategySessions(executions, sessions);
    expect(list.map((s) => [s.version, s.mode, s.active, s.href])).toEqual([
      [3, 'live', true, '/trading/sess-live'],
      [3, 'paper', true, '/trading/sess-paper'],
      [2, 'paper', false, null],
    ]);
  });

  it('prefers live for a version and ignores stopped sessions', () => {
    const list = strategySessions(executions, sessions);
    expect(sessionForVersion(list, 's1', 3)?.mode).toBe('live');
    expect(sessionForVersion(list, 's1', 2)).toBeNull();
    expect(sessionForVersion(list, 'other', 3)).toBeNull();
  });

  it('finds the latest session and labels it', () => {
    const list = strategySessions(executions, sessions);
    const latest = latestSession(list, 's1');
    expect(latest?.mode).toBe('live');
    expect(latest && openSessionLabel(latest)).toBe('Open the live session');
    expect(latest && openSessionLabel(latest, true)).toBe('Open the v3 live session');
    expect(latestSession(list, 'none')).toBeNull();
  });

  it('skips executions that are neither paper nor live', () => {
    const list = strategySessions(
      [exec('e9', 1, ExecutionMode.UNSPECIFIED, ExecutionStatus.RUNNING, '2026-01-01T00:00:00Z')],
      []
    );
    expect(list).toEqual([]);
  });
});
