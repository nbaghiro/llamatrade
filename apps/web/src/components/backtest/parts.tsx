import type { ReactNode } from 'react';

import type { LogLine } from '../../lib/backtestView';
import { StatusMark } from '../ui/StatusMark';

/** A bordered panel with an optional header row and footer. */
export function Panel({
  title,
  aside,
  footer,
  children,
  tone = 'plain',
  className = '',
}: {
  title?: ReactNode;
  aside?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  tone?: 'plain' | 'risk';
  className?: string;
}) {
  return (
    <section
      className={`min-w-0 overflow-hidden rounded-panel border bg-panel ${
        tone === 'risk' ? 'border-risk-line' : 'border-line'
      } ${className}`}
    >
      {(title || aside) && (
        <header className="flex min-h-[38px] items-center justify-between gap-2.5 border-b border-line px-3.5 py-[9px]">
          {title && (
            <h2 className="m-0 font-sans text-[13px] font-semibold tracking-normal">{title}</h2>
          )}
          {aside && <div className="text-[11.5px] text-fg-3">{aside}</div>}
        </header>
      )}
      {children}
      {footer && (
        <footer className="border-t border-line px-3.5 py-2.5 text-xs text-fg-2">{footer}</footer>
      )}
    </section>
  );
}

/** The page title row: title and meta on the left, actions on the right. */
export function PageHead({
  title,
  meta,
  actions,
}: {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        <h1 className="m-0 text-[21px] leading-tight">{title}</h1>
        {meta && <div className="mt-1 text-xs text-fg-3">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export interface Cell {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}

const CELL_COLS = {
  3: 'grid-cols-3',
  4: 'grid-cols-2 sm:grid-cols-4',
  6: 'grid-cols-3 lg:grid-cols-6',
} as const;

/** A row of labelled figures divided by rules. */
export function Cells({
  cells,
  cols = 6,
}: {
  cells: readonly Cell[];
  cols?: keyof typeof CELL_COLS;
}) {
  return (
    <dl className={`m-0 grid ${CELL_COLS[cols]}`}>
      {cells.map((c) => (
        <div
          key={c.label}
          className="min-w-0 border-b border-r border-line px-3.5 py-[11px] [&:nth-last-child(-n+1)]:border-r-0"
        >
          <dt className="text-[11px] font-medium text-fg-3">{c.label}</dt>
          <dd className="m-0 mt-1 whitespace-nowrap font-mono text-[19px] font-medium leading-tight tracking-[-0.02em] tabular-nums">
            {c.value}
          </dd>
          {c.sub && (
            <dd className="m-0 mt-0.5 whitespace-nowrap font-mono text-[11px] text-fg-3">
              {c.sub}
            </dd>
          )}
        </div>
      ))}
    </dl>
  );
}

/** A figure that waits for the whole run. */
export function Pending({ label = 'Not available yet' }: { label?: string }) {
  return (
    <span className="text-fg-3" aria-label={label} title={label}>
      ·
    </span>
  );
}

export function SideTag({ side }: { side: string }) {
  return (
    <span className="rounded-sm px-[5px] py-[3px] font-mono text-[10px] font-semibold leading-none ring-1 ring-inset ring-line-strong">
      {side}
    </span>
  );
}

/** Label and value rows, as in a summary panel. */
export function KvList({ rows }: { rows: readonly [string, ReactNode][] }) {
  return (
    <dl className="m-0">
      {rows.map(([k, v]) => (
        <div
          key={k}
          className="flex justify-between gap-3 border-b border-line py-[7px] text-[12.5px] last:border-b-0"
        >
          <dt className="text-fg-2">{k}</dt>
          <dd className="m-0 text-right">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

const LOG_MARK: Record<LogLine['tone'], { mark: string; cls: string }> = {
  ok: { mark: '✓', cls: 'text-fg' },
  now: { mark: '›', cls: 'text-fg' },
  bad: { mark: '!', cls: 'text-risk' },
  note: { mark: '·', cls: 'text-fg-2' },
};

/** The run log: elapsed seconds beside each line. */
export function RunLogList({ lines }: { lines: readonly LogLine[] }) {
  return (
    <ol
      className="m-0 list-none px-3.5 py-3 font-mono text-[11.5px] leading-[1.8] text-fg-2"
      aria-live="polite"
    >
      {lines.map((l, i) => (
        <li key={`${i}-${l.text}`} className="grid grid-cols-[50px_1fr] gap-2">
          <span className="text-fg-3">{l.at.toFixed(2)}s</span>
          <span className={LOG_MARK[l.tone].cls}>
            <span className={l.tone === 'bad' ? '' : 'text-accent'} aria-hidden="true">
              {LOG_MARK[l.tone].mark}{' '}
            </span>
            {l.text}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** A backtest's state as a mark and a word. Failed is amber; nothing was lost. */
export function RunStatus({
  phase,
  label,
  className = '',
}: {
  phase: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  label?: string;
  className?: string;
}) {
  if (phase === 'completed') {
    return (
      <span
        className={`inline-flex items-center gap-1.5 whitespace-nowrap text-[12.5px] text-fg-2 ${className}`}
      >
        <i aria-hidden="true" className="h-[7px] w-[7px] flex-none rounded-full bg-fg-2" />
        {label ?? 'Completed'}
      </span>
    );
  }
  const map = {
    pending: ['waiting', 'Queued'],
    running: ['running', 'Running'],
    failed: ['error', 'Failed'],
    cancelled: ['stopped', 'Cancelled'],
  } as const;
  const [state, word] = map[phase];
  return <StatusMark state={state} label={label ?? word} className={className} />;
}
