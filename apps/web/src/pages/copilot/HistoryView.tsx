import { sessionWhen } from '@llamatrade/core/agent/history';
import { MessageRole, type AgentMessage, type AgentSession } from '@llamatrade/core/stores/agent';
import { ArrowLeft, Plus, Search, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import {
  conversationKinds,
  highlight,
  KIND_LABEL,
  outcomeLabel,
  paragraphs,
  searchConversation,
  type ConversationKind,
  type SearchHit,
} from '../../components/agent/historySearch';
import { SEARCH_DEPTH, useConversationIndex } from '../../components/agent/useConversationIndex';
import { Skeleton } from '../../components/ui';

type Filter = 'all' | ConversationKind;
const FILTERS: Filter[] = ['all', 'explained', 'drafts', 'backtests'];

function Marked({ text, query }: { text: string; query: string }) {
  return (
    <>
      {highlight(text, query).map((p, i) =>
        p.match ? (
          <mark key={i} className="rounded-[2px] bg-accent/25 text-fg">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        )
      )}
    </>
  );
}

function Reading({
  session,
  messages,
  hit,
  query,
  onContinue,
}: {
  session: AgentSession;
  messages: readonly AgentMessage[] | undefined;
  hit: SearchHit | null;
  query: string;
  onContinue: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector('[data-hit]')?.scrollIntoView({ block: 'center' });
  }, [hit, messages]);

  return (
    <section aria-label={session.title || 'Conversation'} className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-none items-center justify-between gap-3 border-b border-line px-6 py-4">
        <div className="flex min-w-0 items-baseline gap-2.5">
          <b className="truncate text-[14.5px] font-semibold">{session.title || 'Untitled'}</b>
          <span className="flex-none text-[12px] text-fg-3">
            {sessionWhen(session.lastActivityAt?.seconds)}
          </span>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onContinue}>
          Continue
        </button>
      </div>
      <div ref={ref} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-[640px] gap-5 px-6 py-7">
          {!messages ? (
            <div className="grid gap-3">
              <Skeleton className="ml-auto h-9 w-1/2" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            messages.map((m) =>
              m.role === MessageRole.USER ? (
                <div key={m.id} className="grid justify-items-end">
                  <div className="max-w-[80%] whitespace-pre-wrap rounded-[10px] bg-fg px-3.5 py-2.5 text-[14px] text-canvas">
                    {m.content}
                  </div>
                </div>
              ) : (
                <div key={m.id} className="grid gap-2 text-[14px] leading-[1.6]">
                  <span className="font-mono text-[11px] text-fg-3">
                    Copilot
                    {m.toolCalls.length > 0 &&
                      ` · ${m.toolCalls.length} ${m.toolCalls.length === 1 ? 'source' : 'sources'}`}
                  </span>
                  {paragraphs(m.content).map((p, i) => {
                    const on = hit?.messageId === m.id && hit.paragraph === i;
                    return (
                      <p
                        key={i}
                        data-hit={on ? '' : undefined}
                        className={`m-0 whitespace-pre-wrap ${on ? '-mx-2.5 rounded-[7px] bg-accent-soft px-2.5 py-1.5' : ''}`}
                      >
                        {on ? <Marked text={p} query={query} /> : p}
                      </p>
                    );
                  })}
                </div>
              )
            )
          )}
        </div>
      </div>
    </section>
  );
}

/** Earlier conversations, searched by what was said (history2 A). */
export function HistoryView({
  sessions,
  loading,
  initialQuery,
  onQuery,
  onOpen,
  onNew,
  onDelete,
  onBack,
}: {
  sessions: readonly AgentSession[];
  loading: boolean;
  initialQuery: string;
  onQuery: (q: string) => void;
  onOpen: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onBack: () => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const { index, loading: indexing } = useConversationIndex(sessions, true);

  const results = useMemo(() => {
    const sorted = [...sessions].sort((a, b) =>
      Number((b.lastActivityAt?.seconds ?? 0n) - (a.lastActivityAt?.seconds ?? 0n))
    );
    return sorted
      .map((s) => {
        const messages = index[s.id];
        const hit = query.trim()
          ? searchConversation({ id: s.id, title: s.title, messages: messages ?? [] }, query)
          : null;
        return { session: s, messages, hit };
      })
      .filter((r) => !query.trim() || r.hit)
      .filter(
        (r) => filter === 'all' || (r.messages && conversationKinds(r.messages).includes(filter))
      );
  }, [sessions, index, query, filter]);

  const current = results.find((r) => r.session.id === selected) ?? results[0] ?? null;
  const answers = results.filter((r) => r.hit && r.hit.paragraph >= 0).length;

  const changeQuery = (q: string) => {
    setQuery(q);
    onQuery(q);
  };

  return (
    <div className="flex min-h-0 flex-1">
      <section
        aria-label="Conversations"
        className={`flex min-h-0 w-full flex-none flex-col border-r border-line bg-panel md:w-[480px] ${current && selected ? 'max-md:hidden' : ''}`}
      >
        <div className="grid gap-3 px-5 pb-3 pt-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                className="btn btn-ghost px-1.5"
                aria-label="Back to Copilot"
                onClick={onBack}
              >
                <ArrowLeft className="h-4 w-4" />
              </button>
              <h1 className="m-0 text-[20px] font-semibold tracking-[-0.02em]">Conversations</h1>
            </div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={onNew}>
              <Plus className="h-3.5 w-3.5" />
              New
            </button>
          </div>
          <label className="flex h-10 items-center gap-2 rounded-[9px] border border-line-strong bg-panel px-3 text-fg-3 focus-within:border-accent">
            <Search className="h-4 w-4 flex-none" />
            <span className="sr-only">Search what was said</span>
            <input
              type="search"
              value={query}
              autoFocus
              onChange={(e) => changeQuery(e.target.value)}
              placeholder="Search what was said"
              className="min-w-0 flex-1 bg-transparent text-[14px] text-fg outline-none placeholder:text-fg-3"
            />
            {query.trim() && (
              <span className="num flex-none text-[12px]">
                {answers} {answers === 1 ? 'answer' : 'answers'}
              </span>
            )}
          </label>
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Show">
            {FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                role="radio"
                aria-checked={filter === f}
                onClick={() => setFilter(f)}
                className={`h-8 rounded-full border px-3 text-[13px] ${
                  filter === f
                    ? 'border-accent/50 bg-accent-soft text-fg'
                    : 'border-line-strong text-fg-2'
                }`}
              >
                {f === 'all' ? 'All' : KIND_LABEL[f]}
              </button>
            ))}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">
          {loading && sessions.length === 0 ? (
            <div className="grid gap-4 pt-2" aria-hidden="true">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <p className="m-0 pt-2 text-[13px] text-fg-3">
              No conversations yet. Ask Copilot to build, edit or explain a strategy.
            </p>
          ) : results.length === 0 ? (
            <p className="m-0 pt-2 text-[13px] text-fg-3">
              {indexing
                ? 'Searching your conversations.'
                : query.trim()
                  ? `Nothing in your last ${Math.min(SEARCH_DEPTH, sessions.length)} conversations mentions “${query.trim()}”.`
                  : 'No conversations of this kind yet.'}
            </p>
          ) : (
            results.map(({ session: s, messages, hit }) => {
              const on = current?.session.id === s.id;
              return (
                <div key={s.id} className="group relative border-b border-line">
                  <button
                    type="button"
                    onClick={() => setSelected(s.id)}
                    aria-current={on ? 'true' : undefined}
                    className={`grid w-full gap-1.5 py-3.5 pr-8 text-left ${on ? '' : 'opacity-90 hover:opacity-100'}`}
                  >
                    <span className="flex items-baseline justify-between gap-3">
                      <b
                        className={`truncate text-[13.5px] font-semibold ${on ? 'text-accent' : ''}`}
                      >
                        {s.title || 'Untitled'}
                      </b>
                      <span className="flex-none font-mono text-[11.5px] text-fg-3">
                        {sessionWhen(s.lastActivityAt?.seconds)}
                      </span>
                    </span>
                    {hit && hit.paragraph >= 0 && (
                      <span
                        className={`line-clamp-3 border-l-2 pl-3 text-[13px] leading-[1.55] text-fg-2 ${on ? 'border-accent' : 'border-line-strong'}`}
                      >
                        <Marked text={hit.text} query={query} />
                      </span>
                    )}
                    {messages && outcomeLabel(messages) && (
                      <span className="text-[12px] text-fg-3">{outcomeLabel(messages)}</span>
                    )}
                  </button>
                  {confirming === s.id ? (
                    <span className="absolute right-0 top-3 flex items-center gap-1 rounded-[7px] border border-line-strong bg-panel px-1.5 py-1 text-xs shadow-sm">
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
                        type="button"
                        className="px-1 text-fg-2"
                        onClick={() => setConfirming(null)}
                      >
                        Keep
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirming(s.id)}
                      aria-label={`Delete ${s.title || 'conversation'}`}
                      className="absolute right-0 top-3 grid h-6 w-6 place-items-center rounded-[6px] text-fg-3 opacity-0 hover:text-fg focus:opacity-100 group-hover:opacity-100 max-md:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              );
            })
          )}
          {query.trim() && sessions.length > SEARCH_DEPTH && (
            <p className="m-0 pt-3 text-[12px] text-fg-3">
              Search reads your last {SEARCH_DEPTH} conversations. Older ones match by title.
            </p>
          )}
        </div>
      </section>
      {current ? (
        <div className={`min-w-0 flex-1 flex-col ${selected ? 'flex' : 'hidden md:flex'}`}>
          {selected && (
            <button
              type="button"
              className="btn btn-ghost m-2 self-start md:hidden"
              onClick={() => setSelected(null)}
            >
              <ArrowLeft className="h-4 w-4" />
              Results
            </button>
          )}
          <Reading
            session={current.session}
            messages={current.messages}
            hit={current.hit}
            query={query}
            onContinue={() => onOpen(current.session.id)}
          />
        </div>
      ) : (
        <div className="hidden flex-1 md:block" />
      )}
    </div>
  );
}
