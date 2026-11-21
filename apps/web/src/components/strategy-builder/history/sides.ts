import type { BlockId, StrategyTree } from '@llamatrade/core/strategy/types';

import { dayKey, type TradeInput } from '../../../lib/backtestView';
import { partsText, conditionParts } from '../../../lib/outline';
import { rebalanceIndexes, type RebalanceEvery } from '../blocks/conditionHistory';

export interface ConditionSides {
  ifId: BlockId;
  /** "the 14-day RSI of SPY is above 70" */
  condition: string;
  when: ReadonlySet<string>;
  otherwise: ReadonlySet<string>;
}

function heldSymbols(tree: StrategyTree, id: BlockId, out: Set<string>) {
  const block = tree.blocks[id];
  if (!block) return;
  if (block.type === 'asset') {
    out.add(block.symbol);
    return;
  }
  if ('childIds' in block) for (const c of block.childIds) heldSymbols(tree, c, out);
}

/**
 * The first if/else whose two sides hold different symbols, found breadth first, so a
 * backtest's holdings can say which side was chosen. Null when there is none, or the
 * sides share a symbol and can't be told apart from holdings alone.
 */
export function conditionSides(tree: StrategyTree): ConditionSides | null {
  const queue: BlockId[] = [tree.rootId];
  while (queue.length) {
    const id = queue.shift() as BlockId;
    const block = tree.blocks[id];
    if (!block || !('childIds' in block)) continue;
    for (const childId of block.childIds) {
      const child = tree.blocks[childId];
      if (child?.type !== 'if') continue;
      const elseBlock = block.childIds
        .map((c) => tree.blocks[c])
        .find((b) => b?.type === 'else' && b.ifBlockId === child.id);
      if (!elseBlock) continue;
      const when = new Set<string>();
      const otherwise = new Set<string>();
      heldSymbols(tree, child.id, when);
      heldSymbols(tree, elseBlock.id, otherwise);
      const shared = [...when].some((s) => otherwise.has(s));
      if (when.size === 0 || otherwise.size === 0 || shared) return null;
      return {
        ifId: child.id,
        condition: partsText(conditionParts(child.condition, child.id)),
        when,
        otherwise,
      };
    }
    queue.push(...block.childIds);
  }
  return null;
}

export type SideKey = 'when' | 'otherwise';

export interface SideAt {
  date: Date;
  side: SideKey | null;
}

const DAY_MS = 86_400_000;

/** The side whose symbols are the only ones held at the end of `day`, or null for a mix or nothing. */
function sideOnDay(
  trades: readonly TradeInput[],
  day: string,
  sides: Pick<ConditionSides, 'when' | 'otherwise'>
): SideKey | null {
  const end = Date.parse(`${day}T00:00:00Z`) + DAY_MS;
  const held = new Set(
    trades
      .filter(
        (t) =>
          t.entryTime !== null &&
          t.entryTime.getTime() < end &&
          (t.exitTime === null || t.exitTime.getTime() >= end)
      )
      .map((t) => t.symbol)
  );
  const list = [...held];
  if (list.length > 0 && list.every((s) => sides.when.has(s))) return 'when';
  if (list.length > 0 && list.every((s) => sides.otherwise.has(s))) return 'otherwise';
  return null;
}

/** Which side the backtest held at the end of each of `dates`. */
export function sidesAtDates(
  trades: readonly TradeInput[],
  dates: readonly Date[],
  sides: Pick<ConditionSides, 'when' | 'otherwise'>
): SideAt[] {
  const days = [...new Set(dates.map(dayKey))].sort();
  return days.map((day) => ({
    date: new Date(`${day}T12:00:00Z`),
    side: sideOnDay(trades, day, sides),
  }));
}

/**
 * Which side each day with orders landed on, read from what the backtest held at the end of
 * that day. A day whose holdings mix both sides, or hold nothing, reads as unknown.
 */
export function sidesAtRebalances(
  trades: readonly TradeInput[],
  sides: Pick<ConditionSides, 'when' | 'otherwise'>
): SideAt[] {
  const days: Date[] = [];
  for (const t of trades) {
    if (t.entryTime) days.push(t.entryTime);
    if (t.exitTime) days.push(t.exitTime);
  }
  return sidesAtDates(trades, days, sides);
}

/**
 * The scheduled rebalances in a backtest's window: the first trading day of each period on
 * the curve's dates. Daily schedules return null, since every day would count.
 */
export function scheduledDates(dates: readonly Date[], every: RebalanceEvery): Date[] | null {
  if (every === 'daily') return null;
  return rebalanceIndexes(dates, every).map((i) => dates[i]);
}

export interface SideCounts {
  when: number;
  otherwise: number;
  unknown: number;
  /** Rebalances read as one side or the other. */
  known: number;
  total: number;
}

export function sideCounts(points: readonly SideAt[]): SideCounts {
  const when = points.filter((p) => p.side === 'when').length;
  const otherwise = points.filter((p) => p.side === 'otherwise').length;
  return {
    when,
    otherwise,
    unknown: points.length - when - otherwise,
    known: when + otherwise,
    total: points.length,
  };
}

export interface SideSpan {
  side: SideKey;
  from: Date;
  to: Date;
}

/** Consecutive rebalances on one side joined into spans that run to the next rebalance. */
export function sideSpans(points: readonly SideAt[], end: Date): SideSpan[] {
  const out: SideSpan[] = [];
  points.forEach((p, i) => {
    if (!p.side) return;
    const to = points[i + 1]?.date ?? end;
    const last = out[out.length - 1];
    if (last && last.side === p.side && last.to.getTime() === p.date.getTime()) last.to = to;
    else out.push({ side: p.side, from: p.date, to });
  });
  return out;
}

/**
 * The side a selected block sits on, read against the saved rules: `toSaved` maps the draft's
 * block ids to the saved ones. Null when the selection is outside both sides.
 */
export function sideOfBlock(
  tree: StrategyTree,
  blockId: BlockId | null,
  ifId: BlockId,
  toSaved: ReadonlyMap<BlockId, BlockId>
): SideKey | null {
  let id: BlockId | null = blockId;
  while (id) {
    const block: StrategyTree['blocks'][BlockId] | undefined = tree.blocks[id];
    if (!block) return null;
    if (block.type === 'if' && toSaved.get(block.id) === ifId) return 'when';
    if (block.type === 'else' && toSaved.get(block.ifBlockId) === ifId) return 'otherwise';
    id = block.parentId ?? null;
  }
  return null;
}
