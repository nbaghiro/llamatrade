import { groupSessionsByDay, sessionWhen } from '@llamatrade/core/agent/history';
import type { AgentSession } from '@llamatrade/core/stores/agent';
import { Plus, Search, Trash2, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { Skeleton } from '../ui';

interface CopilotHistoryRailProps {
  sessions: readonly AgentSession[];
  currentId: string | null;
  loading: boolean;
  unavailable: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  /** Phones show the rail as its own screen; this closes it. */
  onClose?: () => void;
  className?: string;
}

/** Past conversations grouped by day, with search at the top. */
export function CopilotHistoryRail({
  sessions,
  currentId,
  loading,
  unavailable,
  onSelect,
  onNew,
  onDelete,
  onClose,
  className = '',
}: CopilotHistoryRailProps) {
  const [query, setQuery] = useState('');
  const [confirming, setConfirming] = useState<string | null>(null);
  const groups = useMemo(() => groupSessionsByDay(sessions, query), [sessions, query]);
  const keepRef = useRef<HTMLButtonElement>(null);
  const trashRefs = useRef(new Map<string, HTMLButtonElement>());
  const returnTo = useRef<string | null>(null);

  useEffect(() => {
    if (confirming) {
      keepRef.current?.focus();
    } else if (returnTo.current) {
      trashRefs.current.get(returnTo.current)?.focus();
      returnTo.current = null;
    }
  }, [confirming]);

  const keep = (id: string) => {
    returnTo.current = id;
    setConfirming(null);
  };

  return (
    <aside aria-label="Conversations" className={`flex min-h-0 flex-col bg-panel ${className}`}>
      {onClose && (
        <div className="flex items-center justify-between gap-3 px-4 pt-2 md:hidden">
          <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em]">Conversations</h1>
          <button
            type="button"
            className="btn btn-ghost px-2"
            aria-label="Back to the conversation"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      )}
      <div className="grid gap-2 px-3.5 pb-1 pt-3.5">
        <button type="button" className="btn btn-primary w-full" onClick={onNew}>
          <Plus className="h-3.5 w-3.5" />
          New conversation
        </button>
        <label className="flex h-8 items-center gap-2 rounded-[8px] border border-line-strong bg-panel px-3 text-fg-3 focus-within:border-accent max-md:h-10">
          <Search className="h-4 w-4 flex-none" />
          <span className="sr-only">Search conversations</span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations"
            className="min-w-0 flex-1 bg-transparent text-[13px] text-fg outline-none placeholder:text-fg-3"
          />
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-3">
        {loading && sessions.length === 0 ? (
          <div className="grid gap-4 px-4 pt-4" aria-hidden="true">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="grid gap-1.5">
                <Skeleton className="h-3 w-4/5" />
                <Skeleton className="h-2.5 w-16" />
              </div>
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <p className="m-0 px-4 pt-4 text-[12.5px] text-fg-3">
            {unavailable
              ? 'Older conversations will return when Copilot is back.'
              : 'No conversations yet. Ask Copilot to build, edit or explain a strategy.'}
          </p>
        ) : groups.length === 0 ? (
          <p className="m-0 px-4 pt-4 text-[12.5px] text-fg-3">
            No conversation titles contain &ldquo;{query.trim()}&rdquo;.
          </p>
        ) : (
          groups.map((g) => (
            <div key={g.label}>
              <div className="px-4 pb-1.5 pt-3.5 font-mono text-[11px] font-medium text-fg-3">
                {g.label}
              </div>
              {g.sessions.map((s) => {
                const on = s.id === currentId;
                return (
                  <div
                    key={s.id}
                    className={`group relative border-l-2 ${
                      on ? 'border-accent bg-sunk' : 'border-transparent hover:bg-sunk/60'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => onSelect(s.id)}
                      aria-current={on ? 'true' : undefined}
                      className="grid w-full gap-0.5 px-4 py-2 pr-10 text-left"
                    >
                      <span className="truncate font-medium text-fg">{s.title || 'Untitled'}</span>
                      <span className="text-xs text-fg-3">
                        {sessionWhen(s.lastActivityAt?.seconds)}
                      </span>
                    </button>
                    {confirming === s.id ? (
                      <div
                        role="group"
                        aria-label={`Delete ${s.title || 'this conversation'}?`}
                        className="absolute right-2 top-1.5 flex items-center gap-1 rounded-[7px] border border-line-strong bg-panel px-1.5 py-1 text-xs shadow-sm"
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') {
                            e.stopPropagation();
                            keep(s.id);
                          }
                        }}
                      >
                        <span className="text-fg-2">Delete?</span>
                        <button
                          type="button"
                          className="px-1 font-medium text-risk"
                          onClick={() => {
                            onDelete(s.id);
                            setConfirming(null);
                          }}
                        >
                          Delete
                        </button>
                        <button
                          ref={keepRef}
                          type="button"
                          className="px-1 text-fg-2"
                          onClick={() => keep(s.id)}
                        >
                          Keep
                        </button>
                      </div>
                    ) : (
                      <button
                        ref={(el) => {
                          if (el) trashRefs.current.set(s.id, el);
                          else trashRefs.current.delete(s.id);
                        }}
                        type="button"
                        onClick={() => setConfirming(s.id)}
                        aria-label={`Delete ${s.title || 'conversation'}`}
                        className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-[6px] text-fg-3 opacity-0 hover:bg-panel hover:text-fg focus:opacity-100 group-hover:opacity-100 max-md:opacity-100"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>
      {unavailable && sessions.length > 0 && (
        <p className="m-0 border-t border-line px-4 py-3 text-[12.5px] text-fg-3">
          Showing the conversations loaded before Copilot stopped responding.
        </p>
      )}
    </aside>
  );
}
