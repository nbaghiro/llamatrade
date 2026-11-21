import type { WrittenHolding } from '../../../lib/outline';

export interface GapRow {
  symbol: string;
  /** Percent the rules would hold, null when a ranking decides it at the rebalance. */
  would: number | null;
  /** Percent of the sleeve held now. */
  holds: number;
  /** Dollars between the two, null when `would` isn't known. */
  gap: number | null;
}

/**
 * What the rules would hold against what the session holds, by symbol, with cash as the last
 * row. `values` are market values in dollars and `sleeve` the sleeve's equity.
 */
export function holdGap(
  would: readonly WrittenHolding[],
  values: ReadonlyMap<string, number>,
  sleeve: number
): { rows: GapRow[]; largest: GapRow | null } {
  if (sleeve <= 0) return { rows: [], largest: null };
  const symbols = [...new Set([...would.map((w) => w.symbol), ...values.keys()])];
  const rows: GapRow[] = symbols.map((symbol) => {
    const w = would.find((x) => x.symbol === symbol);
    const pct = w === undefined ? 0 : w.pct;
    const value = values.get(symbol) ?? 0;
    return {
      symbol,
      would: pct,
      holds: (value / sleeve) * 100,
      gap: pct === null ? null : Math.abs((pct / 100) * sleeve - value),
    };
  });
  const invested = [...values.values()].reduce((s, v) => s + v, 0);
  const allKnown = rows.every((r) => r.would !== null);
  const wouldCash = allKnown
    ? Math.max(0, 100 - rows.reduce((s, r) => s + (r.would ?? 0), 0))
    : null;
  const cash = sleeve - invested;
  rows.sort((a, b) => (b.would ?? -1) - (a.would ?? -1) || b.holds - a.holds);
  rows.push({
    symbol: 'Cash',
    would: wouldCash,
    holds: (cash / sleeve) * 100,
    gap: wouldCash === null ? null : Math.abs((wouldCash / 100) * sleeve - cash),
  });
  const largest = rows
    .filter((r) => r.symbol !== 'Cash' && r.gap !== null)
    .reduce<GapRow | null>(
      (best, r) => (best === null || (r.gap ?? 0) > (best.gap ?? 0) ? r : best),
      null
    );
  return { rows, largest };
}
