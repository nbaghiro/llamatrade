export interface NoMatchInput {
  noun: string;
  query?: string;
  filters?: readonly string[];
  total?: number;
}

function list(items: readonly string[]): string {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** Names the search and filters that hid everything, e.g. "No strategies match “TLT” with the Draft filter." */
export function noMatchSentence({ noun, query, filters = [], total }: NoMatchInput): string {
  const q = query?.trim();
  const what = q ? `No ${noun} match “${q}”` : `No ${noun} match`;
  const by = filters.length
    ? ` with the ${list(filters)} ${filters.length === 1 ? 'filter' : 'filters'}`
    : q
      ? ''
      : ' these filters';
  const clear =
    q && filters.length ? 'the search or the filters' : q ? 'the search' : 'the filters';
  const all = total !== undefined && total > 0 ? ` to see all ${total}` : '';
  return `${what}${by}. Clear ${clear}${all}.`;
}
