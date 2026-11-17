import type { ReactNode } from 'react';

export interface StatItem {
  label: ReactNode;
  value: ReactNode;
  /** Colour for profit and loss only. */
  tone?: 'gain' | 'loss';
}

const TONE = { gain: 'text-gain', loss: 'text-loss' } as const;

/** Label and figure rows with hairlines between, as beside the annotated curve. */
export function StatList({
  items,
  className = '',
}: {
  items: readonly StatItem[];
  className?: string;
}) {
  return (
    <dl className={`m-0 ${className}`}>
      {items.map((it, i) => (
        <div
          key={i}
          className="flex items-baseline justify-between gap-3 border-b border-line py-[7px] text-[12.5px] last:border-b-0"
        >
          <dt className="min-w-0 truncate text-fg-2">{it.label}</dt>
          <dd
            className={`m-0 flex-none font-mono tabular-nums ${it.tone ? TONE[it.tone] : 'text-fg'}`}
          >
            {it.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
