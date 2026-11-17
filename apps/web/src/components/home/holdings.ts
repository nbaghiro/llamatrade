import type { Position } from '@llamatrade/core/proto/trading_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';

import { outlineOf } from './templates';

export interface Holding {
  symbol: string;
  shares: number;
  price: number | null;
  value: number;
  target: number | null;
}

/** Explicit per-symbol target weights from a strategy definition, as fractions. */
export function targetWeights(definition: string): Map<string, number> {
  const out = new Map<string, number>();
  for (const line of outlineOf(definition).lines) {
    if (!line.weight || !/^[A-Z][A-Z0-9.]*$/.test(line.text)) continue;
    const w = Number.parseFloat(line.weight);
    if (Number.isFinite(w)) out.set(line.text, w / 100);
  }
  return out;
}

export function holdingsOf(
  positions: readonly Position[],
  targets: Map<string, number>
): Holding[] {
  return positions
    .map((p) => {
      const shares = toNumber(p.quantity);
      const price = p.currentPrice ? toNumber(p.currentPrice) : null;
      const value = p.marketValue ? toNumber(p.marketValue) : shares * (price ?? 0);
      return { symbol: p.symbol, shares, price, value, target: targets.get(p.symbol) ?? null };
    })
    .filter((h) => h.shares !== 0)
    .sort((a, b) => b.value - a.value);
}
