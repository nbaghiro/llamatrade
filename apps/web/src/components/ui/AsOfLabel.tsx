import { useEffect, useState } from 'react';

import { asOfCloseLabel, isSessionOpen } from '../../lib/marketClock';

interface AsOfLabelProps {
  /** Show the label during market hours too. */
  always?: boolean;
  className?: string;
}

/** "As of Fri, Nov 13 close" when the market is closed, so figures say where they come from. */
export function AsOfLabel({ always = false, className = '' }: AsOfLabelProps) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);
  if (!always && isSessionOpen(now)) return null;
  return <span className={`text-[12px] text-fg-3 ${className}`}>{asOfCloseLabel(now)}</span>;
}
