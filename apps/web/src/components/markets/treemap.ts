export interface TreemapItem {
  key: string;
  value: number;
}

export interface TreemapRect {
  key: string;
  value: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Largest first, then by key, so equal values always land in the same order. */
export function treemapOrder<T extends TreemapItem>(items: readonly T[]): T[] {
  return items
    .filter((i) => Number.isFinite(i.value) && i.value > 0)
    .sort((a, b) => b.value - a.value || a.key.localeCompare(b.key));
}

/** The worst aspect ratio in a strip of areas laid along a side of this length. */
function worst(areas: readonly number[], side: number): number {
  const sum = areas.reduce((s, a) => s + a, 0);
  const max = Math.max(...areas);
  const min = Math.min(...areas);
  const s2 = side * side;
  return Math.max((s2 * max) / (sum * sum), (sum * sum) / (s2 * min));
}

/**
 * A squarified treemap (Bruls, Huizing and van Wijk): each rectangle's area is proportional to
 * its value, rectangles stay close to square, and they come back largest first.
 */
export function treemap(
  items: readonly TreemapItem[],
  width: number,
  height: number
): TreemapRect[] {
  const ordered = treemapOrder(items);
  if (ordered.length === 0 || !(width > 0) || !(height > 0)) return [];
  const total = ordered.reduce((s, i) => s + i.value, 0);
  const areas = ordered.map((i) => (i.value / total) * width * height);

  const out: TreemapRect[] = [];
  let x = 0;
  let y = 0;
  let w = width;
  let h = height;
  let i = 0;
  while (i < areas.length) {
    const side = Math.min(w, h);
    const row = [areas[i]];
    let j = i + 1;
    while (j < areas.length && worst([...row, areas[j]], side) <= worst(row, side)) {
      row.push(areas[j]);
      j++;
    }
    const sum = row.reduce((s, a) => s + a, 0);
    const last = j >= areas.length;
    if (w >= h) {
      const t = last ? w : sum / h;
      let at = y;
      row.forEach((a, k) => {
        const size = k === row.length - 1 ? y + h - at : a / t;
        out.push({ key: ordered[i + k].key, value: ordered[i + k].value, x, y: at, w: t, h: size });
        at += size;
      });
      x += t;
      w -= t;
    } else {
      const t = last ? h : sum / w;
      let at = x;
      row.forEach((a, k) => {
        const size = k === row.length - 1 ? x + w - at : a / t;
        out.push({ key: ordered[i + k].key, value: ordered[i + k].value, x: at, y, w: size, h: t });
        at += size;
      });
      y += t;
      h -= t;
    }
    i = j;
  }
  return out;
}

export type Direction = 'left' | 'right' | 'up' | 'down';

const ARROWS: Record<string, Direction> = {
  ArrowLeft: 'left',
  ArrowRight: 'right',
  ArrowUp: 'up',
  ArrowDown: 'down',
};

export function arrowDirection(key: string): Direction | null {
  return ARROWS[key] ?? null;
}

/** The tile an arrow key moves to: the nearest one on that side, favouring tiles in line. */
export function neighbour(
  rects: readonly Pick<TreemapRect, 'x' | 'y' | 'w' | 'h'>[],
  from: number,
  dir: Direction
): number | null {
  const a = rects[from];
  if (!a) return null;
  const eps = 1e-6;
  const horizontal = dir === 'left' || dir === 'right';
  let best: number | null = null;
  let bestScore = Infinity;
  rects.forEach((b, k) => {
    if (k === from) return;
    const gap =
      dir === 'right'
        ? b.x - (a.x + a.w)
        : dir === 'left'
          ? a.x - (b.x + b.w)
          : dir === 'down'
            ? b.y - (a.y + a.h)
            : a.y - (b.y + b.h);
    if (gap < -eps) return;
    const [a0, a1, b0, b1] = horizontal
      ? [a.y, a.y + a.h, b.y, b.y + b.h]
      : [a.x, a.x + a.w, b.x, b.x + b.w];
    const off = Math.max(0, b0 - a1, a0 - b1);
    const centre = Math.abs((a0 + a1) / 2 - (b0 + b1) / 2);
    const score = gap + off * 4 + centre * 0.01;
    if (score < bestScore) {
      bestScore = score;
      best = k;
    }
  });
  return best;
}

/** Day moves at or beyond this many percent get the strongest tint. */
export const TINT_CAP_PCT = 1;

export interface TileTint {
  tone: 'gain' | 'loss' | 'flat';
  /** 0 to 1 along the capped scale. */
  strength: number;
}

/** A tile's tint from the day's % change; unknown or unchanged prices stay plain. */
export function tileTint(pct: number | null): TileTint {
  if (pct === null || !Number.isFinite(pct) || Math.abs(pct) < 0.005) {
    return { tone: 'flat', strength: 0 };
  }
  return {
    tone: pct > 0 ? 'gain' : 'loss',
    strength: Math.min(Math.abs(pct) / TINT_CAP_PCT, 1),
  };
}
