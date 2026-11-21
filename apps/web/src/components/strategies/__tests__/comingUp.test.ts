import { describe, expect, it } from 'vitest';

import { comingUp } from '../detail/comingUp';
import { branchSpans } from '../rules/evaluate';

const utc = (m: number, d: number) => new Date(Date.UTC(2026, m, d));

describe('comingUp', () => {
  it('lists the next monthly rebalance with Thanksgiving and its early close', () => {
    const items = comingUp('monthly', utc(10, 18));
    expect(items.map((i) => [i.at.toISOString().slice(0, 10), i.kind])).toEqual([
      ['2026-11-26', 'closed'],
      ['2026-11-27', 'early'],
      ['2026-12-01', 'rebalance'],
    ]);
  });

  it('leaves out a rebalance past the window and has no date for daily', () => {
    expect(comingUp('annually', utc(1, 2), 10)).toEqual([]);
    expect(comingUp('daily', utc(10, 18)).every((i) => i.kind !== 'rebalance')).toBe(true);
  });
});

describe('branchSpans', () => {
  const dates = Array.from({ length: 6 }, (_, i) => utc(0, i + 1));
  const h = {
    dates,
    left: [1, 2, 3, 4, 5, 6],
    held: [true, true, false, false, true, true],
  };

  it('joins rebalances on one side into spans up to the next change', () => {
    const spans = branchSpans(h, [0, 1, 2, 3, 4, 5], dates[0], utc(0, 10));
    expect(spans.map((s) => [s.holds, s.from.getUTCDate(), s.to.getUTCDate()])).toEqual([
      [true, 1, 3],
      [false, 3, 5],
      [true, 5, 10],
    ]);
  });

  it('keeps only rebalances inside the dates', () => {
    const spans = branchSpans(h, [0, 2, 4], dates[2], dates[3]);
    expect(spans).toHaveLength(1);
    expect(spans[0].holds).toBe(false);
  });
});
