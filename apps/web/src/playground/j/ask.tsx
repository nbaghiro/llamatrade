import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { ACCOUNT, signedUsd, strategyById } from '../data';

import { AskContext, useAsk, type AskApi, type ProposalState, type Turn } from './askContext';
import { ArtifactBlock } from './copilot';
import { PROPOSALS } from './model';
import { Button, Mono, PanelHead, StageCard } from './ui';

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
      text: 'This draft holds QQQ while it closes above its 100-day average and moves to T-bills when it falls below. It checks at each close.',
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

/** Holds the conversation, the streaming reply and the state of Copilot's proposed edits. */
export function AskProvider({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [threadOpen, setThreadOpen] = useState(false);
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
    setThreadOpen(true);
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
        document.getElementById('j-ask')?.focus();
      }
      if (e.key === 'Escape') setThreadOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const api = useMemo<AskApi>(
    () => ({
      turns,
      shown,
      ask,
      threadOpen,
      setThreadOpen,
      proposals,
      setProposal: (id, s) => setProposals((p) => ({ ...p, [id]: s })),
    }),
    [turns, shown, ask, threadOpen, proposals]
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

const CHIP =
  'h-7 flex-none whitespace-nowrap rounded-full border border-line-strong bg-canvas px-3 text-[12px] text-fg-2 transition-colors hover:border-fg-3 hover:text-fg';

/** The composer docked under the card, with a few suggestions above it. */
export function Composer({
  context,
  placeholder,
  suggestions = [],
}: {
  context?: string;
  placeholder?: string;
  suggestions?: string[];
}) {
  const { ask, threadOpen, setThreadOpen, turns } = useAsk();
  const [q, setQ] = useState('');
  const submit = (text: string) => {
    ask(text, context);
    setQ('');
  };
  const asked = new Set(turns.filter((t) => t.role === 'you').map((t) => t.text));
  const chips = suggestions.filter((s) => !asked.has(s)).slice(0, 3);
  const questions = turns.length / 2;
  return (
    <div className="pointer-events-auto grid gap-2.5">
      <div className="flex items-center gap-1.5 overflow-x-auto [scrollbar-width:none]">
        {!threadOpen && questions > 0 && (
          <button
            type="button"
            onClick={() => setThreadOpen(true)}
            className={`${CHIP} inline-flex items-center gap-2 text-fg`}
          >
            <Mono className="text-fg-3">Copilot</Mono>
            Back to the conversation · {questions}
          </button>
        )}
        {chips.map((s) => (
          <button key={s} type="button" onClick={() => submit(s)} className={CHIP}>
            {s}
          </button>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(q);
        }}
        className="flex h-14 items-center gap-3 rounded-[12px] border border-line-strong bg-canvas pl-4 pr-2 shadow-[0_24px_60px_-28px_rgb(0_0_0/0.5)] transition-colors focus-within:border-fg-3"
      >
        <Mono className="text-fg-3">Ask</Mono>
        <input
          id="j-ask"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={
            threadOpen ? 'Ask a follow-up' : (placeholder ?? 'Ask, or describe a strategy')
          }
          aria-label="Ask Copilot"
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent text-[15px] text-fg outline-none placeholder:text-fg-3"
        />
        <kbd className="hidden rounded-[4px] border border-line px-1.5 font-mono text-[10.5px] leading-[18px] text-fg-3 md:block">
          ⌘K
        </kbd>
        <button
          type="submit"
          aria-label="Send"
          className="grid h-10 w-10 flex-none place-items-center rounded-[9px] bg-fg text-canvas"
        >
          <ArrowUp />
        </button>
      </form>
    </div>
  );
}

/** The conversation as a tall card in the page's place, each reply with what it made under it. */
export function Conversation({ back }: { back: string }) {
  const { turns, shown, setThreadOpen } = useAsk();
  const latest = useRef<HTMLDivElement>(null);
  const last = turns[turns.length - 1];
  useEffect(() => {
    if (turns.length > 2) latest.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [turns.length]);
  const questions = turns.length / 2;

  return (
    <StageCard>
      <div className="flex min-h-[calc(100vh-310px)] flex-col">
        <PanelHead
          eyebrow="Copilot"
          title="Conversation"
          meta={`${questions} ${questions === 1 ? 'question' : 'questions'} · Esc returns to ${back}`}
          right={
            <Button onClick={() => setThreadOpen(false)} aria-label={`Back to ${back}`}>
              ← Back to {back}
            </Button>
          }
        />
        <div className="mt-[18px] border-t border-line">
          {turns.map((t) => {
            const streaming = t.id === last?.id && t.role === 'copilot';
            const text = streaming ? t.text.slice(0, shown) : t.text;
            const done = !streaming || shown >= t.text.length;
            if (t.role === 'you')
              return (
                <div
                  key={t.id}
                  ref={t.id === last.id - 1 ? latest : undefined}
                  className="flex scroll-mt-[76px] justify-end pt-5"
                >
                  <p className="m-0 max-w-[80%] rounded-[12px] bg-sunk px-3.5 py-2 text-[13.5px] leading-[1.5] text-fg">
                    {t.text}
                  </p>
                </div>
              );
            return (
              <div key={t.id} className="border-b border-line pb-5 pt-3 last:border-b-0">
                <Mono className="text-fg">Copilot</Mono>
                <p className="m-0 mt-2 max-w-[600px] text-[14px] leading-[1.6] text-fg">
                  {text}
                  {!done && (
                    <span className="ml-0.5 inline-block h-3.5 w-[6px] translate-y-0.5 animate-pulse bg-fg" />
                  )}
                </p>
                {done && t.artifact && (
                  <div className="mt-4 animate-rise">
                    <ArtifactBlock turn={t} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </StageCard>
  );
}
