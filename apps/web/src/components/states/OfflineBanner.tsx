import { WifiOff } from 'lucide-react';
import { useEffect, useState } from 'react';

import { retryConnection, staleSince, useOnline } from '../../hooks/useOnline';

interface OfflineBannerViewProps {
  offlineSince: Date;
  now: Date;
  retrying: boolean;
  stillOffline: boolean;
  onRetry: () => void;
}

export function OfflineBannerView({
  offlineSince,
  now,
  retrying,
  stillOffline,
  onRetry,
}: OfflineBannerViewProps) {
  const stale = staleSince(offlineSince, now);
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2.5 border-b border-risk-line bg-risk-soft px-4 py-2 text-[12.5px] text-fg-2 md:px-[22px]"
    >
      <WifiOff aria-hidden="true" className="h-4 w-4 flex-none text-risk" />
      <span className="min-w-0 flex-1">
        <b className="font-semibold text-fg">You&apos;re offline.</b> {stale}
        <span className="hidden md:inline">
          {' '}
          Your sessions keep running on LlamaTrade&apos;s servers, and orders still go to Alpaca.
        </span>
        {stillOffline && <span className="text-fg-3"> Still no connection.</span>}
      </span>
      <button
        type="button"
        onClick={onRetry}
        disabled={retrying}
        className="flex-none text-[12.5px] font-medium text-accent hover:underline disabled:opacity-60"
      >
        {retrying ? 'Checking…' : 'Retry now'}
      </button>
    </div>
  );
}

/** A thin banner under the top bar while the browser is offline. Clears on reconnect. */
export function OfflineBanner() {
  const { online, offlineSince } = useOnline();
  const [retrying, setRetrying] = useState(false);
  const [stillOffline, setStillOffline] = useState(false);

  useEffect(() => {
    if (online) setStillOffline(false);
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
