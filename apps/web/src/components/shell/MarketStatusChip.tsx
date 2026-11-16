import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useEffect, useState } from 'react';

import { useOnline } from '../../hooks/useOnline';
import { describeOpen, marketChip } from '../../lib/marketClock';

const CLOCK_TICK_MS = 30_000;
const STATUS_REFRESH_MS = 5 * 60_000;

/** "Market open · 10:42 ET", or when it is closed, when it opens next. */
export function MarketStatusChip({ className = '' }: { className?: string }) {
  const status = useDashboardStore((s) => s.marketStatus);
  const source = useDashboardStore((s) => s.marketStatusSource);
  const nextOpen = useDashboardStore((s) => s.marketNextOpen);
  const fetchMarketStatus = useDashboardStore((s) => s.fetchMarketStatus);
  const { online, offlineSince } = useOnline();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    fetchMarketStatus().catch(() => undefined);
    const refresh = setInterval(() => {
      fetchMarketStatus().catch(() => undefined);
    }, STATUS_REFRESH_MS);
    const tick = setInterval(() => setNow(new Date()), CLOCK_TICK_MS);
    return () => {
      clearInterval(refresh);
      clearInterval(tick);
    };
  }, [fetchMarketStatus]);

  if (!online) {
    return (
      <span
        className={`inline-flex items-center gap-[7px] whitespace-nowrap text-xs text-risk ${className}`}
      >
        <i aria-hidden="true" className="h-[7px] w-[7px] bg-risk" />
        {offlineSince ? `Offline · last update ${describeOpen(offlineSince, now)}` : 'Offline'}
      </span>
    );
  }

  const chip = marketChip({ status, source, nextOpen, now });
  return (
    <span
      className={`inline-flex items-center gap-[7px] whitespace-nowrap text-xs text-fg-2 ${className}`}
      title={source === 'rpc' ? 'Market clock from Alpaca' : 'Estimated from the New York clock'}
    >
      <i
        aria-hidden="true"
        className={`h-[7px] w-[7px] rounded-full ${
          chip.open
            ? 'bg-accent shadow-[0_0_0_3px_var(--accent-soft)]'
            : 'shadow-[inset_0_0_0_1.5px_rgb(var(--fg-3))]'
        }`}
      />
      {chip.text}
    </span>
  );
}
