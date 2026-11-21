/**
 * A strategy's code read as sentences (builder/phone2 A): every number and the rebalance cadence
 * become values a person can tap and change, and a change is written back into the code at the
 * value's position so the rest of the text stays as it was.
 */

import { children, headOf, isAtom, isList, isNumber, keyword, readCode, type Atom, type List, type Node } from './sexpr.ts';

export const CADENCES = ['daily', 'weekly', 'monthly', 'quarterly'] as const;

export interface IndicatorRef {
  name: string;
  symbol: string;
  period: number | null;
}

export interface EditableValue {
  /** Position in reading order; the same value keeps its index after an edit. */
  index: number;
  start: number;
  end: number;
  text: string;
  kind: 'number' | 'choice';
  /** What the value is, for the sheet title and the change summary: "RSI threshold". */
  label: string;
  /** Shown after the number in the sentence: "%", " days". */
  suffix: string;
  min: number;
  max: number;
  step: number;
  choices: readonly string[];
  /** For a threshold, the indicator it is compared against, so its history can be drawn. */
  against: IndicatorRef | null;
}

export type Piece =
  | { t: 'text'; text: string }
  | { t: 'sym'; text: string }
  | { t: 'value'; value: EditableValue };

export interface ReadStrategy {
  name: string;
  /** One paragraph per sentence. */
  sentences: Piece[][];
  values: EditableValue[];
  symbols: string[];
}

const INDICATOR_NAMES: Record<string, string> = {
  rsi: 'RSI',
  sma: 'moving average',
  ema: 'exponential average',
  return: 'return',
  volatility: 'volatility',
  drawdown: 'drawdown',
  macd: 'MACD',
  atr: 'ATR',
};

const COMPARATORS: Record<string, string> = {
  '>': 'is above',
  '<': 'is below',
  '>=': 'is at or above',
  '<=': 'is at or below',
  '=': 'equals',
  'cross-above': 'crosses above',
  'cross-below': 'crosses below',
};

const METHOD_WORDS: Record<string, string> = {
  'inverse-volatility': 'inverse volatility',
  'risk-parity': 'risk parity',
  'min-variance': 'minimum variance',
  'market-cap': 'market cap',
  momentum: 'momentum',
};

class Reader {
  values: EditableValue[] = [];
  symbols = new Set<string>();

  value(atom: Atom, spec: Omit<EditableValue, 'index' | 'start' | 'end' | 'text'>): Piece {
    const v: EditableValue = { ...spec, index: this.values.length, start: atom.start, end: atom.end, text: atom.text };
    this.values.push(v);
    return { t: 'value', value: v };
  }

  number(node: Node | undefined, label: string, suffix: string, range: { min: number; max: number }, against: IndicatorRef | null = null): Piece[] {
    if (!isAtom(node) || !isNumber(node.text)) return node ? [{ t: 'text', text: plain(node) }] : [];
    const decimals = node.text.includes('.') ? node.text.split('.')[1].length : 0;
    return [this.value(node, { kind: 'number', label, suffix, ...range, step: decimals ? 10 ** -decimals : 1, choices: [], against })];
  }

  sym(text: string): Piece {
    this.symbols.add(text.toUpperCase());
    return { t: 'sym', text: text.toUpperCase() };
  }
}

const text = (s: string): Piece => ({ t: 'text', text: s });

function plain(node: Node): string {
  if (node.kind === 'list') return `(${node.items.map(plain).join(' ')})`;
  return node.text;
}

/** "A", "A and B", "A, B and C" with symbol pieces. */
function joinPieces(parts: Piece[][], last = 'and'): Piece[] {
  const out: Piece[] = [];
  parts.forEach((p, i) => {
    if (i > 0) out.push(text(i === parts.length - 1 ? ` ${last} ` : ', '));
    out.push(...p);
  });
  return out;
}

/** An operand of a condition: an indicator, a price or a number. */
function operand(r: Reader, node: Node, against: IndicatorRef | null): { pieces: Piece[]; ref: IndicatorRef | null } {
  if (isList(node)) {
    const head = headOf(node);
    const args = node.items.slice(1).filter((x) => !(isAtom(x) && x.text.startsWith(':')));
    const symAtom = args.find((x): x is Atom => isAtom(x) && !isNumber(x.text));
    const periodAtom = args.find((x): x is Atom => isAtom(x) && isNumber(x.text));
    const symbol = symAtom?.text.toUpperCase() ?? '';
    const name = INDICATOR_NAMES[head] ?? head;
    const ref: IndicatorRef = { name: head, symbol, period: periodAtom ? Number(periodAtom.text) : null };
    const pieces: Piece[] = [];
    if (symbol) pieces.push(r.sym(symbol), text("'s "));
    if (head === 'price') return { pieces: symbol ? [text('the price of '), r.sym(symbol)] : [text('the price')], ref };
    if (periodAtom) {
      pieces.push(...r.number(periodAtom, `${name} period`, '-day', { min: 2, max: 400 }));
      pieces.push(text(` ${name}`));
    } else {
      pieces.push(text(name));
    }
    return { pieces, ref };
  }
  if (isAtom(node) && isNumber(node.text)) {
    const label = against ? `${INDICATOR_NAMES[against.name] ?? against.name} threshold` : 'Threshold';
    const range = against?.name === 'rsi' ? { min: 0, max: 100 } : { min: -1000, max: 100000 };
    return { pieces: r.number(node, label, '', range, against), ref: null };
  }
  if (isAtom(node)) return { pieces: [r.sym(node.text)], ref: null };
  return { pieces: [text(plain(node))], ref: null };
}

function condition(r: Reader, node: Node): Piece[] {
  if (!isList(node)) return [text(plain(node))];
  const head = headOf(node);
  const args = node.items.slice(1);
  if (head === 'and' || head === 'or') return joinPieces(args.map((a) => condition(r, a)), head);
  if (head === 'not') return [text('not '), ...condition(r, args[0] ?? node)];
  const cmp = COMPARATORS[head];
  if (cmp && args.length >= 2) {
    const left = operand(r, args[0], null);
    const right = operand(r, args[1], left.ref);
    return [...left.pieces, text(` ${cmp} `), ...right.pieces];
  }
  return [text(plain(node))];
}

/** The symbols an allocation holds, flattened. */
function assetsOf(node: Node): Atom[] {
  if (!isList(node)) return [];
  if (headOf(node) === 'asset') {
    const sym = node.items[1];
    return isAtom(sym) ? [sym] : [];
  }
  return children(node).flatMap(assetsOf);
}

function symbolList(r: Reader, assets: Atom[], max = 5): Piece[] {
  const shown = assets.length > max ? assets.slice(0, max - 1) : assets;
  const parts = shown.map((a) => [r.sym(a.text)]);
  if (assets.length > shown.length) {
    assets.slice(shown.length).forEach((a) => r.symbols.add(a.text.toUpperCase()));
    parts.push([text(`${assets.length - shown.length} more`)]);
  }
  return joinPieces(parts);
}

/** What a block holds, as the words after "hold". */
function allocation(r: Reader, node: Node): Piece[] {
  if (!isList(node)) return [text(plain(node))];
  const head = headOf(node);
  const kids = children(node);
  if (head === 'asset') {
    const sym = node.items[1];
    const w = keyword(node, 'weight');
    const out: Piece[] = isAtom(sym) ? [r.sym(sym.text)] : [];
    if (w) out.push(text(' '), ...r.number(w, `${isAtom(sym) ? sym.text.toUpperCase() : 'Asset'} weight`, '%', { min: 0, max: 100 }));
    return out;
  }
  if (head === 'group') return kids.filter((k) => !(k.kind === 'string')).flatMap((k) => allocation(r, k));
  if (head === 'weight') {
    const method = keyword(node, 'method');
    const m = isAtom(method) ? method.text : 'equal';
    if (m === 'specified') return joinPieces(kids.map((k) => allocation(r, k)));
    const assets = kids.flatMap(assetsOf);
    const names = symbolList(r, assets);
    if (m === 'equal') return [...names, text(assets.length > 1 ? ' in equal weights' : '')];
    const out: Piece[] = [...names, text(` weighted by ${METHOD_WORDS[m] ?? m}`)];
    const lb = keyword(node, 'lookback');
    if (lb) out.push(text(' over '), ...r.number(lb, 'Weighting lookback', ' days', { min: 5, max: 400 }));
    return out;
  }
  if (head === 'filter') {
    const by = keyword(node, 'by');
    const select = keyword(node, 'select');
    const lb = keyword(node, 'lookback');
    const out: Piece[] = [];
    if (isList(select)) {
      const dir = isAtom(select.items[0]) ? select.items[0].text : 'top';
      out.push(text(`the ${dir} `), ...r.number(select.items[1], `${dir === 'bottom' ? 'Bottom' : 'Top'} count`, '', { min: 1, max: 50 }), text(' of '));
    }
    out.push(...symbolList(r, kids.flatMap(assetsOf)));
    if (isAtom(by)) out.push(text(` by ${METHOD_WORDS[by.text] ?? by.text}`));
    if (lb) out.push(text(' over '), ...r.number(lb, `${isAtom(by) ? cap(METHOD_WORDS[by.text] ?? by.text) : 'Ranking'} lookback`, ' days', { min: 5, max: 400 }));
    return out;
  }
  if (head === 'if') return [text('a choice by rule')];
  return kids.flatMap((k) => allocation(r, k));
}

function cap(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Sentences for a block: an if becomes "When …, hold …." and "Otherwise …". */
function blockSentences(r: Reader, node: Node, prefix: string): Piece[][] {
  if (!isList(node)) return [];
  const head = headOf(node);
  if (head === 'if') {
    const [cond, then, ...rest] = node.items.slice(1);
    const elseNode = rest.find((x) => headOf(x) === 'else');
    const out: Piece[][] = [];
    const thenIsIf = headOf(then) === 'if';
    out.push([text(`${prefix}hen `), ...condition(r, cond), text(thenIsIf ? ':' : ', hold '), ...(thenIsIf ? [] : allocation(r, then)), text(thenIsIf ? '' : '.')]);
    if (thenIsIf) out.push(...blockSentences(r, then, 'W'));
    if (isList(elseNode)) {
      const inner = children(elseNode)[0];
      if (headOf(inner) === 'if') out.push(...blockSentences(r, inner, 'Otherwise, w'));
      else if (inner) out.push([text('Otherwise hold '), ...allocation(r, inner), text('.')]);
    }
    return out;
  }
  if (head === 'group') {
    const kid = children(node).find((k) => k.kind !== 'string');
    return kid ? blockSentences(r, kid, prefix) : [];
  }
  return [[text('Hold '), ...allocation(r, node), text('.')]];
}

/** Reads strategy code into sentences and editable values; null when it is not a strategy form. */
export function readStrategy(code: string): ReadStrategy | null {
  const top = readCode(code).find((n): n is List => headOf(n) === 'strategy');
  if (!top) return null;
  const r = new Reader();
  const name = top.items[1]?.kind === 'string' ? top.items[1].text : 'Untitled strategy';
  const sentences: Piece[][] = [];
  const rebalance = keyword(top, 'rebalance');
  const benchmark = keyword(top, 'benchmark');
  const head: Piece[] = [];
  if (isAtom(rebalance)) {
    head.push(text('Rebalances '), r.value(rebalance, { kind: 'choice', label: 'Rebalance', suffix: '', min: 0, max: 0, step: 0, choices: CADENCES, against: null }));
  }
  if (isAtom(benchmark)) head.push(text(head.length ? ' against ' : 'Compared against '), { t: 'sym', text: benchmark.text.toUpperCase() });
  if (head.length) sentences.push([...head, text('.')]);
  for (const block of children(top).filter((n) => n.kind !== 'string')) sentences.push(...blockSentences(r, block, 'W'));
  return { name, sentences, values: r.values, symbols: [...r.symbols] };
}

/** The code with one value replaced by new text. */
export function replaceValue(code: string, value: Pick<EditableValue, 'start' | 'end'>, next: string): string {
  return code.slice(0, value.start) + next + code.slice(value.end);
}

/** A number for the code: no trailing zeros, at most the step's decimals. */
export function formatValue(n: number, step: number): string {
  const decimals = Math.min(4, String(step).split('.')[1]?.length ?? 0);
  return String(Number(n.toFixed(decimals)));
}

/** A number moved by the step and kept inside the value's range. */
export function stepValue(value: Pick<EditableValue, 'min' | 'max' | 'step'>, current: number, dir: 1 | -1): number {
  const next = current + dir * (value.step || 1);
  return Math.min(value.max, Math.max(value.min, Number(next.toFixed(6))));
}

export interface Change {
  label: string;
  from: string;
  to: string;
}

/** The values that differ between two readings of the same strategy, by reading order. */
export function changesBetween(before: readonly EditableValue[], after: readonly EditableValue[]): Change[] {
  const out: Change[] = [];
  const n = Math.min(before.length, after.length);
  for (let i = 0; i < n; i++) {
    if (before[i].text !== after[i].text) out.push({ label: before[i].label, from: before[i].text, to: after[i].text });
  }
  return out;
}

/** "RSI threshold 70 to 72, Top count 2 to 3", for the version's change summary. */
export function changeSummary(changes: readonly Change[]): string {
  return changes.map((c) => `${c.label} ${c.from} to ${c.to}`).join(', ');
}
