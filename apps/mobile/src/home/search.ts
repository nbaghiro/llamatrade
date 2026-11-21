/** Narrowing the search list as someone types (palette2 A). Pure, for the tests. */

export interface SearchItem {
  key: string;
  title: string;
  /** Extra words that should match, e.g. "paper" or a symbol. */
  keywords?: readonly string[];
}

/** 3 for a title that starts with the query, 2 for a word that does, 1 for a match anywhere, 0 for none. */
export function score(item: SearchItem, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 1;
  const title = item.title.toLowerCase();
  if (title.startsWith(q)) return 3;
  const words = [...title.split(/[\s\-_/]+/), ...(item.keywords ?? []).map((k) => k.toLowerCase())];
  if (words.some((w) => w.startsWith(q))) return 2;
  if (title.includes(q) || words.some((w) => w.includes(q))) return 1;
  return 0;
}

/** Items that match, best first, keeping the original order among equals. */
export function narrow<T extends SearchItem>(items: readonly T[], query: string): T[] {
  return items
    .map((item, i) => ({ item, i, s: score(item, query) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || a.i - b.i)
    .map((x) => x.item);
}

/** Adds a key to the front of a recent list, without duplicates, keeping at most `max`. */
export function pushRecent(list: readonly string[], key: string, max = 6): string[] {
  return [key, ...list.filter((k) => k !== key)].slice(0, max);
}
