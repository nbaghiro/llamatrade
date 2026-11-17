import { AlertTriangle, ChevronRight, Snowflake } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { NeedItem } from './needs';

/** One amber card per issue on wide screens, one amber card of rows on a phone (phone2 B). */
export function NeedsYou({ items }: { items: readonly NeedItem[] }) {
  if (!items.length) return null;
  return (
    <section aria-label="Needs you">
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-fg-3">
        Needs you
      </div>
      <div className="hidden gap-3 md:grid md:grid-cols-2">
        {items.map((it) => {
          const Icon = it.kind === 'frozen' ? Snowflake : AlertTriangle;
          return (
            <div
              key={it.id}
              className="flex items-start gap-3 rounded-panel border border-risk-line bg-risk-soft px-4 py-3"
            >
              <Icon className="mt-0.5 h-4 w-4 flex-none text-risk" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <b className="block text-[13px] font-semibold text-fg">{it.title}</b>
                <p className="m-0 mt-0.5 text-[12.5px] text-fg-2">{it.detail}</p>
              </div>
              <Link to={it.href} className="btn btn-secondary btn-sm flex-none">
                Review
              </Link>
            </div>
          );
        })}
      </div>
      <div className="overflow-hidden rounded-panel border border-risk-line bg-risk-soft md:hidden">
        {items.map((it) => {
          const Icon = it.kind === 'frozen' ? Snowflake : AlertTriangle;
          return (
            <Link
              key={it.id}
              to={it.href}
              className="flex items-center gap-3 border-b border-risk-line px-3.5 py-3 last:border-b-0"
            >
              <Icon className="h-4 w-4 flex-none text-risk" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <b className="block truncate text-[13px] font-semibold">{it.title}</b>
                <span className="block truncate text-[11.5px] text-fg-2">{it.short}</span>
              </span>
              <ChevronRight className="h-4 w-4 flex-none text-fg-3" aria-hidden="true" />
            </Link>
          );
        })}
      </div>
    </section>
  );
}
