/** What a Copilot question is about (page2 A), and the questions written for its current state. */

/** What another screen passes to `openCopilot`; a marker carries its session id and date. */
export interface CopilotContext {
  kind: 'session' | 'strategy' | 'account' | 'marker';
  id: string;
  /** ISO date of a marker, e.g. "2026-11-17". */
  date?: string;
}

export type SessionState = 'running' | 'waiting' | 'paused' | 'frozen' | 'stopped' | 'error';

export interface SessionInput {
  id: string;
  strategyId: string;
  name: string;
  live: boolean;
  state: SessionState;
  version?: number;
}

export interface StrategyInput {
  id: string;
  name: string;
  draft: boolean;
  version?: number;
  /** At least one completed backtest. */
  backtested: boolean;
}

export type SubjectState = SessionState | 'draft' | 'backtested' | 'untested';

export interface CopilotSubject {
  key: string;
  kind: 'account' | 'session' | 'strategy';
  id: string;
  name: string;
  live?: boolean;
  state?: SubjectState;
  version?: number;
  /** The strategy Copilot is given as context. */
  strategyId?: string;
}

export const ACCOUNT_SUBJECT: CopilotSubject = { key: 'account', kind: 'account', id: 'account', name: 'Account' };

const OPEN: readonly SessionState[] = ['frozen', 'error', 'running', 'waiting', 'paused'];

/** Account first, then open sessions (attention first), stopped sessions, then strategies not in a session. */
export function buildSubjects(sessions: readonly SessionInput[], strategies: readonly StrategyInput[]): CopilotSubject[] {
  const rank = (s: SessionInput) => {
    const i = OPEN.indexOf(s.state);
    return i < 0 ? OPEN.length : i;
  };
  const inSession = new Set(sessions.map((s) => s.strategyId));
  const sessionSubjects = [...sessions]
    .sort((a, b) => rank(a) - rank(b))
    .map<CopilotSubject>((s) => ({
      key: `session:${s.id}`,
      kind: 'session',
      id: s.id,
      name: s.name,
      live: s.live,
      state: s.state,
      version: s.version,
      strategyId: s.strategyId,
    }));
  const strategySubjects = strategies
    .filter((s) => !inSession.has(s.id))
    .map<CopilotSubject>((s) => ({
      key: `strategy:${s.id}`,
      kind: 'strategy',
      id: s.id,
      name: s.name,
      state: s.draft ? 'draft' : s.backtested ? 'backtested' : 'untested',
      version: s.version,
      strategyId: s.id,
    }));
  return [ACCOUNT_SUBJECT, ...sessionSubjects, ...strategySubjects];
}

/** The subject a context names; a strategy that runs as a session resolves to that session. */
export function subjectFor(context: CopilotContext | null, subjects: readonly CopilotSubject[]): CopilotSubject {
  if (!context || context.kind === 'account') return ACCOUNT_SUBJECT;
  if (context.kind === 'strategy') {
    return (
      subjects.find((s) => s.kind === 'strategy' && s.id === context.id) ??
      subjects.find((s) => s.kind === 'session' && s.strategyId === context.id && s.state !== 'stopped') ??
      ACCOUNT_SUBJECT
    );
  }
  return subjects.find((s) => s.kind === 'session' && s.id === context.id) ?? ACCOUNT_SUBJECT;
}

const STATE_LABEL: Record<SubjectState, string> = {
  running: 'Running',
  waiting: 'Waiting for data',
  paused: 'Paused',
  frozen: 'Frozen',
  stopped: 'Stopped',
  error: 'Error',
  draft: 'Draft',
  backtested: 'Backtested, never run',
  untested: 'Not backtested yet',
};

export function subjectStateLabel(state: SubjectState): string {
  return STATE_LABEL[state];
}

/** One sentence on what Copilot reads for the subject, limited to the tools the agent has. */
export function subjectReads(subject: CopilotSubject): string {
  const version = subject.version ? `version ${subject.version} of the strategy` : 'the strategy';
  switch (subject.kind) {
    case 'session':
      return `Copilot reads ${version}, positions across your account, account performance against SPY and this strategy's backtests. It can't read this session's fills on their own yet.`;
    case 'strategy':
      return `Copilot reads ${version}, its backtests and details of the symbols it holds. Nothing is saved until you choose to save it.`;
    case 'account':
      return 'Copilot reads your account summary, positions, performance against SPY and your strategies. It can’t place or cancel orders.';
  }
}

export type QuestionIcon = 'clock' | 'why' | 'chart' | 'draft' | 'test';

export interface SubjectQuestion {
  icon: QuestionIcon;
  text: string;
}

/** Questions written for the subject's current state; none assume a run that didn't happen. */
export function subjectQuestions(subject: CopilotSubject): SubjectQuestion[] {
  const n = subject.name;
  if (subject.kind === 'account') {
    return [
      { icon: 'why', text: 'Why did my account move today?' },
      { icon: 'chart', text: 'Which session has done best since it started?' },
      { icon: 'clock', text: 'What runs before the close today?' },
      { icon: 'draft', text: 'Draft a strategy that balances what I already hold' },
    ];
  }
  switch (subject.state) {
    case 'frozen':
    case 'error':
      return [
        { icon: 'why', text: `Why is ${n} ${subject.state === 'frozen' ? 'frozen' : 'showing an error'}?` },
        { icon: 'clock', text: `What happens to ${n} until it's resolved?` },
        { icon: 'chart', text: `How has ${n} done since it started?` },
      ];
    case 'running':
    case 'waiting':
      return [
        { icon: 'clock', text: `What will ${n}'s next rebalance do?` },
        { icon: 'why', text: `Why does ${n} hold what it holds now?` },
        { icon: 'chart', text: `How does ${n} compare with its backtest?` },
        { icon: 'draft', text: `Draft a version of ${n} that switches less often` },
      ];
    case 'paused':
      return [
        { icon: 'clock', text: `What happens when I resume ${n}?` },
        { icon: 'why', text: `Why does ${n} hold what it holds now?` },
        { icon: 'chart', text: `How has ${n} done since it started?` },
      ];
    case 'stopped':
      return [
        { icon: 'chart', text: `How did ${n} do while it ran?` },
        { icon: 'why', text: `What would ${n} hold today?` },
        { icon: 'draft', text: `Draft a version of ${n} to try on paper` },
      ];
    case 'backtested':
      return [
        { icon: 'why', text: `Explain how ${n} decides what to hold` },
        { icon: 'chart', text: `What hurt ${n} most in its backtest?` },
        { icon: 'test', text: `Backtest ${n} over the last five years` },
      ];
    case 'draft':
    case 'untested':
    default:
      return [
        { icon: 'why', text: `Explain how ${n} decides what to hold` },
        { icon: 'test', text: `Backtest ${n} over the last five years` },
        { icon: 'draft', text: `What would make ${n} switch less often?` },
      ];
  }
}

/** The subject's questions not yet asked in the thread. */
export function followUps(subject: CopilotSubject, asked: readonly string[], limit = 2): string[] {
  const seen = new Set(asked.map((a) => a.trim().toLowerCase()));
  return subjectQuestions(subject)
    .map((q) => q.text)
    .filter((q) => !seen.has(q.toLowerCase()))
    .slice(0, limit);
}

export function askPlaceholder(subject: CopilotSubject): string {
  return subject.kind === 'account' ? 'Ask about your account' : `Ask about ${subject.name}`;
}
