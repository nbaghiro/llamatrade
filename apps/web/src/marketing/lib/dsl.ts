/** Highlighting for the strategy-language snippets in the screen art. */

export type DslToken = { text: string; tone?: 'keyword' | 'string' };

const KEYWORDS = new Set(['strategy', 'weight', 'asset', 'filter', 'if', 'else']);

/** Block keywords straight after "(" and quoted strings are marked; everything else is plain. */
export function highlightDsl(line: string): DslToken[] {
  const out: DslToken[] = [];
  const re = /"[^"]*"|\(([a-z-]+)/g;
  let last = 0;
  for (let m = re.exec(line); m; m = re.exec(line)) {
    if (m[0].startsWith('"')) {
      if (m.index > last) out.push({ text: line.slice(last, m.index) });
      out.push({ text: m[0], tone: 'string' });
      last = m.index + m[0].length;
    } else if (KEYWORDS.has(m[1])) {
      out.push({ text: line.slice(last, m.index + 1) });
      out.push({ text: m[1], tone: 'keyword' });
      last = m.index + m[0].length;
    }
  }
  if (last < line.length) out.push({ text: line.slice(last) });
  return out.filter((t) => t.text.length > 0);
}
