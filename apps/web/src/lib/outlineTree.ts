/**
 * Shared shape of an outline drawn as a tree: guide lines into each row, collapsing, and the
 * path a running session holds today. Pure functions; `ui/TreeRow` draws what these return.
 */

import { hasChildren, type BlockId, type StrategyTree } from '@llamatrade/core/strategy/types';

import type { OutlineLineKind } from './outline';

export interface Guide {
  /** The line turns into this row at this level. */
  elbow: boolean;
  /** The line carries on below this row at this level. */
  down: boolean;
  liveUp: boolean;
  liveDown: boolean;
  liveAcross: boolean;
}

export interface FlatRow {
  id: string;
  depth: number;
}

/** Whether each row of a flat outline has rows nested under it. */
export function withKids<T extends FlatRow>(rows: readonly T[]): (T & { kids: boolean })[] {
  return rows.map((r, i) => ({ ...r, kids: (rows[i + 1]?.depth ?? -1) > r.depth }));
}

/** Drops the rows under each closed row, counting them on it. */
export function collapse<T extends FlatRow & { kids: boolean }>(
  rows: readonly T[],
  closed: ReadonlySet<string>
): (T & { hidden: number })[] {
  const shown: (T & { hidden: number })[] = [];
  let hideBelow = Infinity;
  rows.forEach((r, i) => {
    if (r.depth > hideBelow) return;
    hideBelow = Infinity;
    let hidden = 0;
    if (r.kids && closed.has(r.id)) {
      hideBelow = r.depth;
      for (let j = i + 1; j < rows.length && rows[j].depth > r.depth; j++) hidden++;
    }
    shown.push({ ...r, hidden });
  });
  return shown;
}

/** The guide lines of each row, with the live path picked out. */
export function guidesOf(rows: readonly { depth: number; live: boolean }[]): Guide[][] {
  const later = (r: number, level: number, liveOnly: boolean) => {
    for (let j = r + 1; j < rows.length; j++) {
      if (rows[j].depth <= level) return false;
      if (rows[j].depth === level + 1 && (!liveOnly || rows[j].live)) return true;
    }
    return false;
  };
  const ancestorLive = (r: number, level: number) => {
    for (let j = r; j >= 0; j--) if (rows[j].depth === level) return rows[j].live;
    return false;
  };
  return rows.map((r, i) =>
    Array.from({ length: r.depth }, (_, level): Guide => {
      const parentLive = ancestorLive(i, level);
      const elbow = level === r.depth - 1;
      const liveDown = parentLive && later(i, level, true);
      return {
        elbow,
        down: later(i, level, false),
        liveUp: elbow ? parentLive && (r.live || liveDown) : liveDown,
        liveDown,
        liveAcross: elbow && parentLive && r.live,
      };
    })
  );
}

/** Ids of a row and every row above it. */
export function ancestors(rows: readonly FlatRow[], id: string): Set<string> {
  const out = new Set<string>();
  const i = rows.findIndex((r) => r.id === id);
  if (i < 0) return out;
  out.add(id);
  let depth = rows[i].depth;
  for (let j = i - 1; j >= 0 && depth > 0; j--) {
    if (rows[j].depth < depth) {
      out.add(rows[j].id);
      depth = rows[j].depth;
    }
  }
  return out;
}

function symbolsUnder(tree: StrategyTree, id: BlockId): string[] {
  const block = tree.blocks[id];
  if (!block) return [];
  if (block.type === 'asset') return [block.symbol];
  return hasChildren(block) ? block.childIds.flatMap((c) => symbolsUnder(tree, c)) : [];
}

/**
 * The blocks on the path a session holds today: each held asset and its parents. Of an if and its
 * otherwise, the side covering more of the holdings wins, so a shared symbol doesn't light both.
 */
export function heldPath(tree: StrategyTree, held: ReadonlySet<string>): Set<BlockId> {
  const out = new Set<BlockId>();
  if (held.size === 0) return out;
  const covers = (id: BlockId) => symbolsUnder(tree, id).filter((s) => held.has(s)).length;
  const walk = (id: BlockId): boolean => {
    const block = tree.blocks[id];
    if (!block) return false;
    if (block.type === 'asset') {
      if (!held.has(block.symbol)) return false;
      out.add(id);
      return true;
    }
    if (!hasChildren(block)) return false;
    let any = false;
    const handled = new Set<BlockId>();
    for (const childId of block.childIds) {
      if (handled.has(childId)) continue;
      const child = tree.blocks[childId];
      if (child?.type === 'if') {
        const elseId = block.childIds.find((c) => {
          const b = tree.blocks[c];
          return b?.type === 'else' && b.ifBlockId === childId;
        });
        if (elseId) handled.add(elseId);
        const pick = elseId && covers(elseId) > covers(childId) ? elseId : childId;
        if (covers(pick) > 0 && walk(pick)) any = true;
        continue;
      }
      if (walk(childId)) any = true;
    }
    if (any) out.add(id);
    return any;
  };
  walk(tree.rootId);
  return out;
}

/** Words the type label already says, dropped from the front of a rule's sentence. */
const LEADS: Partial<Record<OutlineLineKind, readonly string[]>> = {
  if: ['If '],
  weight: ['hold at ', 'hold '],
  filter: ['pick the '],
  group: ['the group '],
};

/** A rule's sentence without the words its type label says, e.g. "If " under IF. */
export function phraseParts<P extends { kind: string; text: string }>(
  kind: OutlineLineKind,
  parts: readonly P[]
): P[] {
  const [first, ...rest] = parts;
  const lead = LEADS[kind]?.find((l) => first?.kind === 'text' && first.text.startsWith(l));
  if (!first || !lead) return [...parts];
  const remaining = first.text.slice(lead.length);
  return remaining ? [{ ...first, text: remaining }, ...rest] : rest;
}
