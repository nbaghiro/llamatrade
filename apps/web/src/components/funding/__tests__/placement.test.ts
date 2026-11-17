import { describe, expect, it, vi } from 'vitest';

vi.mock('@llamatrade/core/net', () => ({ ledgerClient: {}, getTenantContext: () => undefined }));

import { beforeAfter, placed, placementProblem } from '../placement';

describe('placement', () => {
  it('adds only positive, finite amounts', () => {
    expect(placed({ a: 10, b: -5, c: Number.NaN, d: 2.5 })).toBe(12.5);
  });

  it('needs an amount and caps the total at what is available', () => {
    expect(placementProblem(100, {})).toBe('Enter an amount for at least one sleeve.');
    expect(placementProblem(100, { a: 60, b: 40 })).toBeNull();
    expect(placementProblem(100, { a: 60, b: 50 })).toBe("That's $10.00 more than is available.");
  });

  it('draws new money as hatched parts in the after bar', () => {
    const { now, after } = beforeAfter(
      [
        { id: 'rr', value: 31_904.2 },
        { id: 'ms', value: 22_118.07 },
      ],
      0,
      10_000,
      { rr: 10_000 }
    );
    expect(now.map((p) => p.id)).toEqual(['rr', 'ms', 'unallocated']);
    expect(after).toEqual([
      { id: 'rr', value: 31_904.2 },
      { id: 'rr+', value: 10_000, added: true },
      { id: 'ms', value: 22_118.07 },
      { id: 'unallocated', value: 0, added: false },
    ]);
  });

  it('keeps unplaced money in unallocated cash', () => {
    const { after } = beforeAfter([], 500, 1000, {});
    expect(after).toEqual([{ id: 'unallocated', value: 1500, added: true }]);
  });
});
