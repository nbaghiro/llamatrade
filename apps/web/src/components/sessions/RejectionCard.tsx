import { Link } from 'react-router-dom';

import { formatMoney, formatNumber } from '../../lib/format';

import type { Rejection } from './rejection';

interface RejectionCardProps {
  rejection: Rejection;
  /** The session is running, so a smaller order can go through its checks now. */
  canPlace: boolean;
  placing: boolean;
  error: string | null;
  /** "today" or "Dec 1": when the next rebalance runs. */
  nextLabel: string | null;
  onPlace: () => void;
}

const TIME = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

/** The card that opens from a rejected order's marker on the session's lanes (order2 B). */
export function RejectionCard({
  rejection: r,
  canPlace,
  placing,
  error,
  nextLabel,
  onPlace,
}: RejectionCardProps) {
  const side = r.title.startsWith('Sell') ? 'Sell' : 'Place';
  const fits = canPlace && r.fits > 0;
  return (
    <div className="grid w-[300px] gap-2 text-[12.5px] leading-[1.5]">
      <div className="flex items-baseline gap-2">
        <b className="font-semibold text-fg">{r.title}</b>
        <span className="num ml-auto text-[11px] text-fg-3">{TIME.format(r.at)}</span>
      </div>
      <p className="m-0 text-fg-2">
        {r.reason} {r.sent}
        {r.othersClear ? ' The other checks found nothing.' : ''}
      </p>
      {r.leftBehind && (
        <p className="m-0 text-fg-2">
          {r.leftBehind}
          {nextLabel ? ` The next rebalance is ${nextLabel}.` : ''}
        </p>
      )}
      {error && (
        <p role="alert" className="m-0 text-risk">
          {error}
        </p>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {fits && (
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={placing}
            onClick={onPlace}
            title={`${formatMoney(r.fits * r.price)} at the price used for this order`}
          >
            {placing ? 'Placing…' : `${side} ${formatNumber(r.fits, { dp: 0 })} ${r.order.symbol}`}
          </button>
        )}
        <Link
          to={`/trading/orders/${r.order.id}`}
          className="ml-auto text-[12px] text-fg-3 hover:text-fg hover:underline"
        >
          Order page
        </Link>
      </div>
    </div>
  );
}
