/** One symbol's ledger count, split by the sleeves that hold it. */
export interface LedgerCount {
  symbol: string;
  bySleeve: { name: string; qty: number }[];
  total: number;
  /** Held by a frozen sleeve. */
  frozen: boolean;
}

/** Every symbol the sleeves hold in the ledger, alphabetical, with frozen holdings marked. */
export function ledgerBySymbol(
  sleeves: readonly { sleeveId: string | null; name: string; frozen: boolean }[],
  counts: Readonly<Record<string, Readonly<Record<string, number>>>>
): LedgerCount[] {
  const out = new Map<string, LedgerCount>();
  for (const s of sleeves) {
    const own = s.sleeveId ? counts[s.sleeveId] : undefined;
    if (!own) continue;
    for (const [symbol, qty] of Object.entries(own)) {
      if (qty === 0) continue;
      const row = out.get(symbol) ?? { symbol, bySleeve: [], total: 0, frozen: false };
      row.bySleeve.push({ name: s.name, qty });
      row.total += qty;
      row.frozen ||= s.frozen;
      out.set(symbol, row);
    }
  }
  return [...out.values()].sort((a, b) => a.symbol.localeCompare(b.symbol));
}
