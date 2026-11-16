import { useRef, type KeyboardEvent, type ReactNode } from 'react';

import { radioKeyTarget } from './radioKeys';

export interface TabOption<K extends string> {
  key: K;
  label: ReactNode;
}

interface TabsProps<K extends string> {
  options: readonly TabOption<K>[];
  value: K;
  onChange: (key: K) => void;
  label: string;
  className?: string;
}

/** Underlined page tabs. */
export function Tabs<K extends string>({
  options,
  value,
  onChange,
  label,
  className = '',
}: TabsProps<K>) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className={`flex gap-1 border-b border-line ${className}`}
    >
      {options.map((o) => {
        const on = o.key === value;
        return (
          <button
            key={o.key}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(o.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${
              on ? 'border-accent text-fg' : 'border-transparent text-fg-2 hover:text-fg'
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** A compact segmented control for a short set of choices. */
export function Segmented<K extends string>({
  options,
  value,
  onChange,
  label,
  className = '',
}: TabsProps<K>) {
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const checked = Math.max(
    0,
    options.findIndex((o) => o.key === value)
  );
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
      aria-label={label}
      className={`inline-flex gap-0.5 rounded-[8px] border border-line bg-panel p-0.5 ${className}`}
    >
      {options.map((o, i) => {
        const on = o.key === value;
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
            className={`whitespace-nowrap rounded-[6px] px-2.5 py-1 text-[12.5px] transition-colors ${
              on ? 'bg-sunk text-fg' : 'text-fg-2 hover:text-fg'
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
