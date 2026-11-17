import { useRef, type KeyboardEvent, type ReactNode } from 'react';

import type { AccountScope } from '../../lib/scope';

import { radioKeyTarget } from './radioKeys';

export interface ScopeOption {
  key: AccountScope;
  /** "All accounts", "Live ••4821", "Paper ••PA92" */
  label: string;
  /** The balance under the label, when the page knows it. */
  detail?: ReactNode;
}

interface ScopeControlProps {
  options: readonly ScopeOption[];
  value: AccountScope;
  onChange: (scope: AccountScope) => void;
  className?: string;
}

/**
 * Which money the page shows (mode2 A): All accounts, Live or Paper, each with its balance.
 * With a single option it shows that account as a plain label, since there is nothing to pick.
 */
export function ScopeControl({ options, value, onChange, className = '' }: ScopeControlProps) {
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const checked = Math.max(
    0,
    options.findIndex((o) => o.key === value)
  );

  if (options.length === 0) return null;
  if (options.length === 1) {
    const [only] = options;
    return (
      <div
        className={`inline-flex flex-col rounded-[10px] border border-line bg-panel px-3 py-1.5 ${className}`}
      >
        <span className="text-[12.5px] font-medium text-fg">{only.label}</span>
        {only.detail && <span className="font-mono text-[11px] text-fg-3">{only.detail}</span>}
      </div>
    );
  }

  const onKey = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = radioKeyTarget(e.key, index, options.length);
    if (next === null) return;
    e.preventDefault();
    onChange(options[next].key);
    buttons.current[next]?.focus();
  };

  return (
    <div
      role="radiogroup"
      aria-label="Accounts shown"
      className={`inline-flex max-w-full gap-0.5 overflow-x-auto rounded-[10px] border border-line bg-panel p-[3px] no-scrollbar ${className}`}
    >
      {options.map((o, i) => {
        const on = i === checked;
        return (
          <button
            key={o.key}
            ref={(el) => {
              buttons.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={i === checked ? 0 : -1}
            onKeyDown={(e) => onKey(e, i)}
            onClick={() => onChange(o.key)}
            className={`flex min-w-0 flex-1 flex-col items-start whitespace-nowrap rounded-[7px] px-3 py-1 text-left transition-colors sm:flex-none ${
              on
                ? 'bg-sunk text-fg shadow-[inset_0_0_0_1px_rgb(var(--line-strong))]'
                : 'text-fg-2 hover:text-fg'
            }`}
          >
            <span className="text-[12.5px] font-medium">{o.label}</span>
            {o.detail && <span className="font-mono text-[11px] text-fg-3">{o.detail}</span>}
          </button>
        );
      })}
    </div>
  );
}
