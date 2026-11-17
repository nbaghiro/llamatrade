import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus, type Strategy } from '@llamatrade/core/proto/strategy_pb';

import { dayLabel, rowNextRebalance, type SessionRow } from '../sessions/sessionRows';

export type SubjectKind = 'account' | 'session' | 'strategy' | 'backtest';

/** Something the person can ask Copilot about: the account, a session, a strategy or a backtest. */
export interface CopilotSubject {
  key: string;
  kind: SubjectKind;
  id: string;
  name: string;
  /** The short state at the right of the rail row: "Live", "Frozen", "Draft", "Nov 13". */
  meta: string;
  tone: 'accent' | 'risk' | 'muted' | 'none';
  mode?: 'live' | 'paper';
  /** The page that shows this subject in full. */
  href: string;
  /** The strategy Copilot is given as context for questions about this subject. */
  strategyId?: string;
  strategyName?: string;
  rebalance?: string;
  version?: number;
  /** The next scheduled rebalance, for running sessions. */
  next?: Date | null;
  /** A session's run state in words: "Running", "Frozen". */
  state?: string;
}

export const ACCOUNT_SUBJECT: CopilotSubject = {
  key: 'account',
  kind: 'account',
  id: 'account',
  name: 'Your account',
  meta: '',
  tone: 'none',
  href: '/portfolio',
};

const SESSION_META: Record<SessionRow['state'], string> = {
  running: 'Running',
  starting: 'Starting',
  paused: 'Paused',
  frozen: 'Frozen',
  stopped: 'Stopped',
  error: 'Error',
};

export function sessionSubject(row: SessionRow, today: Date): CopilotSubject {
  const live = row.session.mode === ExecutionMode.LIVE;
  const next = rowNextRebalance(row, today);
  const meta =
    row.state === 'running'
      ? live
        ? 'Live'
        : next
          ? dayLabel(next)
          : 'Paper'
      : SESSION_META[row.state];
  return {
    key: `session:${row.session.id}`,
    kind: 'session',
    id: row.session.id,
    name: row.name,
    meta,
    tone: row.view.attention ? 'risk' : row.view.open ? 'accent' : 'muted',
    mode: live ? 'live' : 'paper',
    href: `/trading/${row.session.id}`,
    strategyId: row.session.strategyId,
    strategyName: row.name,
    rebalance: row.rebalance,
    version: row.version || undefined,
    next,
    state: SESSION_META[row.state],
  };
}

export function strategySubject(s: Strategy): CopilotSubject {
  const draft = s.status === StrategyStatus.DRAFT;
  return {
    key: `strategy:${s.id}`,
    kind: 'strategy',
    id: s.id,
    name: s.name,
    meta: draft ? 'Draft' : s.version ? `v${s.version}` : '',
    tone: 'none',
    href: `/strategies/${s.id}`,
    strategyId: s.id,
    strategyName: s.name,
    rebalance: s.rebalance,
    version: s.version || undefined,
  };
}

function shortDate(seconds: bigint | undefined): string {
  if (!seconds) return '';
  return new Date(Number(seconds) * 1000).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

export function backtestSubject(run: BacktestRun, strategyName: string): CopilotSubject {
  const version = run.strategyVersion ? ` v${run.strategyVersion}` : '';
  return {
    key: `backtest:${run.id}`,
    kind: 'backtest',
    id: run.id,
    name: `${strategyName || 'Backtest'}${version}`,
    meta: shortDate((run.completedAt ?? run.createdAt)?.seconds),
    tone: 'none',
    href: `/backtest/${run.id}`,
    strategyId: run.strategyId,
    strategyName: strategyName || undefined,
    version: run.strategyVersion || undefined,
  };
}

export interface SubjectGroups {
  sessions: CopilotSubject[];
  strategies: CopilotSubject[];
  backtests: CopilotSubject[];
}

/**
 * The rail's lists: every session, the strategies not already running as a session (newest
 * first, at most `limit`) and the latest completed backtests.
 */
export function buildSubjects(
  rows: readonly SessionRow[],
  strategies: readonly Strategy[],
  runs: readonly BacktestRun[],
  today: Date,
  limit = 4
): SubjectGroups {
  const running = new Set(rows.filter((r) => r.view.open).map((r) => r.session.strategyId));
  const names = new Map(strategies.map((s) => [s.id, s.name] as const));
  const updated = (s: Strategy) => Number(s.updatedAt?.seconds ?? s.createdAt?.seconds ?? 0n);
  return {
    sessions: rows.map((r) => sessionSubject(r, today)),
    strategies: strategies
      .filter((s) => !running.has(s.id) && s.status !== StrategyStatus.ARCHIVED)
      .sort((a, b) => updated(b) - updated(a))
      .slice(0, limit)
      .map(strategySubject),
    backtests: runs
      .filter((r) => r.status === BacktestStatus.COMPLETED)
      .slice(0, limit)
      .map((r) => backtestSubject(r, names.get(r.strategyId) ?? '')),
  };
}

export function findSubject(groups: SubjectGroups, key: string | null): CopilotSubject | null {
  if (!key) return null;
  if (key === ACCOUNT_SUBJECT.key) return ACCOUNT_SUBJECT;
  return (
    [...groups.sessions, ...groups.strategies, ...groups.backtests].find((s) => s.key === key) ??
    null
  );
}

export type ReadIcon = 'code' | 'positions' | 'chart' | 'list' | 'backtest';

export interface SubjectRead {
  icon: ReadIcon;
  label: string;
  /** The tool Copilot uses to read it. */
  tool: string;
}

/** The records Copilot can read for a subject, limited to the tools the agent has. */
export function subjectReads(subject: CopilotSubject): SubjectRead[] {
  const strategy = (label: string): SubjectRead => ({ icon: 'code', label, tool: 'get_strategy' });
  const version = subject.version ? `, version ${subject.version}` : '';
  switch (subject.kind) {
    case 'session':
      return [
        strategy(`Strategy${version}`),
        { icon: 'positions', label: 'Positions across your account', tool: 'get_positions' },
        {
          icon: 'chart',
          label: 'Account performance against its benchmark',
          tool: 'get_portfolio_performance',
        },
        { icon: 'backtest', label: 'Backtests of this strategy', tool: 'list_backtests' },
      ];
    case 'strategy':
      return [
        strategy(`The strategy${version}`),
        { icon: 'backtest', label: 'Its backtests', tool: 'list_backtests' },
        { icon: 'list', label: 'Asset details for its symbols', tool: 'get_asset_info' },
      ];
    case 'backtest':
      return [
        { icon: 'backtest', label: 'The backtest result', tool: 'get_backtest_results' },
        strategy('The strategy it tested'),
      ];
    case 'account':
      return [
        { icon: 'chart', label: 'Account summary', tool: 'get_portfolio_summary' },
        { icon: 'positions', label: 'Positions', tool: 'get_positions' },
        {
          icon: 'chart',
          label: 'Performance against its benchmark',
          tool: 'get_portfolio_performance',
        },
        { icon: 'list', label: 'Your strategies', tool: 'list_strategies' },
      ];
  }
}

/** What the subject's reads leave out, said once under the list. */
export function subjectLimits(subject: CopilotSubject): string {
  if (subject.kind === 'session') {
    return "It can't read this session's fills or its sleeve on its own yet, and it can't place or cancel orders.";
  }
  if (subject.kind === 'account') {
    return "It can't read individual fills or your Alpaca keys, and it can't place or cancel orders.";
  }
  return "It can't place or cancel orders, and nothing is saved until you choose to save it.";
}

export type QuestionIcon = 'clock' | 'why' | 'chart' | 'draft' | 'test';

export interface SubjectQuestion {
  icon: QuestionIcon;
  text: string;
}

/** Questions written for the subject's current state. */
export function subjectQuestions(subject: CopilotSubject): SubjectQuestion[] {
  const n = subject.name;
  switch (subject.kind) {
    case 'session': {
      const out: SubjectQuestion[] = [];
      if (subject.tone === 'risk') out.push({ icon: 'why', text: `Why does ${n} need attention?` });
      if (subject.next) {
        out.push({ icon: 'clock', text: `What will the ${dayLabel(subject.next)} rebalance do?` });
      }
      out.push(
        { icon: 'why', text: `Why does ${n} hold what it holds now?` },
        { icon: 'chart', text: `How does ${n} compare with its last backtest?` },
        { icon: 'draft', text: `Draft a version of ${n} that switches less often` }
      );
      return out.slice(0, 5);
    }
    case 'strategy':
      return [
        { icon: 'why', text: `Explain how ${n} decides what to hold` },
        { icon: 'test', text: `Backtest ${n} over the last five years` },
        { icon: 'chart', text: `What would have hurt ${n} most in 2022?` },
        { icon: 'draft', text: `Draft a version of ${n} with a bond hedge` },
      ];
    case 'backtest':
      return [
        { icon: 'why', text: `Explain the largest drawdown in the ${n} backtest` },
        { icon: 'chart', text: `How did the ${n} backtest do against its benchmark?` },
        { icon: 'draft', text: `Suggest one change to ${n} and backtest it` },
      ];
    case 'account':
      return [
        { icon: 'why', text: 'Why did my account move today?' },
        { icon: 'chart', text: 'Which session has done best since it started?' },
        { icon: 'clock', text: 'What runs before the close today?' },
        { icon: 'draft', text: 'Draft a strategy that balances what I already hold' },
      ];
  }
}

/** Conversations whose title names the subject, newest first. */
export function earlierAbout<T extends { title: string; lastActivityAt?: { seconds: bigint } }>(
  sessions: readonly T[],
  subject: CopilotSubject
): T[] {
  if (subject.kind === 'account') return [];
  const name = subject.strategyName ?? subject.name;
  const needle = name.toLowerCase();
  return sessions
    .filter((s) => s.title.toLowerCase().includes(needle))
    .sort(
      (a, b) => Number(b.lastActivityAt?.seconds ?? 0n) - Number(a.lastActivityAt?.seconds ?? 0n)
    )
    .slice(0, 4);
}

export interface StarterGroup {
  label: 'Build' | 'Explain' | 'Test';
  prompts: string[];
}

/** The open canvas's starters, naming your own sessions and strategies where there are some. */
export function canvasStarters(groups: SubjectGroups): StarterGroup[] {
  const session = groups.sessions.find((s) => s.tone !== 'muted') ?? groups.sessions[0];
  const [first, second] = [...groups.sessions, ...groups.strategies]
    .map((s) => s.strategyName ?? s.name)
    .filter((name, i, all) => all.indexOf(name) === i);
  return [
    {
      label: 'Build',
      prompts: [
        'A momentum rotation across QQQ, XLK and SMH with a bond hedge',
        'An all-weather mix of VTI, VGLT, GLD and BND',
      ],
    },
    {
      label: 'Explain',
      prompts: [
        session
          ? `Why ${session.name} holds what it holds now`
          : 'How a rebalance decides what to buy',
        'What the risk checks do before an order',
      ],
    },
    {
      label: 'Test',
      prompts: [
        first
          ? `Backtest ${first} over five years`
          : 'Backtest a 60/40 mix of SPY and BND over five years',
        first && second
          ? `Compare ${first} with ${second} since 2020`
          : 'Compare a 60/40 mix with SPY since 2020',
      ],
    },
  ];
}

/** "Ask about Recession Radar", or "Ask about your account". */
export function askPlaceholder(subject: CopilotSubject): string {
  return subject.kind === 'account' ? 'Ask about your account' : `Ask about ${subject.name}`;
}
