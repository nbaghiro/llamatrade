import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { Brief } from './paper';
import { Kicker } from './ui';

/** A group of short briefs in the narrow column: a kicker, then dated one-liners. */
export function Briefs({
  title,
  items,
  right,
  empty = 'Nothing yet.',
}: {
  title: string;
  items: Brief[];
  right?: ReactNode;
  empty?: string;
}) {
  return (
    <section className="mb-9 last:mb-0">
      <Kicker right={right}>{title}</Kicker>
      {items.length === 0 ? (
        <p className="m-0 py-3 text-[12.5px] text-fg-3">{empty}</p>
      ) : (
        <ul className="m-0 list-none p-0">
          {items.map((b, i) => {
            const body = (
              <>
                <span className="font-mono text-[10.5px] uppercase tabular-nums tracking-[0.04em] text-fg-3">
                  {b.when}
                </span>
                <span className="min-w-0">
                  <span
                    className={`block text-[13px] font-medium ${b.tone === 'gain' ? 'text-gain' : b.tone === 'loss' ? 'text-loss' : 'text-fg'}`}
                  >
                    {b.title}
                  </span>
                  <span className="block text-[12px] leading-[1.45] text-fg-3">{b.detail}</span>
                </span>
              </>
            );
            const cls =
              'grid grid-cols-[52px_minmax(0,1fr)] items-baseline gap-3 border-b border-line py-2.5 last:border-b-0';
            return (
              <li key={i}>
                {b.to ? (
                  <Link to={b.to} className={`${cls} transition-colors hover:bg-panel/70`}>
                    {body}
                  </Link>
                ) : (
                  <div className={cls}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** A label and a figure on one ruled line, for figures in the narrow column. */
export function Stat({
  label,
  children,
  sub,
}: {
  label: string;
  children: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-2.5 last:border-b-0">
      <span className="text-[12.5px] text-fg-2">{label}</span>
      <span className="text-right">
        <span className="font-mono text-[14px] tabular-nums text-fg">{children}</span>
        {sub !== undefined && (
          <span className="ml-2 font-mono text-[11px] tabular-nums text-fg-3">{sub}</span>
        )}
      </span>
    </div>
  );
}
