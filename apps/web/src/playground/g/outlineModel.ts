import type { TreeRowMark } from '../../components/ui/TreeRow';
import type { Rule, Value } from '../data';

export type Kind = 'strategy' | 'if' | 'else' | 'filter' | 'weight' | 'group' | 'asset';

export interface Item {
  id: string;
  depth: number;
  kind: Kind;
  parts: (string | Value)[];
  symbol?: string;
  pct?: number;
  weight?: string;
  pick?: boolean;
  mark?: TreeRowMark;
}

function kindOf(rule: Rule): Kind {
  const first = typeof rule.parts[0] === 'string' ? rule.parts[0] : '';
  if (first.startsWith('If') || first.startsWith('Buy') || first.startsWith('Sell')) return 'if';
  if (first.startsWith('Otherwise')) return 'else';
  if (first.startsWith('Pick') || first.startsWith('Hold the one')) return 'filter';
  return 'weight';
}

const LEADS: Partial<Record<Kind, string[]>> = {
  if: ['If '],
  else: ['Otherwise '],
  filter: ['Pick the'],
  weight: ['Hold '],
};

function trim(kind: Kind, parts: (string | Value)[]): (string | Value)[] {
  const [first, ...rest] = parts;
  if (typeof first !== 'string') return parts;
  const lead = LEADS[kind]?.find((l) => first === l.trim() || first.startsWith(l));
  if (!lead) return parts;
  const left = first.slice(lead.length).trim();
  return left ? [left, ...rest] : rest;
}

const pctOf = (w: string) => Number.parseFloat(w.replace(/[^\d.]/g, '')) || 0;

export function itemsOf(name: string, cadence: string, rules: Rule[]): Item[] {
  const out: Item[] = [
    { id: 'root', depth: 0, kind: 'strategy', parts: [name, ` · rebalance ${cadence}`] },
  ];
  const walk = (rule: Rule, id: string, depth: number) => {
    const kind = kindOf(rule);
    out.push({ id, depth, kind, parts: trim(kind, rule.parts) });
    let d = depth + 1;
    if (rule.group) {
      out.push({ id: `${id}.g`, depth: d, kind: 'group', parts: [rule.group] });
      d += 1;
    }
    rule.children?.forEach((c, i) => walk(c, `${id}.c${i}`, depth + 1));
    rule.funds?.forEach((f) =>
      out.push({
        id: `${id}.f.${f.symbol}`,
        depth: rule.children ? depth + 2 : d,
        kind: 'asset',
        parts: [],
        symbol: f.symbol,
        pct: pctOf(f.weight),
        weight: f.weight,
        pick: f.ifPicked,
      })
    );
  };
  rules.forEach((r, i) => walk(r, `r${i}`, 1));
  return out;
}

const textOf = (it: Item) =>
  `${it.kind}|${it.depth}|${it.parts.map((p) => (typeof p === 'string' ? p : p.text)).join(' ')}|${it.weight ?? ''}`;

/** Merges the current outline with a proposed one: changed rows show as − then +. */
export function diffItems(cur: Item[], next: Item[]): Item[] {
  const curById = new Map(cur.map((c) => [c.id, c]));
  const nextIds = new Set(next.map((n) => n.id));
  const out: Item[] = [];
  let ci = 0;
  const flushRemoved = (until: string | null) => {
    while (ci < cur.length && cur[ci].id !== until) {
      if (!nextIds.has(cur[ci].id)) out.push({ ...cur[ci], mark: 'del' });
      ci++;
    }
  };
  for (const n of next) {
    const old = curById.get(n.id);
    if (old) {
      flushRemoved(n.id);
      ci++;
      if (textOf(old) !== textOf(n)) out.push({ ...old, id: `${old.id}~was`, mark: 'del' });
      out.push(textOf(old) !== textOf(n) ? { ...n, mark: 'add' } : n);
    } else out.push({ ...n, mark: 'add' });
  }
  flushRemoved(null);
  return out;
}

/** Which rows a running session holds today: the held assets and every row above them. */
export function liveSet(items: Item[], held: Set<string>): Set<string> {
  const out = new Set<string>();
  if (held.size === 0) return out;
  items.forEach((it, i) => {
    if (it.kind !== 'asset' || !it.symbol || !held.has(it.symbol) || it.mark === 'del') return;
    out.add(it.id);
    let depth = it.depth;
    for (let j = i - 1; j >= 0 && depth > 0; j--) {
      if (items[j].depth < depth && items[j].mark !== 'del') {
        out.add(items[j].id);
        depth = items[j].depth;
      }
    }
  });
  return out;
}
