import type { ReactNode } from 'react';

import { PanelError } from '../ui';

import type { Fill } from './homeModel';

export function HomePanel({
  title,
  aside,
  children,
  className = '',
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label={title}
      className={`overflow-hidden rounded-panel border border-line bg-panel ${className}`}
    >
      <div className="flex min-h-[44px] items-center justify-between gap-3 border-b border-line px-4 text-[13px]">
        <b className="font-semibold">{title}</b>
        {aside && <span className="text-[12px] text-fg-3">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

export function SideTag({ side }: { side: Fill['side'] }) {
  return (
    <span className="inline-flex h-[19px] w-[38px] flex-none items-center justify-center rounded-[4px] border border-line font-mono text-[9.5px] font-semibold tracking-[0.05em] text-fg-2">
      {side === 'buy' ? 'BUY' : 'SELL'}
    </span>
  );
}

export function FillsFailed({ onRetry, retrying }: { onRetry: () => void; retrying: boolean }) {
  return (
    <PanelError
      title="Fills couldn't be loaded"
      cause="The trading service didn't answer. Fills are still recorded and will show here once it does."
      onRetry={onRetry}
      retrying={retrying}
    />
  );
}

/** A Home card on the wide layout: a title, a quieter line beside it, and controls on the right. */
export function HomeCard({
  title,
  sub,
  right,
  children,
  className = '',
}: {
  title: string;
  sub?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label={title}
      className={`min-w-0 rounded-panel border border-line bg-panel ${className}`}
    >
      <div className="flex min-h-[52px] flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-5 py-2.5">
        <h2 className="m-0 text-[14px] font-semibold text-fg">{title}</h2>
        {sub && <span className="text-[12.5px] text-fg-3">{sub}</span>}
        {right && <div className="ml-auto flex flex-wrap items-center gap-3">{right}</div>}
      </div>
      {children}
    </section>
  );
}
