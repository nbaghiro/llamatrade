import { TemplateDifficulty, type StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';

/** The template suggested first: Classic 60/40 when the catalogue has it. */
export const PREFERRED_TEMPLATE_ID = 'classic-60-40';

type Sx = string | Sx[];

function tokenize(src: string): string[] {
  return src.match(/"(?:[^"\\]|\\.)*"|[()]|[^\s()]+/g) ?? [];
}

/** Parses the first s-expression in `src`. Unbalanced input yields what was read so far. */
export function parseSexpr(src: string): Sx | null {
  const tokens = tokenize(src);
  let i = 0;
  const read = (): Sx | null => {
    const t = tokens[i++];
    if (t === undefined) return null;
    if (t === '(') {
      const list: Sx[] = [];
      while (i < tokens.length && tokens[i] !== ')') {
        const item = read();
        if (item === null) break;
        list.push(item);
      }
      i++;
      return list;
    }
    if (t === ')') return null;
    return t;
  };
  return read();
}

function unquote(atom: string): string {
  return atom.startsWith('"') && atom.endsWith('"') ? atom.slice(1, -1) : atom;
}

function print(node: Sx): string {
  return typeof node === 'string' ? unquote(node) : `(${node.map(print).join(' ')})`;
}

interface Parts {
  head: string;
  args: Sx[];
  opts: Record<string, string>;
  children: Sx[][];
}

function partsOf(list: Sx[]): Parts {
  const [head, ...rest] = list;
  const args: Sx[] = [];
  const opts: Record<string, string> = {};
  const children: Sx[][] = [];
  for (let i = 0; i < rest.length; i++) {
    const item = rest[i];
    if (typeof item === 'string' && item.startsWith(':') && i + 1 < rest.length) {
      opts[item.slice(1)] = print(rest[++i]);
    } else if (Array.isArray(item)) {
      children.push(item);
    } else {
      args.push(item);
    }
  }
  return { head: typeof head === 'string' ? head : '', args, opts, children };
}

export interface OutlineLine {
  depth: number;
  text: string;
  /** A weight such as "60%", shown at the end of the line. */
  weight?: string;
}

const METHOD_LABEL: Record<string, string> = {
  equal: 'Equal weights',
  specified: 'Set weights',
  'inverse-volatility': 'Weighted by inverse volatility',
  momentum: 'Weighted by momentum',
  'risk-parity': 'Risk parity weights',
};

function methodLabel(method: string | undefined): string {
  if (!method) return 'Weights';
  return METHOD_LABEL[method] ?? `Weighted by ${method.replace(/-/g, ' ')}`;
}

const pct = (w: string | undefined) => (w ? `${w}%` : undefined);

function walk(list: Sx[], depth: number, out: OutlineLine[]): void {
  const { head, args, opts, children } = partsOf(list);
  switch (head) {
    case 'strategy':
      children.forEach((c) => walk(c, depth, out));
      return;
    case 'weight':
      out.push({ depth, text: methodLabel(opts.method) });
      children.forEach((c) => walk(c, depth + 1, out));
      return;
    case 'group':
      out.push({ depth, text: args.map(print).join(' ') || 'Group', weight: pct(opts.weight) });
      children.forEach((c) => walk(c, depth + 1, out));
      return;
    case 'asset':
      out.push({ depth, text: args.map(print).join(' '), weight: pct(opts.weight) });
      return;
    case 'if': {
      const [cond, ...branches] = children;
      out.push({ depth, text: `If ${cond ? print(cond) : 'condition'}` });
      if (branches[0]) walk(branches[0], depth + 1, out);
      if (branches[1]) {
        out.push({ depth, text: 'Otherwise' });
        walk(branches[1], depth + 1, out);
      }
      return;
    }
    default:
      out.push({ depth, text: print(list) });
  }
}

export interface TemplateOutline {
  rebalance: string | null;
  benchmark: string | null;
  symbols: string[];
  lines: OutlineLine[];
}

/** A readable outline of a strategy definition: its weights, groups and assets, in order. */
export function outlineOf(sexpr: string): TemplateOutline {
  const root = parseSexpr(sexpr);
  const empty: TemplateOutline = { rebalance: null, benchmark: null, symbols: [], lines: [] };
  if (!Array.isArray(root)) return empty;
  const { opts } = partsOf(root);
  const lines: OutlineLine[] = [];
  walk(root, 0, lines);
  return {
    rebalance: opts.rebalance ?? null,
    benchmark: opts.benchmark ?? null,
    symbols: symbolsOf(sexpr),
    lines,
  };
}

export function symbolsOf(sexpr: string): string[] {
  const seen = new Set<string>();
  for (const m of sexpr.matchAll(/\(asset\s+([A-Za-z][A-Za-z0-9.]*)/g))
    seen.add(m[1].toUpperCase());
  return [...seen];
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "Quarterly · SPY and AGG", "Monthly · 5 symbols". */
export function templateMeta(t: Pick<StrategyTemplate, 'configSexpr'>): string {
  const { rebalance } = outlineOf(t.configSexpr);
  const symbols = symbolsOf(t.configSexpr);
  const holdings =
    symbols.length === 0
      ? ''
      : symbols.length <= 2
        ? symbols.join(' and ')
        : `${symbols.length} symbols`;
  return [rebalance ? capitalize(rebalance) : '', holdings].filter(Boolean).join(' · ');
}

/** Beginner templates first, with the preferred one at the front, then the rest in catalogue order. */
export function rankTemplates<T extends Pick<StrategyTemplate, 'id' | 'difficulty'>>(
  list: readonly T[]
): T[] {
  const rank = (t: T) =>
    t.id === PREFERRED_TEMPLATE_ID ? 0 : t.difficulty === TemplateDifficulty.BEGINNER ? 1 : 2;
  return list
    .map((t, i) => ({ t, i }))
    .sort((a, b) => rank(a.t) - rank(b.t) || a.i - b.i)
    .map(({ t }) => t);
}
