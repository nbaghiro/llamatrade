import type { ValidationIssue } from '@llamatrade/core/strategy/validator';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

import type { EngineCheck } from '../hooks/useEngineCheck';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The engine's answer for the draft, in a panel header: passed, errors, or warnings. */
export function EngineState({
  engine,
  warnings = [],
}: {
  engine: EngineCheck;
  warnings?: readonly ValidationIssue[];
}) {
  const errors = engine.status === 'problems' ? (engine.errors?.length ?? 0) : 0;
  const warn = warnings.length;

  if (engine.status === 'problems' || warn > 0) {
    return (
      <span role="status" className="flex items-center gap-3 text-[12.5px]">
        <span className={`flex items-center gap-1 ${errors ? 'text-loss' : 'text-fg-2'}`}>
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
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
