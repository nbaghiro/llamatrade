import type { ReactNode } from 'react';

/** A legend entry for a curve: a solid line for the main series, dashed for a comparison. */
export function LineKey({
  dashed = false,
  muted = false,
  children,
}: {
  dashed?: boolean;
  /** A grey solid line, for a backtest drawn without a session. */
  muted?: boolean;
  children: ReactNode;
}) {
  const line = dashed
    ? 'border-dashed border-fg-3'
    : muted
      ? 'border-solid border-fg-2'
      : 'border-solid border-accent';
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[11.5px] text-fg-3">
      <i aria-hidden="true" className={`block w-3.5 border-t-[1.5px] ${line}`} />
      {children}
    </span>
  );
}
