import { AlertTriangle, Check } from 'lucide-react';
import type { ReactNode } from 'react';

import { RISK_CHECKS } from '../../lib/sessionState';

interface CheckLadderProps {
  /** Indexes into RISK_CHECKS that stopped the order. */
  stopped: readonly number[];
  /** What a stopping check found, e.g. "$11,210.84 is over $10,000.00". */
  found?: Readonly<Record<number, ReactNode>>;
  /** For the other checks: 'unknown' (not recorded) or 'clear' (no failure was recorded). */
  others?: 'unknown' | 'clear' | 'passed';
}

const OTHER_TEXT = {
  unknown: 'Not recorded',
  clear: 'No failure recorded',
  passed: 'Passed',
} as const;

/**
 * The seven pre-trade checks in order. Only failures are stored, so a check that wasn't stopped
 * reads as not recorded, or as no failure recorded once the order has a stored result.
 */
export function CheckLadder({ stopped, found = {}, others = 'unknown' }: CheckLadderProps) {
  return (
    <ol className="m-0 list-none p-0" aria-label="Risk checks">
      {RISK_CHECKS.map((name, i) => {
        const hit = stopped.includes(i);
        return (
          <li
            key={name}
            className={`grid min-h-10 grid-cols-[22px_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-line px-3.5 py-2 text-[12.5px] last:border-b-0 ${
              hit ? 'bg-risk-soft shadow-[inset_2px_0_0_rgb(var(--risk))]' : ''
            }`}
          >
            {hit ? (
              <AlertTriangle className="h-3.5 w-3.5 text-risk" aria-hidden="true" />
            ) : others === 'unknown' ? (
              <span className="num text-[11px] font-medium text-fg-3">{i + 1}</span>
            ) : (
              <Check className="h-3.5 w-3.5 text-fg-3" aria-hidden="true" />
            )}
            <span className="truncate">{name}</span>
            <span
              className={`text-right text-[11.5px] ${hit ? 'font-semibold text-risk' : 'text-fg-3'}`}
            >
              {hit ? (found[i] ?? 'Stopped') : OTHER_TEXT[others]}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
