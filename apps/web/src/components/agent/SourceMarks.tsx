import { Link } from 'react-router-dom';

import type { SourceView } from './sources';

export function CitationMark({
  n,
  active = false,
  onClick,
}: {
  n: number;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Source ${n}`}
      className={`inline-grid h-4 min-w-4 place-items-center rounded-[4px] px-1 align-[2px] font-mono text-[10px] ${
        active ? 'bg-fg text-canvas' : 'bg-sunk text-fg-2 hover:bg-fg hover:text-canvas'
      }`}
    >
      {n}
    </button>
  );
}

/** What an answer read, as "1 Strategy" links under it. */
export function SourceChips({
  sources,
  active = null,
  onCite,
}: {
  sources: readonly SourceView[];
  active?: number | null;
  onCite?: (n: number) => void;
}) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-fg-3">
      {sources.map((s) => {
        const label = (
          <>
            <span className={`font-mono ${s.n === active ? 'text-fg' : ''}`}>{s.n}</span>{' '}
            <span className="max-w-[220px] truncate">{s.title}</span>
          </>
        );
        return s.href ? (
          <Link
            key={`${s.n}-${s.id}`}
            to={s.href}
            onMouseEnter={() => onCite?.(s.n)}
            className="inline-flex items-baseline gap-1 hover:text-fg"
          >
            {label}
          </Link>
        ) : (
          <span key={`${s.n}-${s.id}`} className="inline-flex items-baseline gap-1">
            {label}
          </span>
        );
      })}
    </div>
  );
}
