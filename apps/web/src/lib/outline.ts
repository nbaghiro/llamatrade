/**
 * The strategy as numbered sentences. Each block type has a sentence template whose values are
 * tokens, so the editor can edit a value in place and the diff can compare two versions value by
 * value. Pure functions only; the React outline renders what these return.
 */

import {
  COMPARATORS,
  INDICATORS,
  hasChildren,
  type Block,
  type BlockId,
  type Comparator,
  type ConditionExpression,
  type ConditionOperand,
  type FilterConfig,
  type FilterPeriod,
  type FilterSortBy,
  type IndicatorName,
  type IndicatorRef,
  type MetricName,
  type PriceField,
  type StrategyTree,
  type WeightBlock,
  type WeightMethod,
} from '@llamatrade/core/strategy/types';

export type Side = 'left' | 'right';

export type TokenField =
  | 'rebalance'
  | 'benchmark'
  | `cond.${Side}.period`
  | `cond.${Side}.indicator`
  | `cond.${Side}.symbol`
  | `cond.${Side}.field`
  | `cond.${Side}.metric`
  | `cond.${Side}.value`
  | 'cond.comparator'
  | 'weight.method'
  | 'weight.lookback'
  | 'weight.top'
  | 'filter.selection'
  | 'filter.count'
  | 'filter.sortBy'
  | 'filter.period'
  | 'group.name'
  | 'asset.weight';

export interface ChoiceOption {
  value: string;
  label: string;
}

export type TokenEditor =
  | { type: 'number'; min: number; max: number; step: number; integer: boolean; suffix?: string }
  | { type: 'choice'; options: readonly ChoiceOption[] }
  | { type: 'symbol'; optional: boolean }
  | { type: 'text' };

export interface OutlineToken {
  kind: 'token';
  field: TokenField;
  /** The block the edit applies to; for asset.weight, the asset (its parent weight holds the value). */
  blockId: BlockId | null;
  value: string;
  text: string;
  /** Unit for the change in words, e.g. "days". */
  unit?: string;
  /** The engine can't run this value. */
  bad?: boolean;
  editor: TokenEditor;
}

export interface OutlineText {
  kind: 'text';
  text: string;
}

export type OutlinePart = OutlineText | OutlineToken;

/** fixed and equal are exact shares of the parent; ranked is decided by the engine at each rebalance. */
export type AssetShare =
  | { kind: 'fixed'; pct: number }
  | { kind: 'equal'; pct: number }
  | { kind: 'ranked'; method: WeightMethod }
  /** Under a filter: the share among the picks, or null when the filter decides it alone. */
  | { kind: 'picked'; pct: number | null }
  | { kind: 'none' };

export type OutlineLineKind = 'if' | 'else' | 'weight' | 'filter' | 'group' | 'asset' | 'collapsed';

export interface OutlineLine {
  key: string;
  blockId: BlockId;
  kind: OutlineLineKind;
  /** Rules are numbered in reading order; asset lines and collapsed lines have no number. */
  number: number | null;
  depth: number;
  parts: OutlinePart[];
  symbol?: string;
  name?: string;
  share?: AssetShare;
  /** For an expandable rule past the visible depth, how many lines it hides. */
  hiddenCount?: number;
}

export interface OutlineMeta {
  timeframe: string;
  benchmark: string;
}

export interface OutlineOptions {
  /** Rules deeper than this many levels collapse into one line until expanded. */
  maxDepth?: number;
  /** Blocks at the collapse depth that the reader has opened. */
  expanded?: ReadonlySet<BlockId>;
}

export const OUTLINE_MAX_DEPTH = 3;

export const REBALANCE_OPTIONS: readonly ChoiceOption[] = [
  { value: '1D', label: 'daily' },
  { value: '1W', label: 'weekly' },
  { value: '1M', label: 'monthly' },
  { value: '3M', label: 'quarterly' },
  { value: '1Y', label: 'annually' },
];

const METHOD_WORDS: Record<WeightMethod, string> = {
  specified: 'fixed weights',
  equal: 'equal weight',
  momentum: 'momentum',
  inverse_volatility: 'inverse volatility',
  min_variance: 'minimum variance',
  risk_parity: 'risk parity',
  market_cap: 'market cap',
};

/** Weight methods the engine can run. market_cap parses but needs fundamentals it doesn't have. */
export const SUPPORTED_METHODS: readonly WeightMethod[] = [
  'specified',
  'equal',
  'momentum',
  'inverse_volatility',
  'min_variance',
  'risk_parity',
];

export function isSupportedMethod(method: string): boolean {
  return (SUPPORTED_METHODS as readonly string[]).includes(method);
}

const LOOKBACK_METHODS: ReadonlySet<WeightMethod> = new Set([
  'momentum',
  'inverse_volatility',
  'min_variance',
  'risk_parity',
]);

export function methodUsesLookback(method: WeightMethod): boolean {
  return LOOKBACK_METHODS.has(method);
}

const COMPARATOR_WORDS: Record<Comparator, { lead: string; token: string }> = {
  gt: { lead: 'is ', token: 'above' },
  lt: { lead: 'is ', token: 'below' },
  gte: { lead: 'is ', token: 'at or above' },
  lte: { lead: 'is ', token: 'at or below' },
  eq: { lead: 'is ', token: 'equal to' },
  neq: { lead: 'is ', token: 'not equal to' },
  cross_above: { lead: '', token: 'crosses above' },
  cross_below: { lead: '', token: 'crosses below' },
};

/** "is above", "crosses below": the comparison as the outline reads it. */
export function comparatorPhrase(c: Comparator): string {
  const w = COMPARATOR_WORDS[c];
  return `${w.lead}${w.token}`;
}

const PRICE_WORDS: Record<PriceField, string> = {
  current: 'price',
  open: 'open',
  high: 'high',
  low: 'low',
  close: 'close',
  volume: 'volume',
};

const METRIC_WORDS: Record<MetricName, string> = {
  drawdown: 'drawdown',
  return: 'return',
  volatility: 'volatility',
};

const SORT_WORDS: Partial<Record<FilterSortBy, string>> = {
  momentum: 'momentum',
  volatility: 'volatility',
  volume: 'volume',
};

const PERIOD_WORDS: Record<FilterPeriod, string> = {
  '1m': '1 month',
  '3m': '3 months',
  '6m': '6 months',
  '12m': '12 months',
};

const INTEGER = (min: number, max: number, suffix?: string): TokenEditor => ({
  type: 'number',
  min,
  max,
  step: 1,
  integer: true,
  suffix,
});

const choice = (options: readonly ChoiceOption[]): TokenEditor => ({ type: 'choice', options });

const INDICATOR_OPTIONS: readonly ChoiceOption[] = INDICATORS.map((i) => ({
  value: i.name,
  label: i.shortLabel,
}));

const COMPARATOR_OPTIONS: readonly ChoiceOption[] = COMPARATORS.map((c) => ({
  value: c.value,
  label: COMPARATOR_WORDS[c.value].token,
}));

const METHOD_OPTIONS: readonly ChoiceOption[] = SUPPORTED_METHODS.map((m) => ({
  value: m,
  label: METHOD_WORDS[m],
}));

const PRICE_OPTIONS: readonly ChoiceOption[] = (Object.keys(PRICE_WORDS) as PriceField[]).map(
  (f) => ({ value: f, label: PRICE_WORDS[f] })
);

const METRIC_OPTIONS: readonly ChoiceOption[] = (Object.keys(METRIC_WORDS) as MetricName[]).map(
  (m) => ({ value: m, label: METRIC_WORDS[m] })
);

const SORT_OPTIONS: readonly ChoiceOption[] = (
  Object.keys(SORT_WORDS) as Array<keyof typeof SORT_WORDS>
).map((s) => ({ value: s, label: SORT_WORDS[s] ?? s }));

const PERIOD_DAYS: Record<FilterPeriod, number> = { '1m': 21, '3m': 63, '6m': 126, '12m': 252 };

/** A filter's lookback in trading days: the exact value written, else its period's length. */
export function filterLookbackDays(config: FilterConfig): number {
  return config.lookbackDays ?? PERIOD_DAYS[config.period];
}

function filterPeriodToken(blockId: BlockId, config: FilterConfig): OutlineToken {
  const exact =
    config.lookbackDays !== undefined && config.lookbackDays !== PERIOD_DAYS[config.period];
  return exact
    ? token(
        'filter.period',
        blockId,
        `${config.lookbackDays}d`,
        `${config.lookbackDays} days`,
        choice(PERIOD_OPTIONS)
      )
    : token(
        'filter.period',
        blockId,
        config.period,
        PERIOD_WORDS[config.period],
        choice(PERIOD_OPTIONS)
      );
}

const PERIOD_OPTIONS: readonly ChoiceOption[] = (Object.keys(PERIOD_WORDS) as FilterPeriod[]).map(
  (p) => ({ value: p, label: PERIOD_WORDS[p] })
);

const SELECTION_OPTIONS: readonly ChoiceOption[] = [
  { value: 'top', label: 'top' },
  { value: 'bottom', label: 'bottom' },
];

export function methodWords(method: WeightMethod): string {
  return METHOD_WORDS[method];
}

export function rebalanceWord(timeframe: string): string {
  return REBALANCE_OPTIONS.find((o) => o.value === timeframe)?.label ?? 'daily';
}

export function indicatorLabel(name: IndicatorName): string {
  return INDICATORS.find((i) => i.name === name)?.shortLabel ?? name.toUpperCase();
}

function indicatorHasPeriod(name: IndicatorName): boolean {
  return INDICATORS.find((i) => i.name === name)?.hasPeriod ?? false;
}

const text = (t: string): OutlineText => ({ kind: 'text', text: t });

function token(
  field: TokenField,
  blockId: BlockId | null,
  value: string | number,
  display: string,
  editor: TokenEditor,
  extra: Partial<Pick<OutlineToken, 'unit' | 'bad'>> = {}
): OutlineToken {
  return { kind: 'token', field, blockId, value: String(value), text: display, editor, ...extra };
}

function formatNumber(v: number): string {
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

function operandParts(op: ConditionOperand, side: Side, blockId: BlockId): OutlinePart[] {
  const f = (name: string) => `cond.${side}.${name}` as TokenField;
  switch (op.type) {
    case 'number':
      return [
        token(
          f('value'),
          blockId,
          op.value,
          `${formatNumber(op.value)}${op.isPercent ? '%' : ''}`,
          {
            type: 'number',
            min: -1e9,
            max: 1e9,
            step: 0.1,
            integer: false,
            suffix: op.isPercent ? '%' : undefined,
          }
        ),
      ];
    case 'price':
      return [
        text('the '),
        token(f('field'), blockId, op.field, PRICE_WORDS[op.field], choice(PRICE_OPTIONS)),
        text(' of '),
        token(f('symbol'), blockId, op.symbol, op.symbol, { type: 'symbol', optional: false }),
      ];
    case 'metric': {
      const parts: OutlinePart[] = [text('the ')];
      if (op.period != null) {
        parts.push(
          token(f('period'), blockId, op.period, String(op.period), INTEGER(1, 2520), {
            unit: 'days',
          }),
          text('-day ')
        );
      }
      parts.push(
        token(f('metric'), blockId, op.metric, METRIC_WORDS[op.metric], choice(METRIC_OPTIONS)),
        text(' of '),
        token(f('symbol'), blockId, op.symbol, op.symbol, { type: 'symbol', optional: false })
      );
      return parts;
    }
    case 'indicator': {
      const parts: OutlinePart[] = [text('the ')];
      if (indicatorHasPeriod(op.indicator) && op.period != null) {
        parts.push(
          token(f('period'), blockId, op.period, String(op.period), INTEGER(1, 2520), {
            unit: 'days',
          }),
          text('-day ')
        );
      }
      parts.push(
        token(
          f('indicator'),
          blockId,
          op.indicator,
          indicatorLabel(op.indicator),
          choice(INDICATOR_OPTIONS)
        ),
        text(' of '),
        token(f('symbol'), blockId, op.symbol, op.symbol, { type: 'symbol', optional: false })
      );
      return parts;
    }
  }
}

export function conditionParts(condition: ConditionExpression, blockId: BlockId): OutlinePart[] {
  const words = COMPARATOR_WORDS[condition.comparator];
  return [
    ...operandParts(condition.left, 'left', blockId),
    text(` ${words.lead}`),
    token(
      'cond.comparator',
      blockId,
      condition.comparator,
      words.token,
      choice(COMPARATOR_OPTIONS)
    ),
    text(' '),
    ...operandParts(condition.right, 'right', blockId),
  ];
}

function weightParts(block: WeightBlock): OutlinePart[] {
  const method = token(
    'weight.method',
    block.id,
    block.method,
    METHOD_WORDS[block.method],
    choice(METHOD_OPTIONS),
    { bad: !isSupportedMethod(block.method) }
  );
  if (block.method === 'specified') return [text('hold '), method];
  if (block.method === 'equal') return [text('hold at '), method];
  const parts: OutlinePart[] = [text('hold ')];
  if (block.top != null) {
    parts.push(
      text('the top '),
      token('weight.top', block.id, block.top, String(block.top), INTEGER(1, 500)),
      text(', ')
    );
  }
  parts.push(text('weighted by '), method);
  if (block.lookbackDays != null) {
    parts.push(
      text(' over '),
      token(
        'weight.lookback',
        block.id,
        block.lookbackDays,
        String(block.lookbackDays),
        INTEGER(1, 2520),
        {
          unit: 'days',
        }
      ),
      text(' days')
    );
  }
  return parts;
}

function filterParts(blockId: BlockId, config: FilterConfig): OutlinePart[] {
  return [
    text('pick the '),
    token(
      'filter.selection',
      blockId,
      config.selection,
      config.selection,
      choice(SELECTION_OPTIONS)
    ),
    text(' '),
    token('filter.count', blockId, config.count, String(config.count), INTEGER(1, 500)),
    text(' by '),
    token(
      'filter.sortBy',
      blockId,
      config.sortBy,
      SORT_WORDS[config.sortBy] ?? config.sortBy,
      choice(SORT_OPTIONS)
    ),
    text(' over '),
    filterPeriodToken(blockId, config),
  ];
}

/** The strategy-level sentence: "Rebalance monthly and compare with SPY". */
export function metaParts(meta: OutlineMeta): OutlinePart[] {
  return [
    text('Rebalance '),
    token(
      'rebalance',
      null,
      meta.timeframe,
      rebalanceWord(meta.timeframe),
      choice(REBALANCE_OPTIONS)
    ),
    text(' and compare with '),
    token('benchmark', null, meta.benchmark, meta.benchmark || 'no benchmark', {
      type: 'symbol',
      optional: true,
    }),
  ];
}

/** The share an asset or sleeve takes of its parent, as written. */
export function childShare(tree: StrategyTree, childId: BlockId): AssetShare {
  const child = tree.blocks[childId];
  if (!child?.parentId) return { kind: 'none' };
  const parent = tree.blocks[child.parentId];
  if (!parent || !hasChildren(parent)) return { kind: 'none' };
  const siblings = parent.childIds.filter((id) => tree.blocks[id]?.type !== 'else');
  if (parent.type === 'filter') return { kind: 'picked', pct: null };
  if (parent.type === 'weight') {
    if (parent.method === 'specified')
      return { kind: 'fixed', pct: parent.allocations[childId] ?? 0 };
    const filter = parent.parentId ? tree.blocks[parent.parentId] : undefined;
    if (parent.method === 'equal' && filter?.type === 'filter') {
      return {
        kind: 'picked',
        pct: 100 / Math.max(1, Math.min(filter.config.count, siblings.length)),
      };
    }
    if (parent.method === 'equal')
      return { kind: 'equal', pct: 100 / Math.max(1, siblings.length) };
    return { kind: 'ranked', method: parent.method };
  }
  if (parent.type === 'if' || parent.type === 'else') {
    return { kind: 'equal', pct: 100 / Math.max(1, siblings.length) };
  }
  return { kind: 'none' };
}

function allocationToken(blockId: BlockId, pct: number): OutlineToken {
  return token('asset.weight', blockId, pct, `${formatNumber(pct)}%`, {
    type: 'number',
    min: 0,
    max: 100,
    step: 0.5,
    integer: false,
    suffix: '%',
  });
}

function lineParts(tree: StrategyTree, block: Block): OutlinePart[] {
  switch (block.type) {
    case 'if':
      return [text('If '), ...conditionParts(block.condition, block.id)];
    case 'else':
      return [text('Otherwise')];
    case 'weight':
      return weightParts(block);
    case 'filter':
      return filterParts(block.id, block.config);
    case 'group': {
      const parts = [
        text('the group '),
        token('group.name', block.id, block.name, block.name, { type: 'text' }),
      ];
      const share = childShare(tree, block.id);
      if (share.kind === 'fixed') parts.push(text(' at '), allocationToken(block.id, share.pct));
      else if (share.kind === 'equal') parts.push(text(` at ${formatNumber(share.pct)}%`));
      return parts;
    }
    case 'asset': {
      const share = childShare(tree, block.id);
      return share.kind === 'fixed' ? [allocationToken(block.id, share.pct)] : [];
    }
    case 'root':
      return [];
  }
}

function countDescendantLines(tree: StrategyTree, block: Block): number {
  if (!hasChildren(block)) return 0;
  return block.childIds.reduce((n, id) => {
    const child = tree.blocks[id];
    return child ? n + 1 + countDescendantLines(tree, child) : n;
  }, 0);
}

/** Number the rules in reading order, keyed by block id. Assets are not rules. */
export function ruleNumbers(tree: StrategyTree): Map<BlockId, number> {
  const out = new Map<BlockId, number>();
  let n = 0;
  const walk = (id: BlockId) => {
    const block = tree.blocks[id];
    if (!block) return;
    if (block.type !== 'root' && block.type !== 'asset') out.set(id, ++n);
    if (hasChildren(block)) block.childIds.forEach(walk);
  };
  walk(tree.rootId);
  return out;
}

/** The outline of a tree, one line per block in reading order. */
export function buildOutline(tree: StrategyTree, options: OutlineOptions = {}): OutlineLine[] {
  const maxDepth = options.maxDepth ?? Number.POSITIVE_INFINITY;
  const expanded = options.expanded ?? new Set<BlockId>();
  const numbers = ruleNumbers(tree);
  const lines: OutlineLine[] = [];

  const visit = (id: BlockId, depth: number) => {
    const block = tree.blocks[id];
    if (!block) return;
    const children = hasChildren(block) ? block.childIds : [];
    if (block.type !== 'root') {
      const line: OutlineLine = {
        key: block.id,
        blockId: block.id,
        kind: block.type,
        number: numbers.get(block.id) ?? null,
        depth,
        parts: lineParts(tree, block),
      };
      if (block.type === 'asset') {
        line.symbol = block.symbol;
        line.name =
          block.displayName && block.displayName !== block.symbol ? block.displayName : undefined;
        line.share = childShare(tree, block.id);
      }
      lines.push(line);
      if (children.length > 0 && depth + 1 >= maxDepth && !expanded.has(block.id)) {
        const hidden = countDescendantLines(tree, block);
        const hasRules = children.some((c) => tree.blocks[c]?.type !== 'asset');
        if (hasRules) {
          lines.push({
            key: `${block.id}:collapsed`,
            blockId: block.id,
            kind: 'collapsed',
            number: null,
            depth: depth + 1,
            parts: [text(`${hidden} more ${hidden === 1 ? 'line' : 'lines'} inside`)],
            hiddenCount: hidden,
          });
          return;
        }
      }
    }
    const childDepth = block.type === 'root' ? 0 : depth + 1;
    children.forEach((c) => visit(c, childDepth));
  };

  visit(tree.rootId, 0);
  return lines;
}

/** Plain text of a line's parts, for screen readers, notes and tests. */
export function partsText(parts: readonly OutlinePart[]): string {
  return parts.map((p) => p.text).join('');
}

/** A line read aloud: "1. If the 14-day RSI of SPY is above 70". */
export function lineText(line: OutlineLine): string {
  if (line.kind === 'asset') {
    const weight = partsText(line.parts);
    return [line.symbol, weight].filter(Boolean).join(' ');
  }
  return partsText(line.parts);
}

// Holdings as written

export interface WrittenHolding {
  symbol: string;
  /** Portfolio weight in percent when every step above it is fixed or equal; null when ranked. */
  pct: number | null;
}

export interface WrittenScenario {
  /** "Always", or which rules hold: "If rule 1 holds", "If rule 1 doesn't hold". */
  label: string;
  holdings: WrittenHolding[];
  /** Weighting methods that decide at each rebalance, so the weights aren't known in advance. */
  rankedBy: WeightMethod[];
}

const MAX_SCENARIOS = 8;

interface Choice {
  ifId: BlockId;
  holds: boolean;
}

function pairedElse(tree: StrategyTree, ifId: BlockId): BlockId | null {
  const ifBlock = tree.blocks[ifId];
  if (!ifBlock?.parentId) return null;
  const parent = tree.blocks[ifBlock.parentId];
  if (!parent || !hasChildren(parent)) return null;
  for (const id of parent.childIds) {
    const b = tree.blocks[id];
    if (b?.type === 'else' && b.ifBlockId === ifId) return id;
  }
  return null;
}

function collectIfs(tree: StrategyTree): BlockId[] {
  const out: BlockId[] = [];
  const walk = (id: BlockId) => {
    const b = tree.blocks[id];
    if (!b) return;
    if (b.type === 'if') out.push(id);
    if (hasChildren(b)) b.childIds.forEach(walk);
  };
  walk(tree.rootId);
  return out;
}

function holdingsFor(tree: StrategyTree, choices: ReadonlyMap<BlockId, boolean>) {
  const pcts = new Map<string, number | null>();
  const ranked = new Set<WeightMethod>();
  const add = (symbol: string, pct: number | null) => {
    const prev = pcts.get(symbol);
    if (prev === undefined) pcts.set(symbol, pct);
    else pcts.set(symbol, prev === null || pct === null ? null : prev + pct);
  };

  const skipped = (b: Block): boolean => {
    if (b.type === 'if') return choices.get(b.id) === false;
    if (b.type === 'else') return choices.get(b.ifBlockId) !== false;
    return false;
  };

  const walk = (id: BlockId, share: number | null) => {
    const b = tree.blocks[id];
    if (!b) return;
    if (b.type === 'asset') {
      add(b.symbol, share);
      return;
    }
    if (!hasChildren(b)) return;
    if (b.type === 'filter') ranked.add('momentum');
    const live = b.childIds.filter((c) => {
      const child = tree.blocks[c];
      return child !== undefined && !skipped(child);
    });
    const contentCount = live.filter((c) => {
      const t = tree.blocks[c]?.type;
      return t !== 'if' && t !== 'else';
    }).length;
    const branchCount = live.length - contentCount;
    for (const c of live) {
      const child = tree.blocks[c];
      if (!child) continue;
      if (child.type === 'if' || child.type === 'else') {
        walk(c, contentCount === 0 && branchCount > 0 ? share : null);
        continue;
      }
      let part: number | null;
      if (b.type === 'weight') {
        if (b.method === 'specified') part = (b.allocations[c] ?? 0) / 100;
        else if (b.method === 'equal') part = 1 / Math.max(1, contentCount);
        else {
          ranked.add(b.method);
          part = null;
        }
      } else if (b.type === 'filter') {
        part = null;
      } else {
        part = 1 / Math.max(1, contentCount);
      }
      walk(c, share === null || part === null ? null : share * part);
    }
  };

  walk(tree.rootId, 1);
  const holdings = [...pcts.entries()].map(([symbol, v]) => ({
    symbol,
    pct: v === null ? null : Math.round(v * 10000) / 100,
  }));
  holdings.sort((a, b) => (b.pct ?? -1) - (a.pct ?? -1));
  return { holdings, rankedBy: [...ranked] };
}

/**
 * What the strategy holds as written, per branch combination. Not an evaluation: weights decided
 * by ranking are null, and which branch applies today isn't known without market data.
 */
export function writtenScenarios(tree: StrategyTree): WrittenScenario[] {
  const ifs = collectIfs(tree);
  const numbers = ruleNumbers(tree);
  if (ifs.length === 0) {
    return [{ label: 'Always', ...holdingsFor(tree, new Map()) }];
  }
  const combos: Choice[][] = [];
  const count = Math.min(2 ** ifs.length, MAX_SCENARIOS);
  for (let mask = 0; mask < count; mask++) {
    combos.push(ifs.map((ifId, i) => ({ ifId, holds: (mask & (1 << i)) === 0 })));
  }
  const seen = new Set<string>();
  const out: WrittenScenario[] = [];
  for (const combo of combos) {
    const map = new Map(combo.map((c) => [c.ifId, c.holds]));
    const result = holdingsFor(tree, map);
    const sig = JSON.stringify(result.holdings);
    if (seen.has(sig)) continue;
    seen.add(sig);
    const relevant = combo.filter((c) => pairedElse(tree, c.ifId) !== null || c.holds);
    const label = relevant
      .map((c) => `rule ${numbers.get(c.ifId) ?? '?'} ${c.holds ? 'holds' : "doesn't hold"}`)
      .join(' and ');
    out.push({ label: label ? `If ${label}` : 'Always', ...result });
  }
  return out;
}

/** What the strategy holds as written when each if block takes the given side. */
export function holdingsWhen(
  tree: StrategyTree,
  choices: ReadonlyMap<BlockId, boolean>
): Pick<WrittenScenario, 'holdings' | 'rankedBy'> {
  return holdingsFor(tree, choices);
}

/** Longest lookback in days, the history a backtest needs before its first rebalance. */
export function longestLookback(tree: StrategyTree): number {
  let max = 0;
  const fromOperand = (op: ConditionOperand) => {
    if ((op.type === 'indicator' || op.type === 'metric') && op.period != null) {
      max = Math.max(max, op.period);
    }
    if (op.type === 'indicator' && op.slowPeriod != null) max = Math.max(max, op.slowPeriod);
  };
  for (const b of Object.values(tree.blocks)) {
    if (b.type === 'weight' && b.lookbackDays != null) max = Math.max(max, b.lookbackDays);
    if (b.type === 'filter') max = Math.max(max, filterLookbackDays(b.config));
    if (b.type === 'if') {
      fromOperand(b.condition.left);
      fromOperand(b.condition.right);
    }
  }
  return max;
}

/** Every symbol the strategy reads: held assets plus signal symbols in conditions. */
export function strategySymbols(
  tree: StrategyTree,
  benchmark = ''
): {
  held: string[];
  signals: string[];
} {
  const held = new Set<string>();
  const signals = new Set<string>();
  const fromOperand = (op: ConditionOperand) => {
    if (op.type !== 'number') signals.add(op.symbol);
  };
  for (const b of Object.values(tree.blocks)) {
    if (b.type === 'asset') held.add(b.symbol);
    if (b.type === 'if') {
      fromOperand(b.condition.left);
      fromOperand(b.condition.right);
    }
  }
  if (benchmark) signals.add(benchmark);
  return {
    held: [...held].sort(),
    signals: [...signals].filter((s) => !held.has(s)).sort(),
  };
}

// Edits

export type OutlineEdit =
  | { kind: 'condition'; blockId: BlockId; condition: ConditionExpression }
  | { kind: 'block'; blockId: BlockId; updates: Partial<Block> }
  | { kind: 'filter'; blockId: BlockId; config: FilterConfig }
  | { kind: 'allocation'; weightId: BlockId; childId: BlockId; percent: number }
  | { kind: 'timeframe'; value: string }
  | { kind: 'benchmark'; value: string }
  | { kind: 'invalid'; reason: string };

const SYMBOL_RE = /^[A-Z][A-Z0-9.-]{0,9}$/;

export function normaliseSymbol(raw: string): string {
  return raw.trim().toUpperCase();
}

export function isValidSymbol(raw: string): boolean {
  return SYMBOL_RE.test(normaliseSymbol(raw));
}

function parseNumber(raw: string, editor: TokenEditor): number | string {
  if (editor.type !== 'number') return 'Enter a number.';
  const v = Number(raw.trim().replace(/%$/, ''));
  if (!Number.isFinite(v) || raw.trim() === '') return 'Enter a number.';
  if (editor.integer && !Number.isInteger(v)) return 'Enter a whole number.';
  if (v < editor.min || v > editor.max) return `Enter a value from ${editor.min} to ${editor.max}.`;
  return v;
}

function editOperand(
  op: ConditionOperand,
  sub: string,
  raw: string,
  editor: TokenEditor
): ConditionOperand | string {
  if (sub === 'symbol') {
    if (op.type === 'number') return 'This value has no symbol.';
    if (!isValidSymbol(raw)) return 'Enter a ticker, for example SPY.';
    return { ...op, symbol: normaliseSymbol(raw) };
  }
  if (sub === 'value') {
    if (op.type !== 'number') return 'This value is not a number.';
    const v = parseNumber(raw, editor);
    return typeof v === 'string' ? v : { ...op, value: v };
  }
  if (sub === 'period') {
    if (op.type !== 'indicator' && op.type !== 'metric') return 'This value has no period.';
    const v = parseNumber(raw, editor);
    return typeof v === 'string' ? v : { ...op, period: v };
  }
  if (sub === 'indicator') {
    if (op.type !== 'indicator') return 'This value is not an indicator.';
    const info = INDICATORS.find((i) => i.name === raw);
    if (!info) return 'Choose an indicator from the list.';
    const next: IndicatorRef = { ...op, indicator: info.name };
    if (info.hasPeriod) next.period = op.period ?? info.defaultPeriod;
    else delete next.period;
    return next;
  }
  if (sub === 'field') {
    if (op.type !== 'price' || !(raw in PRICE_WORDS)) return 'Choose a price field from the list.';
    return { ...op, field: raw as PriceField };
  }
  if (sub === 'metric') {
    if (op.type !== 'metric' || !(raw in METRIC_WORDS)) return 'Choose a measure from the list.';
    return { ...op, metric: raw as MetricName };
  }
  return 'This value can’t be edited here.';
}

const inOptions = (editor: TokenEditor, raw: string) =>
  editor.type === 'choice' && editor.options.some((o) => o.value === raw);

/** Turn an edited token into a store operation. Never throws; a bad value comes back as invalid. */
export function applyTokenEdit(tree: StrategyTree, tok: OutlineToken, raw: string): OutlineEdit {
  const invalid = (reason: string): OutlineEdit => ({ kind: 'invalid', reason });
  if (tok.field === 'rebalance') {
    return inOptions(tok.editor, raw)
      ? { kind: 'timeframe', value: raw }
      : invalid('Choose a rebalance period.');
  }
  if (tok.field === 'benchmark') {
    if (raw.trim() === '') return { kind: 'benchmark', value: '' };
    return isValidSymbol(raw)
      ? { kind: 'benchmark', value: normaliseSymbol(raw) }
      : invalid('Enter a ticker, for example SPY.');
  }
  const block = tok.blockId ? tree.blocks[tok.blockId] : undefined;
  if (!block) return invalid('That part of the strategy no longer exists.');

  if (tok.field.startsWith('cond.')) {
    if (block.type !== 'if') return invalid('That rule is not a condition.');
    if (tok.field === 'cond.comparator') {
      if (!inOptions(tok.editor, raw)) return invalid('Choose a comparison from the list.');
      return {
        kind: 'condition',
        blockId: block.id,
        condition: { ...block.condition, comparator: raw as Comparator },
      };
    }
    const [, side, sub] = tok.field.split('.') as ['cond', Side, string];
    const next = editOperand(block.condition[side], sub, raw, tok.editor);
    if (typeof next === 'string') return invalid(next);
    return {
      kind: 'condition',
      blockId: block.id,
      condition: { ...block.condition, [side]: next },
    };
  }

  if (tok.field.startsWith('weight.')) {
    if (block.type !== 'weight') return invalid('That rule is not a weighting.');
    if (tok.field === 'weight.method') {
      if (!isSupportedMethod(raw)) return invalid('Choose a weighting the engine supports.');
      const method = raw as WeightMethod;
      const updates: Partial<WeightBlock> = { method };
      if (methodUsesLookback(method)) updates.lookbackDays = block.lookbackDays ?? 60;
      else updates.lookbackDays = undefined;
      if (method !== 'momentum') updates.top = undefined;
      if (method === 'specified' && Object.keys(block.allocations).length === 0) {
        const n = block.childIds.length;
        updates.allocations = Object.fromEntries(
          block.childIds.map((id) => [id, n ? Math.round((100 / n) * 100) / 100 : 0])
        );
      }
      return { kind: 'block', blockId: block.id, updates };
    }
    const v = parseNumber(raw, tok.editor);
    if (typeof v === 'string') return invalid(v);
    return {
      kind: 'block',
      blockId: block.id,
      updates: tok.field === 'weight.top' ? { top: v } : { lookbackDays: v },
    };
  }

  if (tok.field.startsWith('filter.')) {
    if (block.type !== 'filter') return invalid('That rule is not a filter.');
    const config: FilterConfig = { ...block.config };
    if (tok.field === 'filter.count') {
      const v = parseNumber(raw, tok.editor);
      if (typeof v === 'string') return invalid(v);
      config.count = v;
    } else {
      if (!inOptions(tok.editor, raw)) return invalid('Choose a value from the list.');
      if (tok.field === 'filter.selection') config.selection = raw as FilterConfig['selection'];
      if (tok.field === 'filter.sortBy') config.sortBy = raw as FilterSortBy;
      if (tok.field === 'filter.period') {
        config.period = raw as FilterPeriod;
        delete config.lookbackDays;
      }
    }
    return { kind: 'filter', blockId: block.id, config };
  }

  if (tok.field === 'group.name') {
    if (block.type !== 'group') return invalid('That rule is not a group.');
    const name = raw.trim();
    return name
      ? { kind: 'block', blockId: block.id, updates: { name } }
      : invalid('Enter a name.');
  }

  if (tok.field === 'asset.weight') {
    const parent = block.parentId ? tree.blocks[block.parentId] : undefined;
    if ((block.type !== 'asset' && block.type !== 'group') || parent?.type !== 'weight')
      return invalid('This holding has no fixed weight.');
    const v = parseNumber(raw, tok.editor);
    if (typeof v === 'string') return invalid(v);
    return { kind: 'allocation', weightId: parent.id, childId: block.id, percent: v };
  }

  return invalid('This value can’t be edited here.');
}

/** Specified weights under one weight block that don't add to 100, as a sentence. */
export function allocationProblem(tree: StrategyTree, weightId: BlockId): string | null {
  const b = tree.blocks[weightId];
  if (b?.type !== 'weight' || b.method !== 'specified' || b.childIds.length === 0) return null;
  const sum = b.childIds.reduce((s, id) => s + (b.allocations[id] ?? 0), 0);
  if (Math.abs(sum - 100) < 0.01) return null;
  return `These weights add up to ${formatNumber(Math.round(sum * 100) / 100)}%, not 100%.`;
}
