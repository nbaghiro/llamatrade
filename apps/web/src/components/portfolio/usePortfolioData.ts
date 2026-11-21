import { useActivityStore } from '@llamatrade/core/stores/activity';
import type { SleeveSummary } from '@llamatrade/core/stores/portfolio';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useEffect, useMemo, useState } from 'react';

import { fillsByLedgerId, sleeveFills, type SleeveFill } from './history';

let activityRequested = false;

/** Loads every activity page once per app load; later visits read what is already there. */
export function useAllActivity() {
  const rows = useActivityStore((s) => s.rows);
  const loading = useActivityStore((s) => s.loading);
  const error = useActivityStore((s) => s.error);
  const hasMore = useActivityStore((s) => s.hasMore);

  useEffect(() => {
    if (activityRequested) return;
    activityRequested = true;
    const { fetch, loadAll } = useActivityStore.getState();
    fetch()
      .then(() => loadAll())
      .catch(() => {
        activityRequested = false;
      });
  }, []);

  return { rows, loading: loading || (rows.length > 0 && hasMore && !error), error };
}

/** Every fill booked to a sleeve, from the trading blotter the shell loads. */
export function useSleeveFills(): { fills: SleeveFill[]; loaded: boolean } {
  const orders = useTradingStore((s) => s.orders);
  const sessions = useTradingStore((s) => s.sessions);
  const loaded = useTradingStore((s) => s.loaded);
  const loading = useTradingStore((s) => s.loading);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);

  useEffect(() => {
    if (!loaded && !loading) loadBlotter().catch(() => undefined);
  }, [loaded, loading, loadBlotter]);

  const fills = useMemo(() => sleeveFills(orders, sessions), [orders, sessions]);
  return { fills, loaded };
}

/** Fills keyed by the ledger event id each one produced; empty until the ids are worked out. */
export function useFillsByLedgerId(fills: readonly SleeveFill[]): ReadonlyMap<string, SleeveFill> {
  const [byId, setById] = useState<ReadonlyMap<string, SleeveFill>>(new Map());
  useEffect(() => {
    let live = true;
    fillsByLedgerId(fills)
      .then((m) => {
        if (live) setById(m);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [fills]);
  return byId;
}

/**
 * Sleeves with every ledger sleeve id known: the portfolio reads the paper ledger only, so a live
 * sleeve's id comes from its execution in the trading blotter.
 */
export function useResolvedSleeves(sleeves: readonly SleeveSummary[]): SleeveSummary[] {
  const executions = useTradingStore((s) => s.executions);
  return useMemo(
    () =>
      sleeves.map((s) => ({
        ...s,
        sleeveId: s.sleeveId ?? executions.find((e) => e.id === s.executionId)?.sleeveId ?? null,
      })),
    [sleeves, executions]
  );
}

/** The session that trades a sleeve, for "Open session" links. */
export function useSessionForSleeve(sleeveId: string | null): string | null {
  const sessions = useTradingStore((s) => s.sessions);
  if (!sleeveId) return null;
  const matches = sessions.filter((s) => s.sleeveId === sleeveId);
  return (matches.find((s) => s.isActive) ?? matches[0])?.id ?? null;
}
