import { useMemo } from 'react';

import { diffCode } from '../../../lib/strategyDiff';

/** A line diff of two versions' code; added lines in the accent, removed lines struck. */
export function CodeDiff({ before, after }: { before: string; after: string }) {
  const lines = useMemo(() => diffCode(before, after), [before, after]);
  return (
    <div className="panel overflow-x-auto py-3 font-mono text-[12.5px] leading-[1.8]">
      {lines.map((l, i) => (
        <div
          key={i}
          className={`grid grid-cols-[28px_44px_minmax(0,1fr)] whitespace-pre pr-4 ${
            l.kind === 'add'
              ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]'
              : l.kind === 'del'
                ? 'bg-hatch text-fg-3 shadow-[inset_2px_0_0_rgb(var(--fg-3))]'
                : ''
          }`}
        >
          <span
            className={`pl-2 ${l.kind === 'add' ? 'text-accent' : 'text-fg-3'}`}
            aria-hidden="true"
          >
            {l.kind === 'add' ? '+' : l.kind === 'del' ? '−' : ''}
          </span>
          <span className="pr-4 text-right text-fg-3 opacity-70">{l.newLine ?? l.oldLine}</span>
          <span className={l.kind === 'del' ? 'line-through decoration-fg-3' : ''}>
            <span className="sr-only">
              {l.kind === 'add' ? 'Added: ' : l.kind === 'del' ? 'Removed: ' : ''}
            </span>
            {l.text || ' '}
          </span>
        </div>
      ))}
    </div>
  );
}
