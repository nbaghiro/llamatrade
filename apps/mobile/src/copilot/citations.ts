/**
 * Citations in an answer (explain2 A). The agent has no structured citations yet, so markers
 * like "[2]" are read from the text, and each tool call in the thread is a numbered source.
 */

export type CitedPart = { text: string } | { n: number };

/** "[2]" or "[1, 3]"; a bracket followed by "(" is a markdown link. */
const MARKER = /\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g;

export function splitCitations(text: string): CitedPart[] {
  const parts: CitedPart[] = [];
  let at = 0;
  for (const m of text.matchAll(MARKER)) {
    const i = m.index ?? 0;
    if (i > at) parts.push({ text: text.slice(at, i) });
    for (const n of m[1].split(',')) parts.push({ n: Number(n.trim()) });
    at = i + m[0].length;
  }
  if (at < text.length) parts.push({ text: text.slice(at) });
  return parts;
}

/** Distinct citation numbers in order of first appearance. */
export function citationNumbers(text: string): number[] {
  const seen: number[] = [];
  for (const p of splitCitations(text)) {
    if ('n' in p && !seen.includes(p.n)) seen.push(p.n);
  }
  return seen;
}

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const DATE =
  /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b|\b(today|this morning|this afternoon)\b/i;

export interface DatedCitation {
  n: number;
  at: Date;
  /** The date as the answer wrote it. */
  said: string;
}

function resolveDate(match: RegExpMatchArray, today: Date): Date | null {
  if (match[4]) return new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const month = MONTHS.indexOf(match[1].slice(0, 3).toLowerCase());
  const day = Number(match[2]);
  if (month < 0 || day < 1 || day > 31) return null;
  if (match[3]) return new Date(Number(match[3]), month, day);
  const sameYear = new Date(today.getFullYear(), month, day);
  return sameYear.getTime() > today.getTime() ? new Date(today.getFullYear() - 1, month, day) : sameYear;
}

/** Citations whose sentence names a date, placed once on the first date found. */
export function datedCitations(content: string, today: Date): DatedCitation[] {
  const out: DatedCitation[] = [];
  const sentences = content.replace(/```[\s\S]*?```/g, '').split(/(?<=[.!?])\s+|\n+/);
  for (const sentence of sentences) {
    const numbers = citationNumbers(sentence);
    if (!numbers.length) continue;
    const match = sentence.match(DATE);
    if (!match) continue;
    const at = resolveDate(match, today);
    if (!at) continue;
    for (const n of numbers) {
      if (!out.some((c) => c.n === n)) out.push({ n, at, said: match[0].trim() });
    }
  }
  return out;
}

const TITLES: Record<string, string> = {
  get_strategy: 'Rule',
  list_strategies: 'Your strategies',
  list_templates: 'Templates',
  get_backtest_results: 'Backtest result',
  list_backtests: 'Backtests',
  run_backtest: 'Backtest run',
  get_portfolio_summary: 'Account summary',
  get_portfolio_performance: 'Performance',
  get_positions: 'Positions',
  validate_dsl: 'Strategy check',
  get_asset_info: 'Asset details',
  recall_memory: 'Earlier conversations',
  get_user_profile: 'Your profile',
  search_past_strategies: 'Past strategies',
};

export function sourceTitle(tool: string): string {
  return TITLES[tool] ?? tool.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

export interface SourceMessage {
  id: string;
  user: boolean;
  tools: readonly { name: string; success: boolean }[];
}

export interface Source {
  n: number;
  messageId: string;
  tool: string;
  title: string;
  ok: boolean;
}

/** Each tool call in the thread as a source, numbered across the thread in order. */
export function threadSources(messages: readonly SourceMessage[]): Source[] {
  const out: Source[] = [];
  for (const m of messages) {
    if (m.user) continue;
    for (const t of m.tools) {
      out.push({ n: out.length + 1, messageId: m.id, tool: t.name, title: sourceTitle(t.name), ok: t.success });
    }
  }
  return out;
}

/** "3 sources", "1 source". */
export function sourcesLabel(count: number): string {
  return count === 1 ? '1 source' : `${count} sources`;
}

/** The index of the last point on or before `at`'s day, or -1 when `at` is outside the series. */
export function pinIndex(times: readonly number[], at: Date): number {
  if (!times.length) return -1;
  const end = new Date(at.getFullYear(), at.getMonth(), at.getDate() + 1).getTime();
  if (end <= times[0] || at.getTime() > times[times.length - 1] + 86_400_000) return -1;
  let found = -1;
  for (let i = 0; i < times.length; i++) {
    if (times[i] < end) found = i;
    else break;
  }
  return found;
}
