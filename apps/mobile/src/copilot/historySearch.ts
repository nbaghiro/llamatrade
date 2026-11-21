/** Search over what was said in earlier conversations (history2 A), run on the phone over loaded messages. */
import { stripDraftInstruction } from './draftQuestions.ts';

export interface SearchMessage {
  id: string;
  user: boolean;
  content: string;
}

export interface SearchableConversation {
  id: string;
  title: string;
  messages: readonly SearchMessage[];
}

export interface SearchHit {
  sessionId: string;
  messageId: string;
  /** The matching paragraph; empty for a title-only match. */
  text: string;
}

/** A reply's readable paragraphs, without code, citation markers or markdown marks. */
export function paragraphs(content: string): string[] {
  return stripDraftInstruction(content)
    .replace(/```[\s\S]*?```/g, '')
    .replace(/\s?\[\d{1,2}(?:\s*,\s*\d{1,2})*\](?!\()/g, '')
    .split(/\n\s*\n/)
    .map((p) =>
      p
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/^#{1,6}\s+/gm, '')
        .replace(/^\s*[-*]\s+/gm, '')
        .trim(),
    )
    .filter(Boolean);
}

/** The first matching paragraph, searching Copilot's replies before the questions, then the title. */
export function searchConversation(convo: SearchableConversation, query: string): SearchHit | null {
  const q = query.trim().toLowerCase();
  if (!q) return null;
  const ordered = [...convo.messages.filter((m) => !m.user), ...convo.messages.filter((m) => m.user)];
  for (const m of ordered) {
    const hit = paragraphs(m.content).find((p) => p.toLowerCase().includes(q));
    if (hit) return { sessionId: convo.id, messageId: m.id, text: hit };
  }
  if (convo.title.toLowerCase().includes(q)) return { sessionId: convo.id, messageId: '', text: '' };
  return null;
}

/** A window of about `max` characters around the first match, with ellipses where cut. */
export function excerpt(text: string, query: string, max = 110): string {
  if (text.length <= max) return text;
  const i = text.toLowerCase().indexOf(query.trim().toLowerCase());
  const start = i < 0 ? 0 : Math.max(0, Math.min(i - Math.floor(max / 3), text.length - max));
  const end = Math.min(text.length, start + max);
  return `${start > 0 ? '…' : ''}${text.slice(start, end).trim()}${end < text.length ? '…' : ''}`;
}

export interface HighlightPart {
  text: string;
  match: boolean;
}

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

/** "3 answers mention SMH". */
export function hitsLabel(count: number, query: string): string {
  const q = query.trim();
  if (count === 0) return `Nothing you've asked mentions ${q}.`;
  return `${count} ${count === 1 ? 'answer mentions' : 'answers mention'} ${q}`;
}
