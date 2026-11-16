import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useEffect, useState } from 'react';

import { marketChip } from '../../lib/marketClock';

/** "Market open · 10:42 ET" from the market service, or the New York clock when it's unavailable. */
export function useMarketLine(): string {
  const status = useDashboardStore((s) => s.marketStatus);
  const source = useDashboardStore((s) => s.marketStatusSource);
  const nextOpen = useDashboardStore((s) => s.marketNextOpen);
  const fetchMarketStatus = useDashboardStore((s) => s.fetchMarketStatus);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    fetchMarketStatus().catch(() => undefined);
    const tick = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(tick);
  }, [fetchMarketStatus]);
  return marketChip({ status, source, nextOpen, now }).text;
}
