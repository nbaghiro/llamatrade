import type { BlockId, StrategyTree } from '@llamatrade/core/strategy/types';

import { dayKey, type TradeInput } from '../../../lib/backtestView';
import { partsText, conditionParts } from '../../../lib/outline';

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

/**
 * Which side each rebalance landed on, read from what the backtest held at the end of
 * that day. A day whose holdings mix both sides, or hold nothing, reads as unknown.
 */
export function sidesAtRebalances(
  trades: readonly TradeInput[],
  sides: Pick<ConditionSides, 'when' | 'otherwise'>
): SideAt[] {
  const days = new Set<string>();
  for (const t of trades) {
    if (t.entryTime) days.add(dayKey(t.entryTime));
    if (t.exitTime) days.add(dayKey(t.exitTime));
  }
  return [...days].sort().map((day) => {
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
    let side: SideKey | null = null;
    if (list.length > 0 && list.every((s) => sides.when.has(s))) side = 'when';
    else if (list.length > 0 && list.every((s) => sides.otherwise.has(s))) side = 'otherwise';
    return { date: new Date(`${day}T12:00:00Z`), side };
  });
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
