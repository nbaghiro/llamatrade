import { marketDataClient } from '@llamatrade/core/net';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { snapshotToQuote } from '@llamatrade/core/stores/markets';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { useOnline } from '../../hooks/useOnline';
import { formatNumber } from '../../lib/format';
import { barClock, etClock } from '../../lib/marketClock';
import { MARKETS } from '../../lib/navigation';

const QUOTE_REFRESH_MS = 60_000;
const CLOCK_TICK_MS = 15_000;
const STATUS_REFRESH_MS = 5 * 60_000;

/** SPY's latest price, refreshed every minute; null until Alpaca returns one. */
function useSpyPrice(): number | null {
  const [price, setPrice] = useState<number | null>(null);
  useEffect(() => {
    let live = true;
    const load = () => {
      marketDataClient
        .getSnapshots({ symbols: ['SPY'] })
        .then((res) => {
          const quote = snapshotToQuote(res.snapshots.SPY);
          if (live && quote) setPrice(quote.price);
        })
        .catch(() => undefined);
    };
    load();
    const timer = setInterval(load, QUOTE_REFRESH_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);
  return price;
}

/** Whether the market is open, with SPY beside it; leads to Markets. */
export function MarketStatus() {
  const status = useDashboardStore((s) => s.marketStatus);
  const source = useDashboardStore((s) => s.marketStatusSource);
  const nextOpen = useDashboardStore((s) => s.marketNextOpen);
  const fetchMarketStatus = useDashboardStore((s) => s.fetchMarketStatus);
  const { online, offlineSince } = useOnline();
  const [now, setNow] = useState(() => new Date());
  const spy = useSpyPrice();

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

  const clock = barClock({ status, source, nextOpen, now });
  const offline = !online && offlineSince;
  const label = offline
    ? `Last update ${etClock(offlineSince)} ET`
    : clock.open
      ? 'Market open'
      : `Market ${clock.state}`;

  return (
    <Link
      to={MARKETS.to}
      title={offline ? label : clock.detail}
      className="hidden items-center gap-2 whitespace-nowrap rounded-full px-1 text-[12px] text-fg-3 transition-colors hover:text-fg-2 sm:flex"
    >
      <i
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${
          clock.open && !offline ? 'bg-gain shadow-[0_0_0_3px_rgb(var(--gain)/0.18)]' : 'bg-fg-3'
        }`}
      />
      <span>{label}</span>
      {spy !== null && (
        <>
          <span aria-hidden="true">·</span>
          <b className="font-mono font-medium text-fg-2">SPY {formatNumber(spy)}</b>
        </>
      )}
    </Link>
  );
}
