/** A run of answer text, or a citation marker such as the "2" in "[2]". */
export type CitedPart = { text: string } | { n: number };

/** Markers like [2] or [1, 3]; a bracket followed by "(" is a markdown link, not a citation. */
const MARKER = /\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g;

/** Splits answer text around its citation markers, in order. "[1, 3]" gives two markers. */
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

const READS: Record<string, string> = {
  get_strategy: 'the rule',
  list_strategies: 'your strategies',
  list_templates: 'templates',
  get_backtest_results: 'the backtest',
  list_backtests: 'backtests',
  run_backtest: 'the backtest run',
  get_portfolio_summary: 'the account summary',
  get_portfolio_performance: 'performance',
  get_positions: 'positions',
  validate_dsl: 'the check',
  get_asset_info: 'asset details',
  recall_memory: 'earlier conversations',
  get_user_profile: 'your profile',
  search_past_strategies: 'past strategies',
};

/** "Read the rule, positions and performance", naming each kind of record once. */
export function readSummary(tools: readonly string[]): string {
  const names = tools
    .map((t) => READS[t] ?? t.replace(/_/g, ' '))
    .filter((n, i, all) => all.indexOf(n) === i);
  if (!names.length) return '';
  const list =
    names.length === 1
      ? names[0]
      : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
  return `Read ${list}`;
}
