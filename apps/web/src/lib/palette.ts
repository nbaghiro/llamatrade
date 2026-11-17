/** Ranking for the command palette: today, sessions, recent, strategies, pages and actions, with Ask Copilot last. */

export type PaletteKind =
  | 'today'
  | 'session'
  | 'recent'
  | 'strategy'
  | 'page'
  | 'action'
  | 'copilot';

export interface PaletteItem {
  id: string;
  kind: Exclude<PaletteKind, 'copilot'>;
  label: string;
  /** Extra words that should find this item but are not shown. */
  keywords?: readonly string[];
  hint?: string;
}

export interface PaletteResult {
  id: string;
  kind: PaletteKind;
  label: string;
  hint?: string;
  /** [start, end) ranges of `label` that matched the query. */
  matches: Array<[number, number]>;
  score: number;
}

export interface PaletteGroup {
  kind: PaletteKind;
  title: string;
  results: PaletteResult[];
}

export const GROUP_TITLES: Record<PaletteKind, string> = {
  today: 'Today',
  session: 'Sessions',
  recent: 'Recent',
  strategy: 'Strategies',
  page: 'Pages',
  action: 'Actions',
  copilot: 'Copilot',
};

const GROUP_ORDER: readonly PaletteKind[] = [
  'today',
  'session',
  'recent',
  'strategy',
  'page',
  'action',
  'copilot',
];

export const COPILOT_RESULT_ID = 'copilot:ask';

/** Substring and keyword matches score at least this; subsequence matches score below it. */
const DIRECT_MATCH = 300;

interface Match {
  score: number;
  ranges: Array<[number, number]>;
}

function isWordStart(text: string, i: number): boolean {
  return i === 0 || /[\s/›·,.(-]/.test(text[i - 1]);
}

/** Scores one text against a lower-cased query; null when it does not match. */
export function matchText(text: string, query: string): Match | null {
  const t = text.toLowerCase();
  if (!query) return { score: 0, ranges: [] };
  if (t === query) return { score: 1000, ranges: [[0, text.length]] };
  if (t.startsWith(query)) return { score: 800 - text.length, ranges: [[0, query.length]] };
  for (let i = t.indexOf(query); i >= 0; i = t.indexOf(query, i + 1)) {
    if (isWordStart(text, i)) return { score: 600 - i, ranges: [[i, i + query.length]] };
  }
  const at = t.indexOf(query);
  if (at >= 0) return { score: 400 - at, ranges: [[at, at + query.length]] };
  return subsequence(text, t, query);
}

/** Letters in order, starting at a word start, in at most a few runs. */
function subsequence(text: string, t: string, query: string): Match | null {
  const ranges: Array<[number, number]> = [];
  let from = 0;
  let gaps = 0;
  for (const ch of query) {
    if (ch === ' ') continue;
    let i = t.indexOf(ch, from);
    while (!ranges.length && i >= 0 && !isWordStart(text, i)) i = t.indexOf(ch, i + 1);
    if (i < 0) return null;
    const last = ranges[ranges.length - 1];
    if (last && last[1] === i) last[1] = i + 1;
    else {
      if (ranges.length) gaps += i - from;
      ranges.push([i, i + 1]);
    }
    from = i + 1;
  }
  if (ranges.length > Math.max(2, Math.ceil(query.length / 2))) return null;
  return { score: 200 - gaps - ranges.length * 10 - text.length / 10, ranges };
}

function scoreItem(item: PaletteItem, query: string): Match | null {
  const own = matchText(item.label, query);
  const viaKeyword = (item.keywords ?? []).some((k) => {
    const m = matchText(k, query);
    return m !== null && m.score >= 400;
  });
  if (own && (own.score >= 400 || !viaKeyword)) return own;
  if (viaKeyword) return { score: 300, ranges: [] };
  return own;
}

export interface RankOptions {
  /** Most results per group. */
  perGroup?: number;
  /** Items shown, in this order, when the query is empty. */
  emptyIds?: readonly string[];
}

/** Groups and orders matches; a non-empty query always ends with an Ask Copilot row. */
export function rankPalette(
  rawQuery: string,
  items: readonly PaletteItem[],
  { perGroup = 5, emptyIds }: RankOptions = {}
): PaletteGroup[] {
  const query = rawQuery.trim().toLowerCase().replace(/\s+/g, ' ');
  const scored: PaletteResult[] = [];
  if (!query) {
    const order = emptyIds ?? items.map((i) => i.id);
    order.forEach((id, n) => {
      const item = items.find((i) => i.id === id);
      if (item) scored.push({ ...toResult(item), score: -n, matches: [] });
    });
  } else {
    for (const item of items) {
      const m = scoreItem(item, query);
      if (m) scored.push({ ...toResult(item), score: m.score, matches: m.ranges });
    }
    if (scored.some((r) => r.score >= DIRECT_MATCH)) {
      const direct = scored.filter((r) => r.score >= DIRECT_MATCH);
      scored.length = 0;
      scored.push(...direct);
    }
  }

  const groups: PaletteGroup[] = [];
  for (const kind of GROUP_ORDER) {
    const results = scored
      .filter((r) => r.kind === kind)
      .sort((a, b) => b.score - a.score || a.label.localeCompare(b.label))
      .slice(0, perGroup);
    if (results.length) groups.push({ kind, title: GROUP_TITLES[kind], results });
  }
  if (query) {
    const label = `Ask Copilot about “${rawQuery.trim()}”`;
    groups.push({
      kind: 'copilot',
      title: GROUP_TITLES.copilot,
      results: [
        {
          id: COPILOT_RESULT_ID,
          kind: 'copilot',
          label,
          hint: 'Opens Copilot',
          matches: [],
          score: 0,
        },
      ],
    });
  }
  return groups;
}

function toResult(item: PaletteItem): PaletteResult {
  return {
    id: item.id,
    kind: item.kind,
    label: item.label,
    hint: item.hint,
    matches: [],
    score: 0,
  };
}

/** Results in display order, for keyboard movement. */
export function flattenGroups(groups: readonly PaletteGroup[]): PaletteResult[] {
  return groups.flatMap((g) => g.results);
}

/** Moves the active row by `delta`, wrapping at both ends. */
export function moveActive(index: number, delta: number, count: number): number {
  if (count <= 0) return 0;
  return (((index + delta) % count) + count) % count;
}

/** Splits a label into plain and highlighted runs. */
export function highlightRuns(
  label: string,
  ranges: ReadonlyArray<[number, number]>
): Array<{ text: string; hit: boolean }> {
  const runs: Array<{ text: string; hit: boolean }> = [];
  let at = 0;
  for (const [s, e] of [...ranges].sort((a, b) => a[0] - b[0])) {
    if (s > at) runs.push({ text: label.slice(at, s), hit: false });
    if (e > Math.max(s, at)) runs.push({ text: label.slice(Math.max(s, at), e), hit: true });
    at = Math.max(at, e);
  }
  if (at < label.length) runs.push({ text: label.slice(at), hit: false });
  return runs;
}

/** The URL that hands a palette query to Copilot. */
export function copilotUrl(query: string): string {
  const q = query.trim();
  return q ? `/copilot?q=${encodeURIComponent(q)}` : '/copilot';
}

/** A leading ">" narrows the palette to actions. */
export function parseQuery(raw: string): { actionsOnly: boolean; query: string } {
  const trimmed = raw.trimStart();
  if (trimmed.startsWith('>')) return { actionsOnly: true, query: trimmed.slice(1) };
  return { actionsOnly: false, query: raw };
}

export interface RecentEntry {
  id: string;
  label: string;
  to: string;
  at: number;
}

/** Puts `entry` first, drops its older copy and keeps at most `max`. */
export function pushRecent(
  list: readonly RecentEntry[],
  entry: RecentEntry,
  max = 4
): RecentEntry[] {
  return [entry, ...list.filter((e) => e.id !== entry.id)].slice(0, max);
}
