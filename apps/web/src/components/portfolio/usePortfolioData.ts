import { useActivityStore } from '@llamatrade/core/stores/activity';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useEffect, useMemo } from 'react';

import { sleeveFills, type SleeveFill } from './history';

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

/** The session that trades a sleeve, for "Open session" links. */
export function useSessionForSleeve(sleeveId: string | null): string | null {
  const sessions = useTradingStore((s) => s.sessions);
  if (!sleeveId) return null;
  const matches = sessions.filter((s) => s.sleeveId === sleeveId);
  return (matches.find((s) => s.isActive) ?? matches[0])?.id ?? null;
}
