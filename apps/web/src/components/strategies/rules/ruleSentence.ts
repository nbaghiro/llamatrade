/**
 * The strategy as one short sentence (rules2 A). Only the top level is spelled out; anything
 * nested deeper folds into a clickable summary ("3 rules"), so a large strategy still reads in
 * two lines. Every value is a term that opens its rule.
 */

import {
  hasChildren,
  type Block,
  type BlockId,
  type ConditionOperand,
  type IfBlock,
  type StrategyTree,
  type WeightBlock,
} from '@llamatrade/core/strategy/types';

import {
  buildOutline,
  filterLookbackDays,
  indicatorLabel,
  lineText,
  ruleNumbers,
  type TokenField,
} from '../../../lib/outline';
import { listWords } from '../holdSentences';

export type SentenceTarget =
  | {
      kind: 'condition';
      blockId: BlockId;
      rule: number;
      part: 'operand' | 'threshold';
      field: TokenField;
    }
  | { kind: 'holding'; blockId: BlockId; rule: number | null; symbol: string; pct: number | null }
  | { kind: 'pick'; blockId: BlockId; rule: number; field: TokenField }
  | { kind: 'rebalance' }
  | { kind: 'fold'; of: 'rules' | 'symbols'; blockId: BlockId; rules: FoldedRule[] };

export interface FoldedRule {
  number: number;
  text: string;
}

export interface SentenceTerm {
  kind: 'term';
  /** Stable within one sentence, for the open state. */
  id: string;
  text: string;
  target: SentenceTarget;
}

export type SentencePart = { kind: 'text'; text: string } | SentenceTerm;

export interface RuleSentence {
  parts: SentencePart[];
  /** Rules in the whole strategy, nested ones included. */
  ruleCount: number;
  /** Past this size the Rules tab opens in Outline, with the sentence above it. */
  outlineFirst: boolean;
}

/** More rules than this and the outline is the better first view. */
export const OUTLINE_FIRST_RULES = 8;
/** Holdings named one by one before they fold into a count. */
const MAX_NAMED = 3;

const LEADS: Record<string, string> = {
  '1D': 'Each trading day',
  '1W': 'Each week',
  '1M': 'On the first trading day of each month',
  '3M': 'Each quarter',
  '1Y': 'Each year',
};

const COMPARE: Record<IfBlock['condition']['comparator'], string> = {
  gt: 'is above',
  lt: 'is below',
  gte: 'is at or above',
  lte: 'is at or below',
  eq: 'equals',
  neq: 'is not',
  cross_above: 'crosses above',
  cross_below: 'crosses below',
};

const SORT_WORDS: Record<string, string> = {
  momentum: 'return',
  volatility: 'volatility',
  volume: 'volume',
  market_cap: 'market cap',
  rsi: 'RSI',
  dividend_yield: 'dividend yield',
};

const num = (v: number) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100));

const text = (t: string): SentencePart => ({ kind: 'text', text: t });

/** "SPY's 14-day RSI", "SPY's 200-day average", "SPY's price". */
export function operandWords(op: ConditionOperand): string {
  switch (op.type) {
    case 'number':
      return `${num(op.value)}${op.isPercent ? '%' : ''}`;
    case 'price':
      return op.field === 'current' || op.field === 'close'
        ? op.symbol
        : `${op.symbol}'s ${op.field}`;
    case 'metric':
      return `${op.symbol}'s ${op.period != null ? `${op.period}-day ` : ''}${op.metric}`;
    case 'indicator': {
      const name =
        op.indicator === 'sma'
          ? 'average'
          : op.indicator === 'ema'
            ? 'exponential average'
            : op.indicator === 'momentum'
              ? 'momentum'
              : indicatorLabel(op.indicator);
      return `${op.symbol}'s ${op.period != null ? `${op.period}-day ` : ''}${name}`;
    }
  }
}

/** "SPY's 14-day RSI is above 70", the condition in plain words. */
export function conditionWords(block: IfBlock): string {
  const { left, comparator, right } = block.condition;
  return `${operandWords(left)} ${COMPARE[comparator]} ${rightWords(left, right)}`;
}

/** The right side, with "its" when it reads the same symbol as the left. */
function rightWords(left: ConditionOperand, right: ConditionOperand): string {
  const words = operandWords(right);
  if (right.type === 'number' || left.type === 'number' || right.symbol !== left.symbol) {
    return words;
  }
  return words.startsWith(`${right.symbol}'s `)
    ? `its ${words.slice(right.symbol.length + 3)}`
    : words;
}

interface Ctx {
  tree: StrategyTree;
  numbers: Map<BlockId, number>;
  lines: Map<BlockId, string>;
  seq: number;
}

function term(ctx: Ctx, textValue: string, target: SentenceTarget): SentenceTerm {
  ctx.seq += 1;
  return { kind: 'term', id: `t${ctx.seq}`, text: textValue, target };
}

function rulesUnder(ctx: Ctx, id: BlockId): FoldedRule[] {
  const out: FoldedRule[] = [];
  const walk = (bid: BlockId) => {
    const b = ctx.tree.blocks[bid];
    if (!b) return;
    const n = ctx.numbers.get(bid);
    if (n !== undefined) out.push({ number: n, text: ctx.lines.get(bid) ?? '' });
    if (hasChildren(b)) b.childIds.forEach(walk);
  };
  walk(id);
  return out;
}

function containsIf(tree: StrategyTree, id: BlockId): boolean {
  const b = tree.blocks[id];
  if (!b) return false;
  if (b.type === 'if') return true;
  return hasChildren(b) && b.childIds.some((c) => containsIf(tree, c));
}

function children(tree: StrategyTree, b: Block): Block[] {
  if (!hasChildren(b)) return [];
  return b.childIds.map((c) => tree.blocks[c]).filter((c): c is Block => c !== undefined);
}

/** Groups are transparent: a group with one child reads as that child. */
function unwrap(tree: StrategyTree, b: Block): Block {
  let cur = b;
  while (cur.type === 'group') {
    const kids = children(tree, cur);
    if (kids.length !== 1) break;
    cur = kids[0];
  }
  return cur;
}

const ruleOf = (ctx: Ctx, id: BlockId) => ctx.numbers.get(id) ?? 0;

function foldTerm(ctx: Ctx, id: BlockId): SentencePart[] {
  const rules = rulesUnder(ctx, id);
  const n = rules.length;
  return [
    term(ctx, `${n} ${n === 1 ? 'rule' : 'rules'}`, {
      kind: 'fold',
      of: 'rules',
      blockId: id,
      rules,
    }),
  ];
}

/** The symbols of a set of assets as one term, folded into a count past three. */
function symbolsTerm(ctx: Ctx, owner: Block, assets: Block[]): SentencePart {
  const symbols = assets.flatMap((a) => (a.type === 'asset' ? [a.symbol] : []));
  const label = symbols.length > MAX_NAMED ? `${symbols.length} funds` : listWords(symbols);
  return term(ctx, label, {
    kind: 'fold',
    of: 'symbols',
    blockId: owner.id,
    rules: symbols.map((s, i) => ({ number: i + 1, text: s })),
  });
}

function weightPhrase(ctx: Ctx, w: WeightBlock): SentencePart[] {
  const kids = children(ctx.tree, w).map((k) => unwrap(ctx.tree, k));
  if (kids.some((k) => k.type !== 'asset')) {
    return containsIf(ctx.tree, w.id)
      ? foldTerm(ctx, w.id)
      : [
          term(ctx, `${kids.length} groups`, {
            kind: 'fold',
            of: 'rules',
            blockId: w.id,
            rules: rulesUnder(ctx, w.id),
          }),
        ];
  }
  const rule = ruleOf(ctx, w.id);
  if (w.method === 'specified') {
    if (kids.length > MAX_NAMED) {
      return [symbolsTerm(ctx, w, kids), text(' in fixed weights')];
    }
    const parts: SentencePart[] = [];
    kids.forEach((k, i) => {
      if (k.type !== 'asset') return;
      if (i > 0) parts.push(text(i === kids.length - 1 ? ' and ' : ', '));
      const pct = w.allocations[k.id] ?? 0;
      parts.push(
        term(ctx, `${k.symbol} at ${num(pct)}%`, {
          kind: 'holding',
          blockId: k.id,
          rule,
          symbol: k.symbol,
          pct,
        })
      );
    });
    return parts;
  }
  if (w.method === 'equal') {
    if (kids.length === 1 && kids[0].type === 'asset') {
      const a = kids[0];
      return [
        term(ctx, a.symbol, { kind: 'holding', blockId: a.id, rule, symbol: a.symbol, pct: 100 }),
      ];
    }
    return [symbolsTerm(ctx, w, kids), text(' in equal weights')];
  }
  const parts: SentencePart[] = [];
  if (w.top != null) {
    parts.push(
      text('the '),
      term(ctx, `top ${w.top}`, { kind: 'pick', blockId: w.id, rule, field: 'weight.top' }),
      text(' of ')
    );
  }
  parts.push(symbolsTerm(ctx, w, kids), text(' weighted by '));
  const how =
    w.method === 'inverse_volatility'
      ? `inverse ${w.lookbackDays != null ? `${w.lookbackDays}-day ` : ''}volatility`
      : `${w.lookbackDays != null ? `${w.lookbackDays}-day ` : ''}${w.method.replace(/_/g, ' ')}`;
  parts.push(term(ctx, how, { kind: 'pick', blockId: w.id, rule, field: 'weight.method' }));
  return parts;
}

/** What a branch holds, as words and terms. */
function holdPhrase(ctx: Ctx, raw: Block): SentencePart[] {
  const b = unwrap(ctx.tree, raw);
  switch (b.type) {
    case 'asset':
      return [
        term(ctx, b.symbol, {
          kind: 'holding',
          blockId: b.id,
          rule: null,
          symbol: b.symbol,
          pct: 100,
        }),
      ];
    case 'weight':
      return weightPhrase(ctx, b);
    case 'filter': {
      const rule = ruleOf(ctx, b.id);
      const kids = children(ctx.tree, b).map((k) => unwrap(ctx.tree, k));
      const inner = kids.length === 1 && kids[0].type === 'weight' ? kids[0] : null;
      const assets = inner ? children(ctx.tree, inner).map((k) => unwrap(ctx.tree, k)) : kids;
      if (assets.some((a) => a.type !== 'asset')) return foldTerm(ctx, b.id);
      const { selection, count, sortBy } = b.config;
      const days = filterLookbackDays(b.config);
      const parts: SentencePart[] = [
        text('the '),
        term(ctx, `${selection} ${count}`, {
          kind: 'pick',
          blockId: b.id,
          rule,
          field: 'filter.count',
        }),
        text(' of '),
        symbolsTerm(ctx, inner ?? b, assets),
        text(' ranked by '),
        term(ctx, `${days}-day ${SORT_WORDS[sortBy] ?? sortBy}`, {
          kind: 'pick',
          blockId: b.id,
          rule,
          field: 'filter.period',
        }),
      ];
      if (inner && inner.method !== 'equal' && inner.method !== 'specified') {
        parts.push(text(`, weighted by ${inner.method.replace(/_/g, ' ')}`));
      }
      return parts;
    }
    case 'group': {
      const kids = children(ctx.tree, b);
      if (containsIf(ctx.tree, b.id)) return foldTerm(ctx, b.id);
      return kids.flatMap((k, i) => [...(i > 0 ? [text(' and ')] : []), ...holdPhrase(ctx, k)]);
    }
    case 'if':
    case 'else':
    case 'root':
      return foldTerm(ctx, b.id);
  }
}

/** A branch's holdings, or "follow N rules" when the branch decides again. */
function branchClause(ctx: Ctx, branch: Block): SentencePart[] {
  const kids = children(ctx.tree, branch);
  if (kids.some((k) => containsIf(ctx.tree, k.id))) {
    return [text('follow '), ...foldTerm(ctx, branch.id)];
  }
  return [
    text('hold '),
    ...kids.flatMap((k, i) => [...(i > 0 ? [text(' and ')] : []), ...holdPhrase(ctx, k)]),
  ];
}

function conditionParts(ctx: Ctx, block: IfBlock): SentencePart[] {
  const rule = ruleOf(ctx, block.id);
  const { left, comparator, right } = block.condition;
  const parts: SentencePart[] = [
    term(ctx, operandWords(left), {
      kind: 'condition',
      blockId: block.id,
      rule,
      part: 'operand',
      field: left.type === 'indicator' ? 'cond.left.period' : 'cond.left.symbol',
    }),
    text(` ${COMPARE[comparator]} `),
  ];
  parts.push(
    term(ctx, rightWords(left, right), {
      kind: 'condition',
      blockId: block.id,
      rule,
      part: 'threshold',
      field: right.type === 'number' ? 'cond.right.value' : 'cond.right.symbol',
    })
  );
  return parts;
}

function pairedElse(tree: StrategyTree, parent: Block, ifId: BlockId): Block | null {
  return children(tree, parent).find((c) => c.type === 'else' && c.ifBlockId === ifId) ?? null;
}

/** The sentence for a parsed strategy, with its rebalance lead. */
export function ruleSentence(tree: StrategyTree, timeframe: string): RuleSentence {
  const numbers = ruleNumbers(tree);
  const lines = new Map(buildOutline(tree).map((l) => [l.blockId, `${lineText(l)}`]));
  const ctx: Ctx = { tree, numbers, lines, seq: 0 };
  const root = tree.blocks[tree.rootId];
  const ruleCount = numbers.size;
  if (!root) return { parts: [], ruleCount, outlineFirst: false };

  const parts: SentencePart[] = [
    term(ctx, LEADS[timeframe] ?? 'At each rebalance', { kind: 'rebalance' }),
    text(', '),
  ];
  const top = children(tree, root);
  let first = true;
  for (const b of top) {
    if (b.type === 'else') continue;
    if (!first) parts.push(text(' Also, '));
    first = false;
    if (b.type === 'if') {
      parts.push(text('if '), ...conditionParts(ctx, b), text(', '), ...branchClause(ctx, b));
      const otherwise = pairedElse(tree, root, b.id);
      if (otherwise) {
        parts.push(text('. Otherwise, '), ...branchClause(ctx, otherwise));
      }
      parts.push(text('.'));
    } else {
      parts.push(text('hold '), ...holdPhrase(ctx, b), text('.'));
    }
  }
  if (first) parts.push(text('hold nothing.'));
  return { parts, ruleCount, outlineFirst: ruleCount > OUTLINE_FIRST_RULES };
}

/** The sentence as plain text. */
export function sentenceText(parts: readonly SentencePart[]): string {
  return parts.map((p) => p.text).join('');
}

/** The sentence without its rebalance lead, for a one-line summary: "if SPY's …, hold …". */
export function summaryParts(sentence: RuleSentence): SentencePart[] {
  return sentence.parts.slice(2);
}
