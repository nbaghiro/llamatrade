import { describe, expect, it } from 'vitest';

import { cellAlpha, cellText, cellTextShort, monthlyRows } from '../chart/monthly';
import {
  areaPath,
  linePath,
  nearestIndex,
  xAt,
  xTickIndexes,
  yAt,
  yDomain,
  niceStep,
  yTicks,
  type Plot,
} from '../chart/scale';

const plot = (count: number, lo = 0, hi = 100): Plot => ({
  width: 120,
  height: 70,
  pad: { t: 10, r: 10, b: 10, l: 10 },
  domain: { lo, hi },
  count,
});

describe('yDomain', () => {
  it('adds 6% headroom on both sides by default', () => {
    expect(yDomain([[0, 100]])).toEqual({ lo: -6, hi: 106 });
  });

  it('pins base and ceil when given', () => {
    expect(yDomain([[-0.2, -0.05]], { base: 0, ceil: 0 })).toEqual({ lo: -0.2, hi: 0 });
    expect(yDomain([[110, 120]], { base: 100 })).toEqual({ lo: 100, hi: 120 + 20 * 0.06 });
  });

  it('handles flat, empty and non-finite data', () => {
    const flat = yDomain([[5, 5]]);
    expect(flat.hi).toBeGreaterThan(flat.lo);
    expect(yDomain([])).toEqual({ lo: 0, hi: 1 });
    expect(yDomain([[Number.NaN, 2, 4]])).toEqual({ lo: 2 - 0.12, hi: 4 + 0.12 });
  });
});

describe('geometry', () => {
  it('maps the ends of both axes to the plot edges', () => {
    const p = plot(11);
    expect(xAt(p, 0)).toBe(10);
    expect(xAt(p, 10)).toBe(110);
    expect(yAt(p, 0)).toBe(60);
    expect(yAt(p, 100)).toBe(10);
  });

  it('centres a single point', () => {
    expect(xAt(plot(1), 0)).toBe(60);
  });

  it('builds line and area paths', () => {
    const p = plot(3);
    expect(linePath(p, [0, 50, 100])).toBe('M10.0,60.0 L60.0,35.0 L110.0,10.0');
    expect(areaPath(p, [0, 50, 100], 0)).toBe(
      'M10.0,60.0 L10.0,60.0 L60.0,35.0 L110.0,10.0 L110.0,60.0 Z'
    );
    expect(areaPath(p, [], 0)).toBe('');
  });

  it('snaps the pointer to the nearest index and clamps', () => {
    const p = plot(11);
    expect(nearestIndex(p, 64)).toBe(5);
    expect(nearestIndex(p, -50)).toBe(0);
    expect(nearestIndex(p, 500)).toBe(10);
    expect(nearestIndex(plot(1), 80)).toBe(0);
  });

  it('spaces ticks evenly and keeps the last label', () => {
    expect(yTicks({ lo: 0, hi: 100 }, 4)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(xTickIndexes(11, 5)).toEqual([0, 2, 4, 6, 8, 10]);
    expect(xTickIndexes(3, 5)).toEqual([0, 1, 2]);
    expect(xTickIndexes(1, 5)).toEqual([0]);
    expect(xTickIndexes(0, 5)).toEqual([]);
  });
});

describe('monthly grid', () => {
  it('lays out rows by year with gaps and a compounded total', () => {
    const rows = monthlyRows([
      { y: 2025, m: 0, r: 0.1 },
      { y: 2024, m: 11, r: -0.05 },
      { y: 2025, m: 1, r: 0.1 },
    ]);
    expect(rows.map((r) => r.year)).toEqual([2024, 2025]);
    expect(rows[0].cells[11].r).toBe(-0.05);
    expect(rows[0].cells[0].r).toBeNull();
    expect(rows[1].total).toBeCloseTo(0.21);
    expect(rows[1].cells).toHaveLength(12);
  });

  it('shades by size up to a cap', () => {
    expect(cellAlpha(0)).toBeCloseTo(0.1);
    expect(cellAlpha(0.04)).toBeCloseTo(0.29);
    expect(cellAlpha(-0.2)).toBeCloseTo(0.48);
  });

  it('formats cell text', () => {
    expect(cellText(0.0004)).toBe('0.0');
    expect(cellText(0.0234)).toBe('2.3');
    expect(cellText(-0.0234)).toBe('−2.3');
    expect(cellTextShort(0.0234)).toBe('2');
    expect(cellTextShort(-0.0263)).toBe('−3');
    expect(cellTextShort(-0.004)).toBe('0');
    expect(cellTextShort(0.125)).toBe('13');
  });
});

describe('yTicks', () => {
  it('picks 1, 2 or 5 times a power of ten', () => {
    expect(niceStep(100, 4)).toBe(20);
    expect(niceStep(0.024, 4)).toBe(0.005);
    expect(niceStep(7000, 4)).toBe(2000);
    expect(niceStep(0, 4)).toBe(1);
  });

  it('places money gridlines on round values inside the domain', () => {
    expect(yTicks({ lo: 26_640, hi: 27_380 }, 4)).toEqual([26_800, 27_000, 27_200]);
  });

  it('places percentage gridlines on round values across zero', () => {
    expect(yTicks({ lo: -0.012, hi: 0.019 }, 4)).toEqual([-0.01, 0, 0.01]);
    expect(yTicks({ lo: -0.14, hi: 0.47 }, 4)).toEqual([0, 0.2, 0.4]);
  });

  it('keeps the domain ends when no round value falls inside', () => {
    expect(yTicks({ lo: 1.01, hi: 1.02 }, 1)).toEqual([1.01, 1.02]);
  });
});
