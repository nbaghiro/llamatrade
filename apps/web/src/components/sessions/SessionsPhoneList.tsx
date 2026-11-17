import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { toDate } from '@llamatrade/core/stores/backtest';
import { Link } from 'react-router-dom';

import { ModeBadge } from '../ui/ModeBadge';
import { Money, Pct } from '../ui/Num';

import { dayLabel, rowNextRebalance, type SessionRow } from './sessionRows';
import { etDayLabel } from './timeline';

/** Running then stopped, with value and today's move; timing beyond the next rebalance is a tap away. */
export function SessionsPhoneList({ rows, today }: { rows: readonly SessionRow[]; today: Date }) {
  const open = rows.filter((r) => r.view.open);
  const stopped = rows.filter((r) => !r.view.open);
  return (
    <div className="grid gap-3">
      {open.length > 0 && <Group title="Running" rows={open} today={today} />}
      {stopped.length > 0 && <Group title="Stopped" rows={stopped} today={today} />}
    </div>
  );
}

function Group({
  title,
  rows,
  today,
}: {
  title: string;
  rows: readonly SessionRow[];
  today: Date;
}) {
  const stopped = title === 'Stopped';
  return (
    <section aria-label={title}>
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-fg-3">
        {title}
      </div>
      <div
        className={`overflow-hidden rounded-panel border bg-panel ${stopped ? 'border-dashed border-line-strong' : 'border-line'}`}
      >
        {rows.map((r) => {
          const next = rowNextRebalance(r, today);
          const ended = toDate(r.session.endedAt);
          const f = r.figures;
          return (
            <Link
              key={r.session.id}
              to={`/trading/${r.session.id}`}
              className="flex items-center gap-3 border-b border-line px-3.5 py-3 last:border-b-0"
            >
              <span className="min-w-0 flex-1">
                <span
                  className={`block truncate text-[13.5px] ${stopped ? 'text-fg-2' : 'text-fg'}`}
                >
                  {r.name}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-fg-3">
                  {!stopped && (
                    <ModeBadge
                      mode={r.session.mode === ExecutionMode.LIVE ? 'live' : 'paper'}
                      size="sm"
                    />
                  )}
                  {r.state === 'frozen' ? (
                    <span className="text-risk">frozen</span>
                  ) : r.state === 'paused' ? (
                    'paused'
                  ) : stopped ? (
                    ended ? (
                      `Stopped ${etDayLabel(ended)}`
                    ) : (
                      r.view.label
                    )
                  ) : next ? (
                    `next ${dayLabel(next)}`
                  ) : (
                    r.rebalance.toLowerCase() || r.view.label.toLowerCase()
                  )}
                </span>
              </span>
              <span className="flex-none text-right">
                {f.equity !== null && (
                  <Money
                    value={f.equity}
                    className={`block text-[12.5px] ${stopped ? 'text-fg-2' : ''}`}
                  />
                )}
                <span className="block text-[11px]">
                  {stopped
                    ? f.totalPct !== null && <Pct value={f.totalPct} pnl dp={1} />
                    : f.today !== null && <Money value={f.today} pnl />}
                </span>
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
