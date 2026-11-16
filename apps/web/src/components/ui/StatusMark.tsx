export type RunState = 'running' | 'waiting' | 'paused' | 'frozen' | 'stopped' | 'error' | 'draft';

const LABEL: Record<RunState, string> = {
  running: 'Running',
  waiting: 'Waiting for data',
  paused: 'Paused',
  frozen: 'Frozen',
  stopped: 'Stopped',
  error: 'Error',
  draft: 'Draft',
};

const DOT: Record<RunState, string> = {
  running: 'rounded-full bg-fg',
  waiting: 'rounded-full bg-fg-3 motion-safe:animate-pulse',
  paused: 'rounded-full shadow-[inset_0_0_0_1.5px_rgb(var(--fg-3))]',
  frozen: 'rounded-[2px] bg-risk',
  stopped: 'rounded-full shadow-[inset_0_0_0_1.5px_rgb(var(--fg-3))]',
  error: 'rotate-45 scale-[0.86] rounded-[1px] shadow-[inset_0_0_0_1.5px_rgb(var(--risk))]',
  draft: 'rounded-[2px] shadow-[inset_0_0_0_1.5px_rgb(var(--fg-3))]',
};

interface StatusMarkProps {
  state: RunState;
  /** Replaces the default label, e.g. "Running since Oct 1". */
  label?: string;
  className?: string;
}

/** A dot and a word for a strategy or session state. Frozen and error are amber. */
export function StatusMark({ state, label, className = '' }: StatusMarkProps) {
  const attention = state === 'frozen' || state === 'error';
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap text-[12.5px] ${
        attention ? 'text-risk' : 'text-fg-2'
      } ${className}`}
    >
      <i aria-hidden="true" className={`h-[7px] w-[7px] flex-none ${DOT[state]}`} />
      {label ?? LABEL[state]}
    </span>
  );
}
