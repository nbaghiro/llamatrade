import { BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { describe, expect, it } from 'vitest';

import type { SessionRow } from '../../sessions/sessionRows';
import {
  ACCOUNT_SUBJECT,
  buildSubjects,
  canvasStarters,
  earlierAbout,
  findSubject,
  subjectLimits,
  subjectQuestions,
  subjectReads,
} from '../subjects';

type Strategy = Parameters<typeof buildSubjects>[1][number];
type Run = Parameters<typeof buildSubjects>[2][number];

const today = new Date(Date.UTC(2026, 10, 16));

const row = (over: Record<string, unknown>, session: Record<string, unknown> = {}) =>
  ({
    session: { id: 's1', strategyId: 'st1', mode: ExecutionMode.PAPER, ...session },
    name: 'Recession Radar',
    version: 4,
    rebalance: 'Weekly',
    state: 'running',
    view: { attention: false, open: true },
    ...over,
  }) as unknown as SessionRow;

const strategy = (id: string, name: string, over: Record<string, unknown> = {}) =>
  ({
    id,
    name,
    status: StrategyStatus.ACTIVE,
    version: 2,
    rebalance: 'weekly',
    updatedAt: { seconds: 100n },
    ...over,
  }) as unknown as Strategy;

const run = (id: string, strategyId: string, status = BacktestStatus.COMPLETED) =>
  ({
    id,
    strategyId,
    strategyVersion: 3,
    status,
    completedAt: { seconds: BigInt(Date.UTC(2026, 10, 13, 17) / 1000) },
  }) as unknown as Run;

describe('buildSubjects', () => {
  const groups = buildSubjects(
    [
      row({}),
      row(
        { name: 'Momentum Sectors', state: 'frozen', view: { attention: true, open: true } },
        {
          id: 's2',
          strategyId: 'st2',
          mode: ExecutionMode.LIVE,
        }
      ),
      row(
        { name: 'Old', state: 'stopped', view: { attention: false, open: false } },
        {
          id: 's3',
          strategyId: 'st4',
        }
      ),
    ],
    [
      strategy('st1', 'Recession Radar'),
      strategy('st3', 'Risk Parity', {
        status: StrategyStatus.DRAFT,
        updatedAt: { seconds: 200n },
      }),
      strategy('st5', 'Archived', { status: StrategyStatus.ARCHIVED }),
      strategy('st4', 'Old'),
    ],
    [run('b1', 'st1'), run('b2', 'st3', BacktestStatus.FAILED)],
    today
  );

  it('lists sessions with their state and tone', () => {
    expect(groups.sessions.map((s) => [s.name, s.meta, s.tone, s.mode])).toEqual([
      ['Recession Radar', 'Nov 23', 'accent', 'paper'],
      ['Momentum Sectors', 'Frozen', 'risk', 'live'],
      ['Old', 'Stopped', 'muted', 'paper'],
    ]);
    expect(groups.sessions[0].state).toBe('Running');
  });

  it('leaves out strategies already running, archived ones, and sorts newest first', () => {
    expect(groups.strategies.map((s) => [s.name, s.meta])).toEqual([
      ['Risk Parity', 'Draft'],
      ['Old', 'v2'],
    ]);
  });

  it('keeps completed backtests, named after their strategy', () => {
    expect(groups.backtests.map((b) => [b.name, b.meta, b.href])).toEqual([
      ['Recession Radar v3', 'Nov 13', '/backtest/b1'],
    ]);
  });

  it('finds subjects by key, including the account', () => {
    expect(findSubject(groups, 'account')).toBe(ACCOUNT_SUBJECT);
    expect(findSubject(groups, 'session:s2')?.name).toBe('Momentum Sectors');
    expect(findSubject(groups, 'session:nope')).toBeNull();
    expect(findSubject(groups, null)).toBeNull();
  });

  it('writes questions for the state and asks about attention first', () => {
    const frozen = subjectQuestions(groups.sessions[1]);
    expect(frozen[0].text).toBe('Why does Momentum Sectors need attention?');
    const running = subjectQuestions(groups.sessions[0]);
    expect(running[0].text).toBe('What will the Nov 23 rebalance do?');
    expect(subjectQuestions(ACCOUNT_SUBJECT)).toHaveLength(4);
  });

  it('only claims reads the agent has tools for', () => {
    const tools = [groups.sessions[0], groups.strategies[0], groups.backtests[0], ACCOUNT_SUBJECT]
      .flatMap(subjectReads)
      .map((r) => r.tool);
    const known = new Set([
      'get_strategy',
      'get_positions',
      'get_portfolio_performance',
      'get_portfolio_summary',
      'list_backtests',
      'get_backtest_results',
      'get_asset_info',
      'list_strategies',
    ]);
    expect(tools.every((t) => known.has(t))).toBe(true);
    expect(subjectLimits(groups.sessions[0])).toMatch(/fills/);
  });

  it('names your own sessions in the canvas starters, with generic ones otherwise', () => {
    const starters = canvasStarters(groups);
    expect(starters[1].prompts[0]).toBe('Why Recession Radar holds what it holds now');
    expect(starters[2].prompts[1]).toBe('Compare Recession Radar with Momentum Sectors since 2020');
    const empty = canvasStarters({ sessions: [], strategies: [], backtests: [] });
    expect(empty[2].prompts[0]).toMatch(/60\/40/);
  });

  it('finds earlier conversations whose title names the subject', () => {
    const sessions = [
      { title: 'Recession Radar in bonds', lastActivityAt: { seconds: 1n } },
      { title: 'Something else', lastActivityAt: { seconds: 2n } },
      { title: 'recession radar v5', lastActivityAt: { seconds: 3n } },
    ];
    expect(earlierAbout(sessions, groups.sessions[0]).map((s) => s.title)).toEqual([
      'recession radar v5',
      'Recession Radar in bonds',
    ]);
    expect(earlierAbout(sessions, ACCOUNT_SUBJECT)).toEqual([]);
  });
});
