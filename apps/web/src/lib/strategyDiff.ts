/**
 * What changed between two versions of a strategy, block by block and value by value. Blocks are
 * matched by their place in the tree, so an edited value reads as a change rather than a removal
 * and an addition. The result renders as the outline with old wording struck, and as sentences.
 */

import {
  hasChildren,
  type Block,
  type BlockId,
  type StrategyTree,
} from '@llamatrade/core/strategy/types';

import {
  buildOutline,
  lineText,
  metaParts,
  partsText,
  type OutlineLine,
  type OutlineMeta,
  type OutlinePart,
  type OutlineText,
  type OutlineToken,
  type TokenField,
} from './outline';

export interface StrategySide {
  tree: StrategyTree;
  meta: OutlineMeta;
  name?: string;
}

export type DiffToken = OutlineToken & { was?: string };
export type DiffPart = OutlineText | DiffToken;
export type DiffStatus = 'same' | 'changed' | 'added' | 'removed';

export interface DiffLine extends Omit<OutlineLine, 'parts'> {
  status: DiffStatus;
  parts: DiffPart[];
  /** The old sentence, when its shape changed so values can't be compared one by one. */
  wasParts?: OutlinePart[];
}

export interface StrategyDiff {
  meta: DiffPart[];
  lines: DiffLine[];
  name: { from: string; to: string } | null;
  /** The change in words, one sentence per change. */
  changes: string[];
}

function blockKey(block: Block): string {
  if (block.type === 'asset') return `asset:${block.symbol}`;
  return block.type;
}

/** Longest common subsequence of two key lists, as index pairs. */
function lcsPairs<T>(
  a: readonly T[],
  b: readonly T[],
  eq: (x: T, y: T) => boolean
): Array<[number, number]> {
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = eq(a[i], b[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: Array<[number, number]> = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (eq(a[i], b[j])) {
      out.push([i, j]);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  return out;
}

/** Pairs each block in `after` with its counterpart in `before`, keyed by the after id. */
export function matchBlocks(before: StrategyTree, after: StrategyTree): Map<BlockId, BlockId> {
  const out = new Map<BlockId, BlockId>();
  const walk = (beforeId: BlockId, afterId: BlockId) => {
    out.set(afterId, beforeId);
    const b = before.blocks[beforeId];
    const a = after.blocks[afterId];
    if (!b || !a || !hasChildren(b) || !hasChildren(a)) return;
    const bKids = b.childIds.filter((id) => before.blocks[id]);
    const aKids = a.childIds.filter((id) => after.blocks[id]);
    const bKeys = bKids.map((id) => blockKey(before.blocks[id]));
    const aKeys = aKids.map((id) => blockKey(after.blocks[id]));
    for (const [i, j] of lcsPairs(bKeys, aKeys, (x, y) => x === y)) walk(bKids[i], aKids[j]);
  };
  if (before.blocks[before.rootId] && after.blocks[after.rootId]) walk(before.rootId, after.rootId);
  return out;
}

const sameShape = (a: readonly OutlinePart[], b: readonly OutlinePart[]): boolean =>
  a.length === b.length &&
  a.every((p, i) => {
    const q = b[i];
    if (p.kind !== q.kind) return false;
    if (p.kind === 'text') return p.text === q.text;
    return q.kind === 'token' && p.field === q.field;
  });

/** Annotates `now` tokens with their old text where the value changed; null if the shapes differ. */
function compareParts(was: readonly OutlinePart[], now: readonly OutlinePart[]): DiffPart[] | null {
  if (!sameShape(was, now)) return null;
  return now.map((p, i) => {
    const old = was[i];
    if (p.kind === 'token' && old.kind === 'token' && old.value !== p.value) {
      return { ...p, was: old.text };
    }
    return p;
  });
}

const hasWas = (parts: readonly DiffPart[]) =>
  parts.some((p) => p.kind === 'token' && p.was !== undefined);

function annotate(line: OutlineLine, status: DiffStatus, extra: Partial<DiffLine> = {}): DiffLine {
  return { ...line, status, parts: line.parts, ...extra };
}

const FIELD_LABELS: Record<string, string> = {
  rebalance: 'rebalance',
  benchmark: 'benchmark',
  period: 'period',
  indicator: 'indicator',
  symbol: 'symbol',
  field: 'price',
  metric: 'measure',
  comparator: 'comparison',
  'weight.method': 'weighting',
  'weight.lookback': 'lookback',
  'weight.top': 'number held',
  'filter.selection': 'selection',
  'filter.count': 'count',
  'filter.sortBy': 'ranking',
  'filter.period': 'lookback',
  'group.name': 'name',
  'asset.weight': 'weight',
};

export function fieldLabel(field: TokenField): string {
  if (field === 'cond.right.value') return 'threshold';
  if (field === 'cond.left.value') return 'value';
  if (field === 'cond.comparator') return 'comparison';
  if (field.startsWith('cond.')) return FIELD_LABELS[field.split('.')[2]] ?? 'value';
  return FIELD_LABELS[field] ?? 'value';
}

function withUnit(text: string, unit: string | undefined): string {
  return unit ? `${text} ${unit}` : text;
}

function tokenChanges(parts: readonly DiffPart[]): string[] {
  return parts
    .filter((p): p is DiffToken => p.kind === 'token' && p.was !== undefined)
    .map(
      (p) =>
        `${fieldLabel(p.field)} from ${withUnit(p.was ?? '', p.unit)} to ${withUnit(p.text, p.unit)}`
    );
}

const capitalise = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

function parentRule(
  tree: StrategyTree,
  numbers: Map<BlockId, number>,
  blockId: BlockId
): number | null {
  let id = tree.blocks[blockId]?.parentId ?? null;
  while (id) {
    const n = numbers.get(id);
    if (n !== undefined) return n;
    id = tree.blocks[id]?.parentId ?? null;
  }
  return null;
}

function hasAncestorIn(tree: StrategyTree, blockId: BlockId, set: ReadonlySet<BlockId>): boolean {
  let id = tree.blocks[blockId]?.parentId ?? null;
  while (id) {
    if (set.has(id)) return true;
    id = tree.blocks[id]?.parentId ?? null;
  }
  return false;
}

function numbersOf(lines: readonly OutlineLine[]): Map<BlockId, number> {
  const out = new Map<BlockId, number>();
  for (const l of lines) if (l.number !== null) out.set(l.blockId, l.number);
  return out;
}

const ruleRef = (n: number | null) => (n === null ? 'the strategy' : `rule ${n}`);

/** Diffs two versions. `before` is the older one; the lines follow `after`'s reading order. */
export function diffStrategies(before: StrategySide, after: StrategySide): StrategyDiff {
  const match = matchBlocks(before.tree, after.tree);
  const matchedBefore = new Set(match.values());
  const beforeLines = buildOutline(before.tree);
  const afterLines = buildOutline(after.tree);
  const beforeByBlock = new Map(beforeLines.map((l) => [l.blockId, l]));
  const beforeNumbers = numbersOf(beforeLines);
  const afterNumbers = numbersOf(afterLines);
  const changes: string[] = [];

  const name =
    before.name !== undefined && after.name !== undefined && before.name !== after.name
      ? { from: before.name, to: after.name }
      : null;
  if (name) changes.push(`Renamed from “${name.from}” to “${name.to}”`);

  const metaNow = metaParts(after.meta);
  const meta = compareParts(metaParts(before.meta), metaNow) ?? metaNow;
  for (const c of tokenChanges(meta)) changes.push(capitalise(c));

  const added = new Set(afterLines.filter((l) => !match.has(l.blockId)).map((l) => l.blockId));
  const removedLines = beforeLines.filter((l) => !matchedBefore.has(l.blockId));
  const removed = new Set(removedLines.map((l) => l.blockId));

  const merged: DiffLine[] = afterLines.map((line) => {
    const beforeId = match.get(line.blockId);
    if (beforeId === undefined) {
      if (!hasAncestorIn(after.tree, line.blockId, added)) {
        changes.push(
          line.kind === 'asset'
            ? `Added ${line.symbol} to ${ruleRef(parentRule(after.tree, afterNumbers, line.blockId))}`
            : `Added rule ${line.number}: ${lineText(line)}`
        );
      }
      return annotate(line, 'added');
    }
    const old = beforeByBlock.get(beforeId);
    if (!old) return annotate(line, 'same');
    const compared = compareParts(old.parts, line.parts);
    if (compared === null) {
      const where =
        line.kind === 'asset'
          ? `${line.symbol} in ${ruleRef(parentRule(after.tree, afterNumbers, line.blockId))}`
          : `Rule ${line.number}`;
      changes.push(`${where} now reads “${lineText(line)}”, was “${lineText(old)}”`);
      return annotate(line, 'changed', { wasParts: old.parts });
    }
    if (hasWas(compared)) {
      const prefix =
        line.kind === 'asset'
          ? `${line.symbol} in ${ruleRef(parentRule(after.tree, afterNumbers, line.blockId))}: `
          : `Rule ${line.number}: `;
      for (const c of tokenChanges(compared)) changes.push(prefix + c);
      return annotate(line, 'changed', { parts: compared });
    }
    return annotate(line, 'same', { parts: compared });
  });

  // Each removed line goes after the nearest earlier line that survived, so it reads in place.
  const afterIdOfBefore = new Map<BlockId, BlockId>();
  for (const [a, b] of match) afterIdOfBefore.set(b, a);
  const inserts = new Map<string, DiffLine[]>();
  let anchor = '^';
  for (const line of beforeLines) {
    const survivor = afterIdOfBefore.get(line.blockId);
    if (survivor !== undefined) {
      anchor = survivor;
      continue;
    }
    const list = inserts.get(anchor) ?? [];
    list.push(annotate(line, 'removed', { key: `removed:${line.key}` }));
    inserts.set(anchor, list);
    if (!hasAncestorIn(before.tree, line.blockId, removed)) {
      changes.push(
        line.kind === 'asset'
          ? `Removed ${line.symbol} from ${ruleRef(parentRule(before.tree, beforeNumbers, line.blockId))}`
          : `Removed rule ${line.number}: ${lineText(line)}`
      );
    }
  }

  const lines: DiffLine[] = [...(inserts.get('^') ?? [])];
  for (const line of merged) {
    lines.push(line);
    lines.push(...(inserts.get(line.blockId) ?? []));
  }

  return { meta, lines, name, changes };
}

export function hasChanges(diff: StrategyDiff): boolean {
  return diff.changes.length > 0;
}

/** A one-line note for a save, from the first change, or a count when there are several. */
export function suggestNote(diff: StrategyDiff): string {
  if (diff.changes.length === 0) return '';
  if (diff.changes.length === 1) return diff.changes[0];
  return `${diff.changes[0]}, and ${diff.changes.length - 1} more ${diff.changes.length === 2 ? 'change' : 'changes'}`;
}

export function diffPartsText(parts: readonly DiffPart[]): string {
  return partsText(parts);
}

// Code diff

export interface CodeLine {
  kind: 'same' | 'add' | 'del';
  text: string;
  /** 1-based line number in the old text (same and del). */
  oldLine?: number;
  /** 1-based line number in the new text (same and add). */
  newLine?: number;
}

const MAX_LCS_CELLS = 4_000_000;

/** A line diff of two texts, deletions before additions within each changed run. */
export function diffCode(oldText: string, newText: string): CodeLine[] {
  const a = oldText === '' ? [] : oldText.split('\n');
  const b = newText === '' ? [] : newText.split('\n');
  const pairs = a.length * b.length > MAX_LCS_CELLS ? [] : lcsPairs(a, b, (x, y) => x === y);
  const out: CodeLine[] = [];
  let i = 0;
  let j = 0;
  const flush = (toI: number, toJ: number) => {
    for (; i < toI; i++) out.push({ kind: 'del', text: a[i], oldLine: i + 1 });
    for (; j < toJ; j++) out.push({ kind: 'add', text: b[j], newLine: j + 1 });
  };
  for (const [pi, pj] of pairs) {
    flush(pi, pj);
    out.push({ kind: 'same', text: a[pi], oldLine: pi + 1, newLine: pj + 1 });
    i = pi + 1;
    j = pj + 1;
  }
  flush(a.length, b.length);
  return out;
}
