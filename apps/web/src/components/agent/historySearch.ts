import { MessageRole, type AgentMessage } from '@llamatrade/core/stores/agent';

export type ConversationKind = 'explained' | 'drafts' | 'backtests';

export const KIND_LABEL: Record<ConversationKind, string> = {
  explained: 'Explained',
  drafts: 'Drafts',
  backtests: 'Backtests',
};

const BACKTEST_TOOLS = new Set(['run_backtest', 'get_backtest_results', 'list_backtests']);

/** What a conversation produced: drafts when Copilot wrote a strategy, backtests when it ran or read one. */
export function conversationKinds(messages: readonly AgentMessage[]): ConversationKind[] {
  let drafts = false;
  let backtests = false;
  let sources = 0;
  for (const m of messages) {
    if (m.role === MessageRole.USER) continue;
    if (m.inlineArtifactIds?.length) drafts = true;
    for (const tc of m.toolCalls ?? []) {
      sources += 1;
      if (BACKTEST_TOOLS.has(tc.name)) backtests = true;
    }
  }
  const kinds: ConversationKind[] = [];
  if (drafts) kinds.push('drafts');
  if (backtests) kinds.push('backtests');
  if (!kinds.length && sources > 0) kinds.push('explained');
  return kinds;
}

/** "Explained · 4 sources", "2 backtests", from what the conversation did. */
export function outcomeLabel(messages: readonly AgentMessage[]): string {
  const calls = messages.reduce(
    (n, m) => n + (m.role === MessageRole.USER ? 0 : (m.toolCalls?.length ?? 0)),
    0
  );
  const runs = messages.reduce(
    (n, m) => n + (m.toolCalls ?? []).filter((t) => t.name === 'run_backtest').length,
    0
  );
  const drafts = messages.reduce((n, m) => n + (m.inlineArtifactIds?.length ?? 0), 0);
  const parts: string[] = [];
  if (drafts) parts.push(drafts === 1 ? '1 draft' : `${drafts} drafts`);
  if (runs) parts.push(runs === 1 ? '1 backtest' : `${runs} backtests`);
  if (!parts.length && calls)
    parts.push(`Explained · ${calls === 1 ? '1 source' : `${calls} sources`}`);
  return parts.join(' · ');
}

/** Splits a reply into the paragraphs a search result can point at. */
export function paragraphs(content: string): string[] {
  return content
    .replace(/```[\s\S]*?```/g, '')
    .split(/\n\s*\n/)
    .map((p) =>
      p
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/^#{1,6}\s+/gm, '')
        .trim()
    )
    .filter(Boolean);
}

export interface SearchHit {
  sessionId: string;
  messageId: string;
  /** Index of the matching paragraph within its message. */
  paragraph: number;
  text: string;
}

export interface SearchableConversation {
  id: string;
  title: string;
  messages: readonly AgentMessage[];
}

/**
 * The first paragraph in each conversation that contains the query, ignoring case, searching
 * Copilot's replies first and then the questions. A title-only match points at no paragraph.
 */
export function searchConversation(convo: SearchableConversation, query: string): SearchHit | null {
  const q = query.trim().toLowerCase();
  if (!q) return null;
  const ordered = [
    ...convo.messages.filter((m) => m.role !== MessageRole.USER),
    ...convo.messages.filter((m) => m.role === MessageRole.USER),
  ];
  for (const m of ordered) {
    const paras = paragraphs(m.content);
    const i = paras.findIndex((p) => p.toLowerCase().includes(q));
    if (i >= 0) return { sessionId: convo.id, messageId: m.id, paragraph: i, text: paras[i] };
  }
  if (convo.title.toLowerCase().includes(q)) {
    return { sessionId: convo.id, messageId: '', paragraph: -1, text: '' };
  }
  return null;
}

export interface HighlightPart {
  text: string;
  match: boolean;
}

/** Splits text around every case-insensitive occurrence of the query. */
export function highlight(text: string, query: string): HighlightPart[] {
  const q = query.trim();
  if (!q) return [{ text, match: false }];
  const lower = text.toLowerCase();
  const needle = q.toLowerCase();
  const parts: HighlightPart[] = [];
  let at = 0;
  for (let i = lower.indexOf(needle); i >= 0; i = lower.indexOf(needle, at)) {
    if (i > at) parts.push({ text: text.slice(at, i), match: false });
    parts.push({ text: text.slice(i, i + q.length), match: true });
    at = i + q.length;
  }
  if (at < text.length) parts.push({ text: text.slice(at), match: false });
  return parts;
}
