import { describe, expect, it } from 'vitest';

import { ledgerBySymbol } from '../checks';

describe('ledgerBySymbol', () => {
  it('splits each symbol by sleeve, marks frozen holdings and skips missing counts', () => {
    const rows = ledgerBySymbol(
      [
        { sleeveId: 'a', name: 'All-Weather', frozen: false },
        { sleeveId: 'b', name: 'Momentum', frozen: true },
        { sleeveId: null, name: 'Lost', frozen: false },
        { sleeveId: 'c', name: 'Unread', frozen: false },
      ],
      { a: { GLD: 26, TLT: 0 }, b: { GLD: 10, SMH: 31 } }
    );
    expect(rows).toEqual([
      {
        symbol: 'GLD',
        bySleeve: [
          { name: 'All-Weather', qty: 26 },
          { name: 'Momentum', qty: 10 },
        ],
        total: 36,
        frozen: true,
      },
      { symbol: 'SMH', bySleeve: [{ name: 'Momentum', qty: 31 }], total: 31, frozen: true },
    ]);
  });
});
