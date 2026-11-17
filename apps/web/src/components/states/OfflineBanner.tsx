import { Info, Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import { retryConnection, useOnline } from '../../hooks/useOnline';
import { describeOpen } from '../../lib/marketClock';

/** How often the strip tries the network on its own. */
export const AUTO_RETRY_MS = 10_000;

interface OfflineBannerViewProps {
  offlineSince: Date;
  now: Date;
  retrying: boolean;
  stillOffline: boolean;
  onRetry: () => void;
}

/**
 * A neutral strip while the browser is offline (offline2 B). It stays grey because nothing is
 * wrong with the account: the sessions run on LlamaTrade's servers and keep trading.
 */
export function OfflineBannerView({
  offlineSince,
  now,
  retrying,
  stillOffline,
  onRetry,
}: OfflineBannerViewProps) {
  const from = describeOpen(offlineSince, now);
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2.5 border-b border-line bg-sunk px-4 py-2 text-[12.5px] text-fg-2 md:px-5"
    >
      <Info aria-hidden="true" className="h-4 w-4 flex-none text-fg-3" />
      <span className="min-w-0 flex-1">
        <b className="font-semibold text-fg">You&apos;re offline.</b>{' '}
        <span className="hidden md:inline">
          Your sessions run on LlamaTrade&apos;s servers and keep trading. The figures here are from{' '}
          {from}.
        </span>
        <span className="md:hidden">
          Your sessions keep trading on LlamaTrade&apos;s servers. Figures from {from}.
        </span>
        {stillOffline && <span className="text-fg-3"> Still no connection.</span>}
      </span>
      <span className="hidden flex-none items-center gap-2 text-[11.5px] text-fg-3 lg:inline-flex">
        <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />
        {retrying ? 'Checking…' : 'Trying again every 10 seconds'}
      </span>
      <button
        type="button"
        onClick={onRetry}
        disabled={retrying}
        className="btn btn-secondary btn-sm flex-none"
      >
        {retrying ? 'Checking…' : 'Try now'}
      </button>
    </div>
  );
}

/** Shown under the bar while offline; retries every ten seconds and clears on reconnect. */
export function OfflineBanner() {
  const { online, offlineSince } = useOnline();
  const [retrying, setRetrying] = useState(false);
  const [stillOffline, setStillOffline] = useState(false);

  useEffect(() => {
    if (online) setStillOffline(false);
  }, [online]);

  useEffect(() => {
    if (online) return;
    const timer = setInterval(() => {
      retryConnection().catch(() => undefined);
    }, AUTO_RETRY_MS);
    return () => clearInterval(timer);
  }, [online]);

  if (online || !offlineSince) return null;

  const retry = () => {
    setRetrying(true);
    retryConnection()
      .then((ok) => setStillOffline(!ok))
      .finally(() => setRetrying(false));
  };

  return (
    <OfflineBannerView
      offlineSince={offlineSince}
      now={new Date()}
      retrying={retrying}
      stillOffline={stillOffline}
      onRetry={retry}
    />
  );
}
