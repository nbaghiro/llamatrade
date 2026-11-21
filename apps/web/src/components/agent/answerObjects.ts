import { MessageRole, type AgentMessage } from '@llamatrade/core/stores/agent';

import { describeSource } from './sources';

type ToolCall = AgentMessage['toolCalls'][number];
type Json = Record<string, unknown>;

export interface HoldingRow {
  symbol: string;
  quantity: number;
  value: number;
  /** Share of the listed positions' market value, 0 to 1. */
  weight: number;
}

/** A record an answer read, drawn as a card in the reader (history2 A). */
export type AnswerObject =
  | { kind: 'holdings'; n: number; rows: HoldingRow[]; more: number }
  | {
      kind: 'strategy';
      n: number;
      name: string;
      version: string;
      status: string;
      symbols: string[];
      href: string | null;
    }
  | {
      kind: 'backtest';
      n: number;
      title: string;
      figures: { label: string; value: string }[];
      href: string | null;
    };

/** The small picture beside a search result: what the conversation was about. */
export type ResultPicture =
  | { kind: 'holdings'; rows: HoldingRow[] }
  | { kind: 'symbols'; symbols: string[] }
  | { kind: 'none' };

function parse(raw: string): Json | null {
  try {
    const v: unknown = JSON.parse(raw);
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as Json) : null;
  } catch {
    return null;
  }
}

const str = (v: unknown): string =>
  typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '';
const num = (v: unknown): number => {
  const n = Number(str(v));
  return Number.isFinite(n) ? n : 0;
};

const MAX_ROWS = 4;

export function holdings(data: Json): HoldingRow[] {
  const list = Array.isArray(data.positions) ? data.positions : [];
  const rows = list
    .filter((p): p is Json => !!p && typeof p === 'object')
    .map((p) => ({
      symbol: str(p.symbol),
      quantity: num(p.quantity ?? p.qty),
      value: Math.abs(num(p.market_value)),
    }))
    .filter((r) => r.symbol !== '' && r.quantity !== 0);
  const total = rows.reduce((s, r) => s + r.value, 0);
  return rows
    .map((r) => ({ ...r, weight: total > 0 ? r.value / total : 0 }))
    .sort((a, b) => b.value - a.value);
}

function objectFor(tc: ToolCall, n: number): AnswerObject | null {
  if (!tc.success) return null;
  const data = parse(tc.resultJson);
  if (!data) return null;
  switch (tc.name) {
    case 'get_positions': {
      const rows = holdings(data);
      return rows.length
        ? {
            kind: 'holdings',
            n,
            rows: rows.slice(0, MAX_ROWS),
            more: Math.max(0, rows.length - MAX_ROWS),
          }
        : null;
    }
    case 'get_strategy': {
      const name = str(data.name);
      if (!name) return null;
      return {
        kind: 'strategy',
        n,
        name,
        version: str(data.version),
        status: str(data.status).toLowerCase(),
        symbols: (Array.isArray(data.symbols) ? data.symbols : []).map(str).filter(Boolean),
        href: describeSource(tc).href,
      };
    }
    case 'get_backtest_results': {
      const view = describeSource(tc);
      return view.rows.length
        ? {
            kind: 'backtest',
            n,
            title: view.title,
            figures: view.rows.slice(0, 4),
            href: view.href,
          }
        : null;
    }
    default:
      return null;
  }
}

/** The cards for what one answer read, numbered from `firstSource` like its citations. */
export function answerObjects(message: AgentMessage, firstSource = 1): AnswerObject[] {
  if (message.role === MessageRole.USER) return [];
  return (message.toolCalls ?? [])
    .map((tc, i) => objectFor(tc, firstSource + i))
    .filter((o): o is AnswerObject => o !== null);
}

/** Every piece of text on a card, for marking the card that matches a search. */
export function objectText(o: AnswerObject): string {
  switch (o.kind) {
    case 'holdings':
      return o.rows.map((r) => r.symbol).join(' ');
    case 'strategy':
      return [o.name, o.status, ...o.symbols].join(' ');
    case 'backtest':
      return [o.title, ...o.figures.map((f) => `${f.label} ${f.value}`)].join(' ');
  }
}

/** The latest record a conversation read that can be drawn small: holdings or a rule's symbols. */
export function resultPicture(messages: readonly AgentMessage[]): ResultPicture {
  for (let i = messages.length - 1; i >= 0; i--) {
    const objects = answerObjects(messages[i]).reverse();
    for (const o of objects) {
      if (o.kind === 'holdings') return { kind: 'holdings', rows: o.rows.slice(0, 3) };
      if (o.kind === 'strategy' && o.symbols.length) {
        return { kind: 'symbols', symbols: o.symbols.slice(0, 3) };
      }
    }
  }
  return { kind: 'none' };
}
