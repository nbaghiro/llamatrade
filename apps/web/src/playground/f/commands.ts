import { BACKTESTS, SESSIONS, STRATEGIES, stateLabel, strategyById, type Strategy } from '../data';

import type { Action } from './copilotContext';
import { pts, to } from './model';

export type Group = 'Run' | 'Jump' | 'Ask';

export interface Result {
  id: string;
  group: Group;
  label: string;
  detail?: string;
  key?: string;
  action: Action;
}

export const PAGES = [
  { label: 'Today', path: '', key: '1' },
  { label: 'Strategies', path: '/strategies', key: '2' },
  { label: 'Backtests', path: '/backtests', key: '3' },
  { label: 'Sessions', path: '/sessions', key: '4' },
  { label: 'Portfolio', path: '/portfolio', key: '5' },
] as const;

const INDEX: Result[] = [
  ...PAGES.map((p) => ({
    id: `page-${p.label}`,
    group: 'Jump' as const,
    label: p.label,
    detail: 'page',
    key: p.key,
    action: { type: 'go' as const, to: to(p.path) },
  })),
  ...STRATEGIES.map((s) => ({
    id: `st-${s.id}`,
    group: 'Jump' as const,
    label: s.name,
    detail: `strategy · v${s.version} · ${stateLabel(s).toLowerCase()}`,
    action: { type: 'go' as const, to: to(`/strategies/${s.id}`) },
  })),
  ...SESSIONS.map((s) => ({
    id: `ses-${s.id}`,
    group: 'Jump' as const,
    label: `${strategyById(s.strategyId)?.name} session`,
    detail: `session · ${s.mode}${s.stoppedOn ? ` · stopped ${s.stoppedOn}` : ''}`,
    action: { type: 'go' as const, to: to(`/sessions/${s.id}`) },
  })),
  ...BACKTESTS.map((b) => ({
    id: `bt-${b.id}`,
    group: 'Jump' as const,
    label: `${strategyById(b.strategyId)?.name} backtest v${b.version}`,
    detail: `backtest · ${pts(b.ret * 100)} · ran ${b.ran}`,
    action: { type: 'go' as const, to: to(`/backtests/${b.id}`) },
  })),
];

const words = (s: string) => s.toLowerCase().split(/\s+/).filter(Boolean);

function matches(label: string, q: string) {
  const l = label.toLowerCase();
  return words(q).every((w) => l.split(/[\s-]+/).some((p) => p.startsWith(w)) || l.includes(w));
}

export function findStrategy(text: string): Strategy | undefined {
  const ws = words(text);
  let best: Strategy | undefined;
  let score = 0;
  for (const s of STRATEGIES) {
    const name = s.name.toLowerCase();
    const sc = ws.filter((w) => name.includes(w)).length;
    if (sc > score) {
      score = sc;
      best = s;
    }
  }
  return best;
}

const QUESTION =
  /^(why|what|how|should|can|could|is|are|draft|lower|raise|make|suggest|explain|write|build a|create)\b/i;

export const SUGGESTED: Result[] = [
  {
    id: 's-why',
    group: 'Ask',
    label: 'Why is the account down today?',
    action: { type: 'ask', prompt: 'Why is the account down today?' },
  },
  {
    id: 's-bt',
    group: 'Run',
    label: 'backtest recession radar 5y',
    detail: 'quick run',
    action: { type: 'backtest', strategyId: 'recession-radar', years: 5 },
  },
  {
    id: 's-gold',
    group: 'Ask',
    label: "Lower Recession Radar's gold to 30%",
    action: { type: 'ask', prompt: "Lower Recession Radar's gold to 30%" },
  },
  {
    id: 's-draft',
    group: 'Ask',
    label: 'Draft a trend strategy on QQQ',
    action: { type: 'ask', prompt: 'Draft a trend strategy on QQQ' },
  },
];

function command(q: string): Result | null {
  const bt = q.match(/^(?:backtest|bt|test)\s+(.+?)(?:\s+(\d+)\s*y(?:ears?|rs?)?)?$/i);
  if (bt) {
    const s = findStrategy(bt[1]);
    if (!s) return null;
    const years = Math.max(1, Math.min(10, Number(bt[2] ?? 2)));
    return {
      id: 'cmd-bt',
      group: 'Run',
      label: `Backtest ${s.name} over ${years} ${years === 1 ? 'year' : 'years'}`,
      detail: `v${s.version} · against SPY`,
      action: { type: 'backtest', strategyId: s.id, years },
    };
  }
  const edit = q.match(/^(?:edit|open|build)\s+(.+)$/i);
  if (edit) {
    const s = findStrategy(edit[1]);
    if (!s) return null;
    return {
      id: 'cmd-edit',
      group: 'Run',
      label: `Edit ${s.name}`,
      detail: 'outline builder',
      action: { type: 'go', to: to(`/strategies/${s.id}`) },
    };
  }
  return null;
}

/** What the command bar offers for a query, best first. */
export function results(query: string, context?: string): Result[] {
  const q = query.trim();
  if (!q) return [...SUGGESTED, ...INDEX.slice(0, PAGES.length)];
  const ask: Result = {
    id: 'ask',
    group: 'Ask',
    label: q,
    detail: context ? `about ${strategyById(context)?.name ?? 'this page'}` : 'Copilot',
    action: { type: 'ask', prompt: q, context },
  };
  const jumps = INDEX.filter((r) => matches(r.label, q)).slice(0, 6);
  const cmd = command(q);
  if (cmd) return [cmd, ask, ...jumps];
  if (q.endsWith('?') || QUESTION.test(q) || words(q).length > 4) return [ask, ...jumps];
  return [...jumps, ask];
}
