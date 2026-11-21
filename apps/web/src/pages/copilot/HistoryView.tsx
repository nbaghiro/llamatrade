import { sessionWhen } from '@llamatrade/core/agent/history';
import { MessageRole, type AgentMessage, type AgentSession } from '@llamatrade/core/stores/agent';
import { ArrowLeft, Plus, Search, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  answerObjects,
  objectText,
  resultPicture,
  type AnswerObject,
  type ResultPicture,
} from '../../components/agent/answerObjects';
import { UserBubble } from '../../components/agent/ChatMessage';
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
import { CitationMark } from '../../components/agent/SourceMarks';
import { threadSources } from '../../components/agent/sources';
import { SEARCH_DEPTH, useConversationIndex } from '../../components/agent/useConversationIndex';
import { CopilotMark } from '../../components/common/Logo';
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

const PCT = (w: number) => `${(w * 100).toFixed(1)}%`;

/** The small picture beside a result: the holdings or symbols the conversation read. */
function Picture({ picture, query }: { picture: ResultPicture; query: string }) {
  const q = query.trim().toLowerCase();
  return (
    <span
      aria-hidden="true"
      className="grid h-10 w-16 flex-none place-items-center overflow-hidden rounded-[7px] border border-line bg-panel px-1.5"
    >
      {picture.kind === 'holdings' ? (
        <span className="grid w-full gap-[3px]">
          {picture.rows.map((r) => (
            <span key={r.symbol} className="flex items-center gap-1">
              <span
                className={`w-6 font-mono text-[8.5px] ${q && r.symbol.toLowerCase().includes(q) ? 'text-accent' : 'text-fg-3'}`}
              >
                {r.symbol}
              </span>
              <span className="h-[3px] flex-1 rounded-full bg-sunk">
                <i
                  className="block h-full rounded-full bg-accent/70"
                  style={{ width: `${Math.max(6, r.weight * 100)}%` }}
                />
              </span>
            </span>
          ))}
        </span>
      ) : picture.kind === 'symbols' ? (
        <span className="truncate font-mono text-[10px] text-fg-2">
          {picture.symbols.map((sym, i) => (
            <span
              key={sym}
              className={q && sym.toLowerCase().includes(q) ? 'font-semibold text-accent' : ''}
            >
              {i > 0 ? ' · ' : ''}
              {sym}
            </span>
          ))}
        </span>
      ) : (
        <CopilotMark className="h-4 w-4 text-fg-3" />
      )}
    </span>
  );
}

function MatchTag() {
  return (
    <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-accent">
      Match
    </span>
  );
}

/** A record the answer read, drawn as a card; the one matching the search is outlined. */
function ObjectCard({ object, query }: { object: AnswerObject; query: string }) {
  const q = query.trim().toLowerCase();
  const hit = q !== '' && objectText(object).toLowerCase().includes(q);
  const frame = `grid gap-2.5 rounded-[10px] border bg-panel px-3.5 py-3 ${
    hit ? 'border-accent/45 shadow-[0_0_0_3px_var(--accent-soft)]' : 'border-line'
  }`;
  if (object.kind === 'holdings') {
    return (
      <div className={frame}>
        <div className="flex items-center gap-2">
          <b className="text-[13px] font-semibold">Positions</b>
          <CitationMark n={object.n} />
          <span className="text-[12px] text-fg-3">across your account</span>
          <span className="flex-1" />
          {hit && <MatchTag />}
        </div>
        <div className="grid gap-1.5">
          {object.rows.map((r) => {
            const on = q !== '' && r.symbol.toLowerCase().includes(q);
            return (
              <div
                key={r.symbol}
                className="grid grid-cols-[52px_minmax(0,1fr)_56px] items-center gap-3 text-[12.5px]"
              >
                <span className={`font-mono ${on ? 'font-semibold text-fg' : 'text-fg-2'}`}>
                  {on ? <Marked text={r.symbol} query={query} /> : r.symbol}
                </span>
                <span className="h-1.5 rounded-full bg-sunk">
                  <i
                    className={`block h-full rounded-full ${on ? 'bg-accent' : 'bg-fg-3/45'}`}
                    style={{ width: `${Math.max(2, r.weight * 100)}%` }}
                  />
                </span>
                <span className="num text-right text-fg-2">{PCT(r.weight)}</span>
              </div>
            );
          })}
        </div>
        {object.more > 0 && (
          <span className="text-[12px] text-fg-3">
            {object.more} more {object.more === 1 ? 'position' : 'positions'}
          </span>
        )}
      </div>
    );
  }
  if (object.kind === 'strategy') {
    return (
      <div className={frame}>
        <div className="flex flex-wrap items-center gap-2">
          <b className="text-[13px] font-semibold">
            <Marked text={object.name} query={query} />
          </b>
          {object.version && (
            <span className="text-[12px] text-fg-3">version {object.version}</span>
          )}
          <CitationMark n={object.n} />
          <span className="flex-1" />
          {hit && <MatchTag />}
          {object.href && (
            <Link to={object.href} className="text-[12.5px] text-accent hover:underline">
              Open
            </Link>
          )}
        </div>
        {object.symbols.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {object.symbols.map((sym) => (
              <span
                key={sym}
                className="rounded-[5px] border border-line px-1.5 py-0.5 font-mono text-[11.5px] text-fg-2"
              >
                <Marked text={sym} query={query} />
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }
  return (
    <div className={frame}>
      <div className="flex items-center gap-2">
        <b className="text-[13px] font-semibold">{object.title}</b>
        <CitationMark n={object.n} />
        <span className="flex-1" />
        {hit && <MatchTag />}
        {object.href && (
          <Link to={object.href} className="text-[12.5px] text-accent hover:underline">
            Open
          </Link>
        )}
      </div>
      <dl className="m-0 grid grid-cols-2 gap-x-4 gap-y-1 text-[12.5px]">
        {object.figures.map((f) => (
          <div key={f.label} className="flex justify-between gap-2">
            <dt className="text-fg-3">{f.label}</dt>
            <dd className="num m-0">{f.value}</dd>
          </div>
        ))}
      </dl>
    </div>
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
  const sources = useMemo(() => threadSources(messages ?? []), [messages]);
  const firstOf = (id: string) => sources.find((s) => s.messageId === id)?.n ?? 1;

  return (
    <section aria-label={session.title || 'Conversation'} className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-none items-center justify-between gap-3 border-b border-line px-6 py-3.5">
        <div className="flex min-w-0 items-baseline gap-2.5">
          <b className="truncate text-[14px] font-semibold">{session.title || 'Untitled'}</b>
          <span className="flex-none text-[12px] text-fg-3">
            {sessionWhen(session.lastActivityAt?.seconds)}
          </span>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onContinue}>
          Continue
        </button>
      </div>
      <div ref={ref} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-[600px] gap-5 px-6 py-6">
          {!messages ? (
            <div className="grid gap-3">
              <Skeleton className="ml-auto h-9 w-1/2" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            messages.map((m) => {
              if (m.role === MessageRole.USER) return <UserBubble key={m.id} text={m.content} />;
              const mine = sources.filter((s) => s.messageId === m.id);
              const objects = answerObjects(m, firstOf(m.id));
              return (
                <div key={m.id} className="grid gap-2.5 text-[14px] leading-[1.6]">
                  <span className="flex items-center gap-1.5 font-mono text-[11px] text-fg-3">
                    <CopilotMark className="h-3.5 w-3.5 text-fg-2" />
                    Copilot
                    {mine.length > 0 &&
                      ` · ${mine.length} ${mine.length === 1 ? 'source' : 'sources'}`}
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
                  {objects.map((o) => (
                    <ObjectCard key={`${o.kind}-${o.n}`} object={o} query={query} />
                  ))}
                  {mine.length > 0 && (
                    <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-[12px] text-fg-3">
                      {mine.map((s) => (
                        <span key={s.n} className="inline-flex items-center gap-1.5">
                          <CitationMark n={s.n} />
                          {s.href ? (
                            <Link to={s.href} className="hover:text-accent">
                              {s.title}
                            </Link>
                          ) : (
                            s.title
                          )}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })
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
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
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
                <div key={s.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => setSelected(s.id)}
                    aria-current={on ? 'true' : undefined}
                    className={`flex w-full items-start gap-3 rounded-[10px] px-2.5 py-3 pr-8 text-left ${on ? 'bg-sunk' : 'hover:bg-sunk/60'}`}
                  >
                    {messages && <Picture picture={resultPicture(messages)} query={query} />}
                    <span className="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)] gap-1">
                      <span className="flex min-w-0 items-baseline justify-between gap-3">
                        <b className="truncate text-[13.5px] font-semibold">
                          {s.title || 'Untitled'}
                        </b>
                        <span className="flex-none font-mono text-[11.5px] text-fg-3">
                          {sessionWhen(s.lastActivityAt?.seconds)}
                        </span>
                      </span>
                      {hit && hit.paragraph >= 0 && (
                        <span className="line-clamp-2 text-[13px] leading-[1.5] text-fg-2">
                          <Marked text={hit.text} query={query} />
                        </span>
                      )}
                      {messages && outcomeLabel(messages) && (
                        <span className="text-[12px] text-fg-3">{outcomeLabel(messages)}</span>
                      )}
                    </span>
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
