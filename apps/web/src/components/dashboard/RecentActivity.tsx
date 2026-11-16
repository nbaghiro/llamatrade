import { dateShort } from '@llamatrade/core/format';
import {
  useDashboardStore,
  type ActivityKind,
  type DashboardActivity,
} from '@llamatrade/core/stores/dashboard';
import { Link } from 'react-router-dom';

import { EmptyState } from '../ui';

const TAG: Record<ActivityKind, string> = {
  buy: 'BUY',
  sell: 'SELL',
  backtest: 'TEST',
  dividend: 'DIV',
};

function Row({ item }: { item: DashboardActivity }) {
  return (
    <li className="flex items-center gap-3 border-b border-line px-3.5 py-[9px] text-[12.5px] last:border-b-0">
      <span className="w-[38px] flex-none rounded-[3px] border border-line-strong py-0.5 text-center font-mono text-[9.5px] font-medium text-fg-2">
        {TAG[item.kind]}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-fg">{item.title}</span>
        <span className="block truncate text-[11.5px] text-fg-3">{item.subtitle}</span>
      </span>
      <span className="num flex-none text-fg-3">{dateShort(item.at)}</span>
    </li>
  );
}

/** Fills, dividends and finished backtests, newest first. */
export default function RecentActivity() {
  const activity = useDashboardStore((s) => s.activity);

  return (
    <section
      aria-label="Recent activity"
      className="min-w-0 overflow-hidden rounded-panel border border-line bg-panel"
    >
      <div className="flex min-h-[42px] items-center justify-between gap-2.5 border-b border-line px-3.5 py-2.5 text-[12.5px]">
        <b className="font-semibold">Recent activity</b>
        <Link to="/portfolio" className="text-accent hover:underline">
          History
        </Link>
      </div>
      {activity.length > 0 ? (
        <ul className="m-0 list-none p-0">
          {activity.map((item) => (
            <Row key={item.id} item={item} />
          ))}
        </ul>
      ) : (
        <EmptyState
          title="No activity yet"
          body="Fills, dividends and finished backtests appear here as they happen."
        />
      )}
    </section>
  );
}
