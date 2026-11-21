import { num } from '@llamatrade/core/format';
import { getTenantContext, ledgerClient } from '@llamatrade/core/net';
import type { LedgerLot } from '@llamatrade/core/stores/portfolio';
import { useEffect, useState } from 'react';

import type { SleeveFill } from './history';

/** How close in time a ledger entry and an order fill must be to be the same trade. */
const SAME_TRADE_MS = 5 * 60_000;

export interface HistoryEntry {
  sleeveId: string;
  side: string;
  qty: number;
  price: number | null;
  realizedPnl: number | null;
  at: Date | null;
}

export type FillNote = { kind: 'newLot' } | { kind: 'realized'; amount: number } | { kind: 'none' };

const near = (a: Date | null, b: Date) =>
  a !== null && Math.abs(a.getTime() - b.getTime()) <= SAME_TRADE_MS;

/**
 * What the ledger recorded for one fill: a buy that opened a lot of exactly its size at its
 * time is a new lot; a sale shows the realized gain the ledger booked for it.
 */
export function fillNote(
  fill: SleeveFill,
  lots: readonly LedgerLot[],
  history: readonly HistoryEntry[]
): FillNote {
  if (fill.side === 'buy') {
    const lot = lots.find(
      (l) =>
        l.symbol === fill.symbol && Math.abs(l.qty - fill.qty) < 1e-6 && near(l.openedAt, fill.at)
    );
    return lot ? { kind: 'newLot' } : { kind: 'none' };
  }
  const entry = history.find(
    (e) =>
      e.sleeveId === fill.sleeveId &&
      e.side === 'sell' &&
      Math.abs(e.qty - fill.qty) < 1e-6 &&
      // The ledger doesn't always send a time; the fill price then identifies the sale.
      (e.at !== null
        ? near(e.at, fill.at)
        : e.price !== null && Math.abs(e.price - fill.price) < 0.005)
  );
  return entry && entry.realizedPnl !== null
    ? { kind: 'realized', amount: entry.realizedPnl }
    : { kind: 'none' };
}

/** The ledger's trade history for each symbol sold today in this account; empty on failure. */
export function useSaleHistory(
  accountId: string,
  symbols: readonly string[]
): readonly HistoryEntry[] {
  const key = [...new Set(symbols)].sort().join(',');
  const [entries, setEntries] = useState<readonly HistoryEntry[]>([]);
  useEffect(() => {
    if (!accountId || !key) return;
    let live = true;
    const context = getTenantContext();
    Promise.all(
      key.split(',').map((symbol) =>
        ledgerClient
          .getHoldingHistory({ context, accountId, symbol })
          .then((r) =>
            r.entries.map((e) => ({
              sleeveId: e.sleeveId,
              side: e.side,
              qty: num(e.qty),
              price: e.price ? num(e.price) : null,
              realizedPnl: e.realizedPnl ? num(e.realizedPnl) : null,
              at: e.occurredAt?.seconds ? new Date(Number(e.occurredAt.seconds) * 1000) : null,
            }))
          )
          .catch(() => [] as HistoryEntry[])
      )
    ).then((lists) => {
      if (live) setEntries(lists.flat());
    });
    return () => {
      live = false;
    };
  }, [accountId, key]);
  return entries;
}
