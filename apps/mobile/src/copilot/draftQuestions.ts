/**
 * Questions-first drafting (builder/draft2 B). Until the agent has a structured questions tool,
 * Copilot is asked to reply with its questions as JSON in a fenced `draft-questions` block.
 * The same instruction and block format as the web app, so a thread reads the same on both.
 */

export interface DraftQuestion {
  id: string;
  label: string;
  help: string;
  short: string;
  options: string[];
  /** The option Copilot would pick. */
  preset: string;
}

export interface DraftAsk {
  intro: string;
  questions: DraftQuestion[];
}

export const MAX_QUESTIONS = 4;
const MAX_OPTIONS = 5;
const FENCE = 'draft-questions';

export const DRAFT_INSTRUCTION = [
  '(Before you write the draft, check the details that would change how this strategy trades:',
  `at most ${MAX_QUESTIONS} questions. Reply with one or two short sentences, then a fenced code`,
  `block tagged ${FENCE} holding JSON shaped like {"questions":[{"id":"lookback","label":"How is`,
  'strongest measured?","short":"Strongest over","help":"The return over this period ranks the',
  'ETFs.","options":["3 months","90 days","6 months"],"default":"90 days"}]}. Use "default" for',
  'the option you would pick. If nothing is unclear, write the draft straight away.)',
].join(' ');

export function draftRequest(description: string): string {
  return `${description.trim()}\n\n${DRAFT_INSTRUCTION}`;
}

/** The person's own words from a draft request. */
export function stripDraftInstruction(content: string): string {
  const i = content.indexOf(DRAFT_INSTRUCTION);
  return i < 0 ? content : content.slice(0, i).trimEnd();
}

const BLOCK = new RegExp('```(?:' + FENCE + '|json)\\s*\\n([\\s\\S]*?)```', 'i');
const str = (v: unknown): string => (typeof v === 'string' ? v.trim() : '');

function readQuestion(raw: unknown, i: number): DraftQuestion | null {
  if (!raw || typeof raw !== 'object') return null;
  const q = raw as Record<string, unknown>;
  const label = str(q.label);
  const options = (Array.isArray(q.options) ? q.options : [])
    .map(str)
    .filter((o, j, all) => o !== '' && all.indexOf(o) === j)
    .slice(0, MAX_OPTIONS);
  if (!label || options.length < 2) return null;
  const wanted = str(q.default);
  return {
    id: str(q.id) || `q${i + 1}`,
    label,
    help: str(q.help),
    short: str(q.short) || label,
    options,
    preset: options.includes(wanted) ? wanted : options[0],
  };
}

/** The questions block from a reply; null when missing, invalid, or without a usable question. */
export function parseDraftQuestions(content: string): DraftAsk | null {
  const match = content.match(BLOCK);
  if (!match) return null;
  let data: unknown;
  try {
    data = JSON.parse(match[1]);
  } catch {
    return null;
  }
  const list = data && typeof data === 'object' && !Array.isArray(data) ? (data as Record<string, unknown>).questions : data;
  if (!Array.isArray(list)) return null;
  const questions = list
    .map(readQuestion)
    .filter((q): q is DraftQuestion => q !== null)
    .slice(0, MAX_QUESTIONS);
  if (!questions.length) return null;
  const intro = content.replace(match[0], '').replace(/\n{3,}/g, '\n\n').trim();
  return { intro, questions };
}

/** Streaming text with a half-written questions block cut off. */
export function hideDraftBlock(content: string): string {
  const i = content.search(new RegExp('```(?:' + FENCE + ')', 'i'));
  return i < 0 ? content : content.slice(0, i).trimEnd();
}

export type DraftPicks = Record<string, string>;

export function presetPicks(questions: readonly DraftQuestion[]): DraftPicks {
  return Object.fromEntries(questions.map((q) => [q.id, q.preset]));
}

export function answersMessage(questions: readonly DraftQuestion[], picks: DraftPicks): string {
  const lines = questions.map((q) => `- ${q.label} ${picks[q.id] ?? q.preset}`);
  return ['Draft it with these choices:', ...lines].join('\n');
}

export const DEFAULTS_MESSAGE = 'Use the option you would pick for each, and write the draft.';

/** The answers the person changed from Copilot's pick. */
export function changedAnswers(questions: readonly DraftQuestion[], picks: DraftPicks): string[] {
  return questions.filter((q) => picks[q.id] && picks[q.id] !== q.preset).map((q) => picks[q.id]);
}

const ASKING =
  /^(why|what|how|when|where|which|who|is|are|does|do|did|can|could|should|would|will|explain|compare|backtest|test|show|tell|list|summari[sz]e|find)\b/i;
const DESCRIBING =
  /^(hold|buy|own|rotate|draft|build|create|make|write|design|invest|allocate|split|keep|go|move|switch|trade|track|follow|a|an)\b/i;

/** True when composer text reads as a strategy to draft rather than a question. */
export function looksLikeDraft(text: string): boolean {
  const t = text.trim();
  if (t.length < 12 || t.includes('?')) return false;
  if (ASKING.test(t)) return false;
  return DESCRIBING.test(t);
}

const CADENCE = /\b(daily|weekly|monthly|quarterly|annually|yearly)\b/gi;
const SYMBOL = /\b[A-Z]{2,5}\b/g;
const NUMBER = /\b\d+(?:\.\d+)?\b/g;
const SKIP = new Set(['ETF', 'ETFS', 'SPDR', 'SPDRS', 'RSI', 'SMA', 'EMA', 'IF', 'AND', 'OR', 'THE']);

/** Symbols, numbers and cadence words in a line: the values a person could have chosen. */
export function valueTokens(text: string): string[] {
  const out = new Set<string>();
  for (const m of text.match(SYMBOL) ?? []) if (!SKIP.has(m)) out.add(m);
  for (const m of text.match(NUMBER) ?? []) out.add(m);
  for (const m of text.match(CADENCE) ?? []) out.add(m.toLowerCase());
  return [...out];
}

/** Values the person named, matching symbols whether they typed them in capitals or not. */
function said(words: readonly string[]): Set<string> {
  return new Set(words.flatMap((w) => [...valueTokens(w), ...valueTokens(w.toUpperCase())]));
}

export type BlockAuthor = 'you' | 'copilot' | null;

/**
 * Who chose each value in a drafted block: "you" when every value in it came from the person's
 * words or an answer they changed, "copilot" when any value came from neither, null when the
 * block holds no values. Per-block notes from the agent would replace this reading.
 */
export function blockAuthor(line: string, personWords: readonly string[]): BlockAuthor {
  const tokens = valueTokens(line);
  if (!tokens.length) return null;
  const known = said(personWords);
  return tokens.every((t) => known.has(t)) ? 'you' : 'copilot';
}
