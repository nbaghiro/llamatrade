import { describe, expect, it } from 'vitest';

import { holdGap } from '../detail/holdGap';

describe('holdGap', () => {
  it('compares fixed weights with the session in dollars, with cash last', () => {
    const { rows, largest } = holdGap(
      [
        { symbol: 'TLT', pct: 60 },
        { symbol: 'GLD', pct: 40 },
      ],
      new Map([
        ['TLT', 5900],
        ['GLD', 3950],
      ]),
      10_000
    );
    expect(rows.map((r) => r.symbol)).toEqual(['TLT', 'GLD', 'Cash']);
    expect(rows[0].gap).toBeCloseTo(100);
    expect(rows[0].holds).toBeCloseTo(59);
    expect(rows[2].would).toBe(0);
    expect(rows[2].holds).toBeCloseTo(1.5);
    expect(largest?.symbol).toBe('TLT');
  });

  it('counts symbols the rules would drop and leaves ranked weights unknown', () => {
    const { rows, largest } = holdGap(
      [{ symbol: 'QQQ', pct: null }],
      new Map([['TLT', 1000]]),
      2000
    );
    expect(rows.find((r) => r.symbol === 'TLT')).toMatchObject({ would: 0, gap: 1000 });
    expect(rows.find((r) => r.symbol === 'QQQ')?.gap).toBeNull();
    expect(rows.find((r) => r.symbol === 'Cash')?.would).toBeNull();
    expect(largest?.symbol).toBe('TLT');
  });

  it('returns nothing without a sleeve', () => {
    expect(holdGap([], new Map(), 0).rows).toEqual([]);
  });
});
