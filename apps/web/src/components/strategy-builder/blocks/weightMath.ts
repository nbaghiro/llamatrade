import type { Block, BlockId, StrategyTree, WeightBlock } from '@llamatrade/core/strategy/types';

/** Weights are percentages kept to one decimal place. */
const round1 = (v: number) => Math.round(v * 10) / 10;

export function total(weights: readonly number[]): number {
  return round1(weights.reduce((s, w) => s + w, 0));
}

/**
 * Rounds to one decimal place while keeping the rounded sum equal to the rounded
 * original sum (largest remainder).
 */
export function roundKeepingSum(weights: readonly number[]): number[] {
  const target = Math.round(weights.reduce((s, w) => s + w, 0) * 10);
  const scaled = weights.map((w) => w * 10);
  const floors = scaled.map(Math.floor);
  let left = target - floors.reduce((s, w) => s + w, 0);
  const order = scaled
    .map((w, i) => ({ i, r: w - Math.floor(w) }))
    .sort((a, b) => b.r - a.r || a.i - b.i);
  const out = [...floors];
  for (const { i } of order) {
    if (left <= 0) break;
    out[i] += 1;
    left -= 1;
  }
  return out.map((w) => w / 10);
}

/** Equal shares of 100% to one decimal place; the first rows take any remainder. */
export function splitEvenly(count: number): number[] {
  if (count <= 0) return [];
  return roundKeepingSum(new Array<number>(count).fill(100 / count));
}

/**
 * Moves weight across the edge between `edge` and `edge + 1`. A positive `delta`
 * grows the left neighbour and shrinks the right one; nothing else changes.
 */
export function dragEdge(weights: readonly number[], edge: number, delta: number): number[] {
  if (edge < 0 || edge + 1 >= weights.length) return [...weights];
  const left = weights[edge];
  const right = weights[edge + 1];
  const d = Math.max(-left, Math.min(right, delta));
  const out = [...weights];
  out[edge] = round1(left + d);
  out[edge + 1] = round1(right - d);
  return out;
}

/**
 * Sets one row and moves the unlocked others in proportion to their current weights,
 * so the side stays at 100% where it can. Locked rows never move. When no unlocked row
 * can absorb the change, only the edited row changes.
 */
export function setWeight(
  weights: readonly number[],
  locked: readonly boolean[],
  index: number,
  value: number
): number[] {
  if (index < 0 || index >= weights.length) return [...weights];
  const others = weights.map((_, i) => i).filter((i) => i !== index && !locked[i]);
  const lockedSum = weights.reduce((s, w, i) => (i !== index && locked[i] ? s + w : s), 0);
  const out = [...weights];
  if (others.length === 0) {
    out[index] = round1(Math.max(0, Math.min(100, value)));
    return out;
  }
  const v = Math.max(0, Math.min(100 - lockedSum, value));
  const remaining = 100 - lockedSum - v;
  const current = others.reduce((s, i) => s + weights[i], 0);
  const shares = others.map((i) =>
    current > 0 ? (weights[i] / current) * remaining : remaining / others.length
  );
  const rounded = roundKeepingSum([v, ...shares]);
  out[index] = rounded[0];
  others.forEach((i, k) => {
    out[i] = rounded[k + 1];
  });
  return out;
}

/** The edge position (0 to 100) after each row, for drawing drag handles on a bar. */
export function edgePositions(weights: readonly number[]): number[] {
  const out: number[] = [];
  let acc = 0;
  for (let i = 0; i < weights.length - 1; i++) {
    acc += weights[i];
    out.push(acc);
  }
  return out;
}

export interface WeightRow {
  id: BlockId;
  label: string;
  name: string | null;
  isAsset: boolean;
}

export function rowOf(block: Block | undefined, id: BlockId): WeightRow {
  if (block?.type === 'asset') {
    return {
      id,
      label: block.symbol,
      name: block.displayName && block.displayName !== block.symbol ? block.displayName : null,
      isAsset: true,
    };
  }
  if (block?.type === 'group') return { id, label: block.name, name: 'Group', isAsset: false };
  return { id, label: block?.type ?? 'block', name: null, isAsset: false };
}

/** Each child's percent in the block when the method fixes it, else null. */
export function knownWeights(block: WeightBlock): number[] | null {
  if (block.method === 'specified') return block.childIds.map((c) => block.allocations[c] ?? 0);
  if (block.method === 'equal') return splitEvenly(block.childIds.length);
  return null;
}

/** The block's share of the whole strategy when its side applies, or null when ranked above it. */
export function shareOfWhole(tree: StrategyTree, id: BlockId): number | null {
  let share = 1;
  let child = tree.blocks[id];
  while (child?.parentId) {
    const parent = tree.blocks[child.parentId];
    if (!parent) break;
    if (parent.type === 'weight') {
      if (parent.method === 'specified') share *= (parent.allocations[child.id] ?? 0) / 100;
      else if (parent.method === 'equal') share /= Math.max(1, parent.childIds.length);
      else return null;
    }
    child = parent;
  }
  return share;
}
