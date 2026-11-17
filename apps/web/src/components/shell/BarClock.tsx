import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useEffect, useState } from 'react';

import { useOnline } from '../../hooks/useOnline';
import { barClock, etClock } from '../../lib/marketClock';

const CLOCK_TICK_MS = 15_000;
const STATUS_REFRESH_MS = 5 * 60_000;

/** The clock as drawn; `stopped` holds it at the last update and says so (offline2 B). */
export function BarClockView({
  time,
  state,
  open,
  detail,
  stopped,
  className = '',
}: {
  time: string;
  state: string;
  open: boolean;
  detail: string;
  stopped: boolean;
  className?: string;
}) {
  return (
    <span
      title={detail}
      className={`inline-flex h-[30px] flex-none items-center gap-2 whitespace-nowrap rounded-full px-2.5 font-mono text-[12px] font-medium text-fg-2 ${className}`}
    >
      <i
        aria-hidden="true"
        className={`h-1.5 w-1.5 flex-none rounded-full ${
          open && !stopped
            ? 'bg-accent shadow-[0_0_0_3px_var(--accent-soft)]'
            : 'shadow-[inset_0_0_0_1.5px_rgb(var(--fg-3))]'
        }`}
      />
      {time}
      <span className="font-sans font-normal text-fg-3">{stopped ? 'last update' : state}</span>
    </span>
  );
}

/** The market clock in the bar (frame2 A): New York time and whether the market is open. */
export function BarClock({ className = '' }: { className?: string }) {
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

  const stopped = !online && offlineSince !== null;
  const clock = barClock({ status, source, nextOpen, now });
  return (
    <BarClockView
      time={stopped ? `${etClock(offlineSince)} ET` : clock.time}
      state={clock.state}
      open={clock.open}
      detail={stopped ? 'Offline. The figures on screen are from this time.' : clock.detail}
      stopped={stopped}
      className={className}
    />
  );
}
