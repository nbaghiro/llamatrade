import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { ACCOUNT, signedUsd, strategyById } from '../data';

import { AskContext, useAsk, type AskApi, type ProposalState, type Turn } from './askContext';
import { InlineArtifact } from './copilot';
import { PROPOSALS } from './model';
import { Mono } from './ui';

function answer(prompt: string, context?: string): Omit<Turn, 'id' | 'role'> {
  const p = prompt.toLowerCase();
  if (/gold|safer|lower|edit|change|tweak|top 4|improve/.test(p)) {
    const id =
      context && PROPOSALS[context]
        ? context
        : /momentum|sector|top 4/.test(p)
          ? 'momentum-sectors'
          : 'recession-radar';
    const prop = PROPOSALS[id];
    const name = strategyById(id)?.name ?? '';
    return {
      text: `Here is an edit to ${name}: ${prop.note.charAt(0).toLowerCase()}${prop.note.slice(1)}. Over the same two years it gives up a little return for a smaller worst drop.`,
      artifact: 'proposal',
      strategyId: id,
    };
  }
  if (/draft|build|new|trend|make|create|write/.test(p))
    return {
      text: 'This draft holds QQQ while it closes above its 100-day average and moves to T-bills when it falls below. It checks at each close. A quick backtest is below.',
      artifact: 'draft',
    };
  if (context && strategyById(context) && !/today|down|account/.test(p)) {
    const s = strategyById(context);
    return {
      text: `${s?.name} ${s?.summary.charAt(0).toLowerCase()}${s?.summary.slice(1)} Its outline and last backtest are below.`,
      artifact: 'explain',
      strategyId: context,
    };
  }
  return {
    text: `The account is down ${signedUsd(ACCOUNT.today).slice(1)} today. All three running sessions fell, and Recession Radar lost the most as TLT and GLD slipped.`,
    artifact: 'today',
  };
}

/** Holds the conversation, the streaming reply and whether the card shows it. */
export function AskProvider({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(0);
  const [proposals, setProposals] = useState<Record<string, ProposalState>>({});
  const nextId = useRef(1);

  const ask = useCallback((prompt: string, context?: string) => {
    const q = prompt.trim();
    if (!q) return;
    const a = answer(q, context);
    const reply: Turn = { id: nextId.current + 1, role: 'copilot', ...a };
    setTurns((t) => [...t, { id: nextId.current, role: 'you', text: q }, reply]);
    nextId.current += 2;
    setOpen(true);
    if (a.artifact === 'proposal' && a.strategyId) {
      const id = a.strategyId;
      setProposals((p) => ({ ...p, [id]: 'open' }));
    }
  }, []);

  const last = turns[turns.length - 1];
  const lastId = last?.id;
  const lastLen = last?.role === 'copilot' ? last.text.length : 0;
  useEffect(() => {
    setShown(0);
    if (!lastLen) return;
    const t = window.setInterval(() => {
      setShown((s) => {
        if (s >= lastLen) {
          window.clearInterval(t);
          return s;
        }
        return Math.min(lastLen, s + 3);
      });
    }, 16);
    return () => window.clearInterval(t);
  }, [lastId, lastLen]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        document.getElementById('i-ask')?.focus();
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const api = useMemo<AskApi>(
    () => ({
      turns,
      shown,
      ask,
      open,
      setOpen,
      proposals,
      setProposal: (id, s) => setProposals((p) => ({ ...p, [id]: s })),
    }),
    [turns, shown, ask, open, proposals]
  );

  return <AskContext.Provider value={api}>{children}</AskContext.Provider>;
}

function ArrowUp() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-3.5 w-3.5">
      <path
        d="M8 13V3M3.5 7.5L8 3l4.5 4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ArrowLeft() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-3 w-3">
      <path
        d="M13 8H3M7.5 3.5L3 8l4.5 4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** The first row of every card. After a question it holds the Back control and takes follow-ups. */
export function AskRow({
  back,
  context,
  placeholder,
  suggestions = [],
}: {
  back: string;
  context?: string;
  placeholder: string;
  suggestions?: string[];
}) {
  const { ask, open, setOpen, turns } = useAsk();
  const [q, setQ] = useState('');
  const submit = (text: string) => {
    ask(text, context);
    setQ('');
  };
  const asked = turns.length / 2;
  return (
    <div className="border-b border-line">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(q);
        }}
        className="flex h-[62px] items-center gap-3 pl-5 pr-3 md:pl-7 md:pr-4"
      >
        {open ? (
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="inline-flex h-7 flex-none items-center gap-1.5 rounded-full border border-line-strong pl-2.5 pr-3 text-[12.5px] font-medium text-fg transition-colors hover:bg-sunk"
          >
            <ArrowLeft />
            {back}
          </button>
        ) : (
          <Mono className="flex-none text-fg-3">Ask</Mono>
        )}
        <input
          id="i-ask"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={open ? 'Ask a follow-up' : placeholder}
          aria-label="Ask Copilot"
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent text-[15px] text-fg outline-none placeholder:text-fg-3"
        />
        <kbd className="hidden flex-none rounded-[5px] border border-line px-1.5 py-0.5 font-mono text-[10.5px] text-fg-3 md:inline">
          ⌘K
        </kbd>
        <button
          type="submit"
          aria-label="Send"
          disabled={!q.trim()}
          className="grid h-9 w-9 flex-none place-items-center rounded-[9px] bg-fg text-canvas transition-opacity disabled:opacity-30"
        >
          <ArrowUp />
        </button>
      </form>
      {!open && (suggestions.length > 0 || asked > 0) && (
        <div className="-mt-1 flex items-center gap-1.5 overflow-x-auto px-5 pb-3.5 md:px-7">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => submit(s)}
              className="h-6 flex-none whitespace-nowrap rounded-full border border-line px-2.5 text-[12px] text-fg-2 transition-colors hover:border-line-strong hover:text-fg"
            >
              {s}
            </button>
          ))}
          {asked > 0 && (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="ml-auto h-6 flex-none whitespace-nowrap rounded-full bg-sunk px-2.5 text-[12px] font-medium text-fg"
            >
              Back to the conversation · {asked}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** The conversation, in the card in place of the page: newest exchange first, under the Ask row. */
export function Conversation() {
  const { turns, shown } = useAsk();
  const pairs = useMemo(() => {
    const out: { q: Turn; a: Turn }[] = [];
    for (let i = 0; i + 1 < turns.length; i += 2) out.push({ q: turns[i], a: turns[i + 1] });
    return out.reverse();
  }, [turns]);
  const [focus, setFocus] = useState<number | null>(null);
  const newest = pairs[0];
  useEffect(() => {
    setFocus(null);
  }, [newest?.a.id]);
  if (!newest) return null;
  const cur = pairs.find((p) => p.a.id === focus) ?? newest;
  const streaming = cur.a.id === newest.a.id;
  const text = streaming ? cur.a.text.slice(0, shown) : cur.a.text;
  const done = !streaming || shown >= cur.a.text.length;
  const earlier = pairs.filter((p) => p !== cur);

  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <span className="inline-flex items-center gap-2 text-[11px] font-medium text-fg-3">
            <Mono className="text-fg">Copilot</Mono>
            {pairs.length > 1 && <span>{`${pairs.length} questions`}</span>}
          </span>
          <h2 className="m-0 mt-1.5 text-[20px] font-semibold leading-tight tracking-[-0.015em] text-fg">
            {cur.q.text}
          </h2>
        </div>
      </div>
      <p className="m-0 mt-3 max-w-[620px] text-[14.5px] leading-[1.6] text-fg">
        {text}
        {!done && (
          <span className="ml-0.5 inline-block h-3.5 w-[6px] translate-y-0.5 animate-pulse bg-fg" />
        )}
      </p>
      <div className="mt-5 min-h-[120px]">
        {done && cur.a.artifact && (
          <div key={cur.a.id} className="animate-rise">
            <InlineArtifact turn={cur.a} />
          </div>
        )}
      </div>
      {earlier.length > 0 && (
        <div className="mt-6">
          <div className="border-b border-line pb-2 text-[11.5px] font-medium text-fg-3">
            {focus === null ? 'Earlier' : 'Other questions'}
          </div>
          {earlier.map((p) => (
            <button
              key={p.a.id}
              type="button"
              onClick={() => setFocus(p.a.id)}
              className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-b border-line py-2.5 text-left transition-colors hover:bg-sunk/50"
            >
              <span className="min-w-0">
                <span className="block truncate text-[13.5px] text-fg">{p.q.text}</span>
                <span className="block truncate text-[12px] text-fg-3">{p.a.text}</span>
              </span>
              <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-fg-3">
                Show
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
