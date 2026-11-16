import { Search } from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';

import { noMatchSentence } from '../../lib/emptyState';

interface EmptyStateProps {
  title: string;
  /** One sentence on what belongs here and how to start. */
  body?: string;
  icon?: ComponentType<{ className?: string }>;
  /** Up to two routes, the primary one last. */
  actions?: ReactNode;
  className?: string;
}

export function EmptyState({ title, body, icon: Icon, actions, className = '' }: EmptyStateProps) {
  return (
    <div className={`grid justify-items-center gap-2 px-6 py-9 text-center ${className}`}>
      {Icon && (
        <span className="grid h-10 w-10 place-items-center rounded-[10px] bg-sunk text-fg-2">
          <Icon className="h-5 w-5" />
        </span>
      )}
      <h5 className="m-0 text-[15px] font-semibold text-fg">{title}</h5>
      {body && <p className="m-0 max-w-[400px] text-[12.5px] text-fg-2">{body}</p>}
      {actions && <div className="mt-1 flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  );
}

interface NoMatchProps {
  /** Plural noun for the list, e.g. "strategies". */
  noun: string;
  query?: string;
  /** Active filter names, e.g. ["Draft"]. */
  filters?: readonly string[];
  total?: number;
  onClear: () => void;
  className?: string;
}

/** The empty state for a search or filter that matched nothing, so it can't read as an empty account. */
export function NoMatch({ noun, query, filters = [], total, onClear, className }: NoMatchProps) {
  return (
    <EmptyState
      className={className}
      icon={Search}
      title="Nothing matches these filters"
      body={noMatchSentence({ noun, query, filters, total })}
      actions={
        <button type="button" onClick={onClear} className="btn btn-secondary">
          Clear filters
        </button>
      }
    />
  );
}
