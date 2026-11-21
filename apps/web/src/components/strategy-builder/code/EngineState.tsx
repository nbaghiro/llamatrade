import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';

import type { EngineCheck } from '../hooks/useEngineCheck';
import { plural } from '../save/checkList';

/** The engine's answer for the draft, in a panel header: passed, or "0 errors · 2 warnings". */
export function EngineState({
  engine,
  counts,
}: {
  engine: EngineCheck;
  /** Open errors and warnings from the checks; defaults to the engine's errors alone. */
  counts?: { errors: number; warnings: number };
}) {
  const errors =
    counts?.errors ?? (engine.status === 'problems' ? (engine.errors?.length ?? 0) : 0);
  const warn = counts?.warnings ?? 0;

  if (engine.status === 'problems' || errors > 0 || warn > 0) {
    return (
      <span role="status" className="flex items-center gap-3 text-[12.5px]">
        <span className={`flex items-center gap-1 ${errors ? 'text-risk' : 'text-fg-3'}`}>
          {errors ? (
            <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {plural(errors, 'error', 'errors')}
        </span>
        {warn > 0 && (
          <span className="flex items-center gap-1 text-risk">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
            {plural(warn, 'warning', 'warnings')}
          </span>
        )}
      </span>
    );
  }

  const text = {
    idle: 'Not checked yet',
    checking: 'Checking',
    ok: 'Engine check passed',
    problems: '',
    unavailable: 'Checks unavailable just now',
  }[engine.status];
  return (
    <span role="status" className="flex items-center gap-1.5 text-[12.5px] text-fg-2">
      <i
        aria-hidden="true"
        className={`inline-block h-1.5 w-1.5 rounded-full ${engine.status === 'ok' ? 'bg-accent' : 'bg-line-strong'}`}
      />
      {text}
    </span>
  );
}
