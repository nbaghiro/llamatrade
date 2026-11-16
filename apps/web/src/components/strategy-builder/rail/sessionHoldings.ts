import { num, toDate } from '@llamatrade/core/format';
import type { Position } from '@llamatrade/core/proto/trading_pb';

export interface SessionHolding {
  symbol: string;
  pct: number;
}

/** A session's positions as weights of their total market value, largest first, plus the latest update time. */
export function sessionHoldings(positions: readonly Position[]): {
  holdings: SessionHolding[];
  asOf: Date | null;
} {
  const valued = positions
    .map((p) => ({ symbol: p.symbol, value: Math.abs(num(p.marketValue)) }))
    .filter((p) => p.value > 0);
  const total = valued.reduce((s, p) => s + p.value, 0);
  const bySymbol = new Map<string, number>();
  for (const p of valued) bySymbol.set(p.symbol, (bySymbol.get(p.symbol) ?? 0) + p.value);
  const holdings =
    total > 0
      ? [...bySymbol.entries()]
          .map(([symbol, value]) => ({ symbol, pct: Math.round((value / total) * 1000) / 10 }))
          .sort((a, b) => b.pct - a.pct)
      : [];
  let asOf: Date | null = null;
  for (const p of positions) {
    const d = toDate(p.updatedAt);
    if (d && (!asOf || d > asOf)) asOf = d;
  }
  return { holdings, asOf };
}
