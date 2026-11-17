import { describe, expect, it } from 'vitest';

import { arrowDirection, neighbour, tileTint, treemap, treemapOrder } from '../treemap';

const items = [
  { key: 'TLT', value: 37520 },
  { key: 'GLD', value: 17102 },
  { key: 'VTI', value: 14458 },
  { key: 'XLK', value: 8787 },
  { key: 'SMH', value: 7786 },
  { key: 'IEF', value: 7229 },
  { key: 'XLI', value: 5509 },
  { key: 'DBC', value: 1200 },
];

const overlaps = (
  a: { x: number; y: number; w: number; h: number },
  b: { x: number; y: number; w: number; h: number }
) =>
  a.x < b.x + b.w - 1e-6 &&
  b.x < a.x + a.w - 1e-6 &&
  a.y < b.y + b.h - 1e-6 &&
  b.y < a.y + a.h - 1e-6;

describe('treemap', () => {
  it.each([
    [1000, 340],
    [358, 250],
    [300, 600],
  ])('gives each item an area proportional to its value at %ix%i', (w, h) => {
    const rects = treemap(items, w, h);
    const total = items.reduce((s, i) => s + i.value, 0);
    expect(rects).toHaveLength(items.length);
    for (const r of rects) {
      expect(r.w * r.h).toBeCloseTo((r.value / total) * w * h, 6);
    }
    const covered = rects.reduce((s, r) => s + r.w * r.h, 0);
    expect(covered).toBeCloseTo(w * h, 6);
  });

  it('keeps every rectangle inside the box without overlaps', () => {
    const rects = treemap(items, 1000, 340);
    for (const r of rects) {
      expect(r.x).toBeGreaterThanOrEqual(-1e-9);
      expect(r.y).toBeGreaterThanOrEqual(-1e-9);
      expect(r.x + r.w).toBeLessThanOrEqual(1000 + 1e-6);
      expect(r.y + r.h).toBeLessThanOrEqual(340 + 1e-6);
    }
    rects.forEach((a, i) => rects.slice(i + 1).forEach((b) => expect(overlaps(a, b)).toBe(false)));
  });

  it('returns largest first, ties by symbol, whatever the input order', () => {
    const shuffled = [
      { key: 'B', value: 10 },
      { key: 'C', value: 30 },
      { key: 'A', value: 10 },
      { key: 'D', value: 5 },
    ];
    const keys = treemap(shuffled, 400, 200).map((r) => r.key);
    expect(keys).toEqual(['C', 'A', 'B', 'D']);
    expect(treemap([...shuffled].reverse(), 400, 200).map((r) => r.key)).toEqual(keys);
    expect(treemap(shuffled, 400, 200)).toEqual(treemap([...shuffled].reverse(), 400, 200));
  });

  it('keeps rectangles reasonably square', () => {
    const rects = treemap(items.slice(0, 6), 1000, 340);
    for (const r of rects) expect(Math.max(r.w / r.h, r.h / r.w)).toBeLessThan(4);
  });

  it('drops empty, negative and non-finite values and handles degenerate boxes', () => {
    const rects = treemap(
      [
        { key: 'A', value: 5 },
        { key: 'Z', value: 0 },
        { key: 'N', value: -3 },
        { key: 'X', value: Number.NaN },
      ],
      100,
      50
    );
    expect(rects).toEqual([{ key: 'A', value: 5, x: 0, y: 0, w: 100, h: 50 }]);
    expect(treemap([], 100, 50)).toEqual([]);
    expect(treemap(items, 0, 50)).toEqual([]);
    expect(treemapOrder([{ key: 'A', value: 0 }])).toEqual([]);
  });
});

describe('neighbour', () => {
  // A | B
  // A | C D
  const rects = [
    { x: 0, y: 0, w: 50, h: 100 },
    { x: 50, y: 0, w: 50, h: 50 },
    { x: 50, y: 50, w: 25, h: 50 },
    { x: 75, y: 50, w: 25, h: 50 },
  ];

  it('moves to the nearest tile on that side', () => {
    expect(neighbour(rects, 0, 'right')).toBe(1);
    expect(neighbour(rects, 1, 'down')).toBe(2);
    expect(neighbour(rects, 2, 'right')).toBe(3);
    expect(neighbour(rects, 3, 'up')).toBe(1);
    expect(neighbour(rects, 2, 'left')).toBe(0);
  });

  it('stays put at an edge or for an unknown tile', () => {
    expect(neighbour(rects, 0, 'left')).toBeNull();
    expect(neighbour(rects, 1, 'up')).toBeNull();
    expect(neighbour(rects, 9, 'up')).toBeNull();
  });

  it('reads arrow keys only', () => {
    expect(arrowDirection('ArrowLeft')).toBe('left');
    expect(arrowDirection('ArrowDown')).toBe('down');
    expect(arrowDirection('Enter')).toBeNull();
  });
});

describe('tileTint', () => {
  it('scales with the move and caps at one percent', () => {
    expect(tileTint(0.5)).toEqual({ tone: 'gain', strength: 0.5 });
    expect(tileTint(-0.25)).toEqual({ tone: 'loss', strength: 0.25 });
    expect(tileTint(3.2)).toEqual({ tone: 'gain', strength: 1 });
    expect(tileTint(-7)).toEqual({ tone: 'loss', strength: 1 });
  });

  it('stays plain without a price or a move', () => {
    expect(tileTint(null)).toEqual({ tone: 'flat', strength: 0 });
    expect(tileTint(0)).toEqual({ tone: 'flat', strength: 0 });
    expect(tileTint(0.001)).toEqual({ tone: 'flat', strength: 0 });
    expect(tileTint(Number.NaN)).toEqual({ tone: 'flat', strength: 0 });
  });
});
