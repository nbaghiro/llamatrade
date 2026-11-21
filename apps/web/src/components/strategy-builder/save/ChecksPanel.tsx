import { AlertTriangle, Check, X } from 'lucide-react';

import { RailPanel } from '../rail/RailPanel';

import type { CheckItem } from './checkList';

const time = (d: Date) => d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

/** problems2 A: every check in the validator's words, with its line and what it means. */
export function ChecksPanel({
  items,
  checkedAt,
  onGoToLine,
}: {
  items: readonly CheckItem[];
  checkedAt: Date | null;
  onGoToLine?: (line: number) => void;
}) {
  if (items.length === 0) return null;
  return (
    <RailPanel title="Checks" meta={checkedAt ? `validated ${time(checkedAt)}` : undefined}>
      <ul className="-my-1 m-0 grid list-none p-0">
        {items.map((c) => {
          const fixed = c.fixedAt !== null;
          const Icon = fixed ? Check : c.severity === 'error' ? X : AlertTriangle;
          return (
            <li
              key={c.key}
              className="grid grid-cols-[16px_minmax(0,1fr)_auto] gap-x-2 gap-y-1 border-b border-line py-2.5 last:border-b-0"
            >
              <Icon
                className={`mt-0.5 h-3.5 w-3.5 ${fixed ? 'text-fg-3' : 'text-risk'}`}
                aria-hidden="true"
              />
              <span
                className={`font-mono text-[12px] leading-[1.5] ${fixed ? 'text-fg-3 line-through' : 'text-fg'}`}
              >
                {c.message}
              </span>
              {fixed ? (
                <i className="font-mono text-[11px] not-italic text-fg-3">fixed</i>
              ) : c.line !== null && onGoToLine ? (
                <button
                  type="button"
                  onClick={() => onGoToLine(c.line as number)}
                  className="font-mono text-[11px] text-fg-3 hover:text-fg hover:underline"
                >
                  line {c.line}
                </button>
              ) : c.line !== null ? (
                <i className="font-mono text-[11px] not-italic text-fg-3">line {c.line}</i>
              ) : (
                <span />
              )}
              <span className="col-start-2 col-end-4 text-[12px] leading-[1.5] text-fg-3">
                {fixed && c.fixedAt
                  ? `${c.severity === 'error' ? 'Error' : 'Warning'}, fixed at ${time(c.fixedAt)}.`
                  : c.explain}
              </span>
            </li>
          );
        })}
      </ul>
    </RailPanel>
  );
}
