/**
 * Which side each rule picks today, worked out in the browser from daily closes. Only
 * close-based indicators and prices can be read this way; anything else stays unknown and
 * the page says so rather than guessing.
 */

import {
  compares,
  indicatorFromCloses,
  isDrawableIndicator,
  warmupBars,
} from '@llamatrade/core/strategy/indicators';
import {
  type BlockId,
  type ConditionExpression,
  type ConditionOperand,
  type IfBlock,
  type StrategyTree,
} from '@llamatrade/core/strategy/types';

export interface DailySeries {
  dates: Date[];
  closes: number[];
}

/** One operand's daily values aligned to its symbol's dates, or null when it can't be read. */
export function operandSeries(
  op: ConditionOperand,
  bars: ReadonlyMap<string, DailySeries>
): { dates: Date[]; values: number[] } | null {
  if (op.type === 'number') return null;
  const s = bars.get(op.symbol);
  if (!s || s.closes.length === 0) return null;
  if (op.type === 'price') {
    if (op.field !== 'current' && op.field !== 'close') return null;
    return { dates: s.dates, values: s.closes };
  }
  if (op.type === 'indicator') {
    if (!isDrawableIndicator(op.indicator)) return null;
    return {
      dates: s.dates,
      values: indicatorFromCloses(op.indicator, s.closes, op.period ?? 14),
    };
  }
  return null;
}

/** Bars of warm-up an operand needs before its first value. */
export function operandWarmup(op: ConditionOperand): number {
  if (op.type === 'indicator' && isDrawableIndicator(op.indicator)) {
    return warmupBars(op.indicator, op.period ?? 14);
  }
  return 0;
}

/** Symbols whose closes the readable conditions need. */
export function readableSymbols(tree: StrategyTree): string[] {
  const out = new Set<string>();
  for (const b of Object.values(tree.blocks)) {
    if (b.type !== 'if' || !isReadable(b.condition)) continue;
    for (const op of [b.condition.left, b.condition.right]) {
      if (op.type !== 'number') out.add(op.symbol);
    }
  }
  return [...out].sort();
}

const readableOperand = (op: ConditionOperand) =>
  op.type === 'number' ||
  (op.type === 'price' && (op.field === 'current' || op.field === 'close')) ||
  (op.type === 'indicator' && isDrawableIndicator(op.indicator));

/** True when both sides can be computed from daily closes, and at least one isn't a number. */
export function isReadable(c: ConditionExpression): boolean {
  return (
    readableOperand(c.left) &&
    readableOperand(c.right) &&
    !(c.left.type === 'number' && c.right.type === 'number')
  );
}

export interface ConditionHistory {
  dates: Date[];
  left: number[];
  /** The other side per day: the threshold repeated, or the right operand's values. */
  right: number[];
  held: boolean[];
}

/** Both sides of a condition over the shared dates of their series. */
export function conditionHistory(
  c: ConditionExpression,
  bars: ReadonlyMap<string, DailySeries>
): ConditionHistory | null {
  if (!isReadable(c)) return null;
  const l = operandSeries(c.left, bars);
  const r = operandSeries(c.right, bars);
  const base = l ?? r;
  if (!base) return null;
  const at = (s: { dates: Date[]; values: number[] } | null, op: ConditionOperand) => {
    if (op.type === 'number') return () => op.value;
    if (!s) return () => NaN;
    const byDay = new Map(s.dates.map((d, i) => [d.toISOString().slice(0, 10), s.values[i]]));
    return (d: Date) => byDay.get(d.toISOString().slice(0, 10)) ?? NaN;
  };
  const leftAt = at(l, c.left);
  const rightAt = at(r, c.right);
  const left = base.dates.map(leftAt);
  const right = base.dates.map(rightAt);
  const held = left.map(
    (v, i) => Number.isFinite(v) && Number.isFinite(right[i]) && compares(v, c.comparator, right[i])
  );
  return { dates: base.dates, left, right, held };
}

export interface Reading {
  value: number;
  against: number;
  holds: boolean;
  asOf: Date;
}

/** The latest day both sides have a value. */
export function latestReading(h: ConditionHistory): Reading | null {
  for (let i = h.dates.length - 1; i >= 0; i--) {
    if (Number.isFinite(h.left[i]) && Number.isFinite(h.right[i])) {
      return { value: h.left[i], against: h.right[i], holds: h.held[i], asOf: h.dates[i] };
    }
  }
  return null;
}

export interface RebalanceCount {
  held: number;
  total: number;
  /** The last rebalance where the side changed, with the reading that day. */
  lastSwitch: { at: Date; value: number } | null;
}

/** At how many of the given rebalance days the condition held, from `from` on. */
export function countAtRebalances(
  h: ConditionHistory,
  rebalanceIdx: readonly number[],
  from: Date | null = null
): RebalanceCount {
  const idx = rebalanceIdx.filter(
    (i) =>
      i < h.dates.length &&
      Number.isFinite(h.left[i]) &&
      (from === null || h.dates[i].getTime() >= from.getTime())
  );
  let lastSwitch: RebalanceCount['lastSwitch'] = null;
  idx.forEach((i, k) => {
    if (k > 0 && h.held[i] !== h.held[idx[k - 1]])
      lastSwitch = { at: h.dates[i], value: h.left[i] };
  });
  return { held: idx.filter((i) => h.held[i]).length, total: idx.length, lastSwitch };
}

/** Today's side for every if block, or null when any of them can't be read. */
export function todaysChoices(
  tree: StrategyTree,
  readings: ReadonlyMap<BlockId, Reading | null>
): Map<BlockId, boolean> | null {
  const out = new Map<BlockId, boolean>();
  for (const b of Object.values(tree.blocks)) {
    if (b.type !== 'if') continue;
    const r = readings.get(b.id);
    if (!r) return null;
    out.set(b.id, r.holds);
  }
  return out;
}

/** If blocks whose condition this module can read. */
export function readableIfs(tree: StrategyTree): IfBlock[] {
  return Object.values(tree.blocks).filter(
    (b): b is IfBlock => b.type === 'if' && isReadable(b.condition)
  );
}

export interface BranchSpan {
  holds: boolean;
  from: Date;
  to: Date;
}

/**
 * Which side the rule took at each rebalance between `from` and `to`, joined into spans that
 * run to the next rebalance (the last one runs to `to`).
 */
export function branchSpans(
  h: Pick<ConditionHistory, 'dates' | 'left' | 'held'>,
  rebalanceIdx: readonly number[],
  from: Date,
  to: Date
): BranchSpan[] {
  const idx = rebalanceIdx.filter(
    (i) =>
      i < h.dates.length &&
      Number.isFinite(h.left[i]) &&
      h.dates[i].getTime() >= from.getTime() &&
      h.dates[i].getTime() <= to.getTime()
  );
  const out: BranchSpan[] = [];
  idx.forEach((i, k) => {
    const end = k + 1 < idx.length ? h.dates[idx[k + 1]] : to;
    const last = out[out.length - 1];
    if (last && last.holds === h.held[i]) last.to = end;
    else out.push({ holds: h.held[i], from: h.dates[i], to: end });
  });
  return out;
}

/** A reading for display: whole numbers as they are, others to one decimal, large ones grouped. */
export function readingText(v: number): string {
  if (Number.isInteger(v)) return v.toLocaleString('en-US');
  return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('en-US') : v.toFixed(1);
}
