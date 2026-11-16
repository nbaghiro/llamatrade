import { AlertTriangle, RotateCw } from 'lucide-react';

import { asSentence } from '../../lib/format';

interface PanelErrorProps {
  /** What failed, e.g. "The definition couldn't be loaded". */
  title: string;
  /** Why it failed, in a sentence. */
  cause?: string;
  /** What still works, e.g. "The strategy and its session aren't affected." */
  unaffected?: string;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}

/** Shown inside the one panel that failed, so the rest of the page keeps working. */
export function PanelError({
  title,
  cause,
  unaffected,
  onRetry,
  retrying = false,
  className = '',
}: PanelErrorProps) {
  return (
    <div
      role="alert"
      className={`grid justify-items-center gap-2 px-6 py-9 text-center ${className}`}
    >
      <span className="grid h-10 w-10 place-items-center rounded-[10px] bg-risk-soft text-risk">
        <AlertTriangle className="h-5 w-5" />
      </span>
      <h5 className="m-0 text-[15px] font-semibold text-fg">{title}</h5>
      {(cause || unaffected) && (
        <p className="m-0 max-w-[400px] text-[12.5px] text-fg-2">
          {[asSentence(cause), unaffected].filter(Boolean).join(' ')}
        </p>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="btn btn-secondary mt-1"
        >
          <RotateCw className={`h-3.5 w-3.5 ${retrying ? 'motion-safe:animate-spin' : ''}`} />
          Try again
        </button>
      )}
    </div>
  );
}
