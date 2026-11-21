import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

import { ACCOUNT, signedUsd, strategyById } from '../data';

import { AskContext, useAsk, type AskApi, type ProposalState, type Turn } from './askContext';
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
      text: 'This draft holds QQQ while it closes above its 100-day average and moves to T-bills when it falls below. It checks at each close.',
      artifact: 'draft',
    };
  if (context && strategyById(context) && !/today|down|account/.test(p)) {
    const s = strategyById(context);
    return {
      text: `${s?.name} ${s?.summary.charAt(0).toLowerCase()}${s?.summary.slice(1)} Its outline and last backtest are on the right.`,
      artifact: 'explain',
      strategyId: context,
    };
  }
  return {
    text: `The account is down ${signedUsd(ACCOUNT.today).slice(1)} today. All three running sessions fell, and Recession Radar lost the most as TLT and GLD slipped.`,
    artifact: 'today',
  };
}

/** Holds the conversation, the streaming reply and which reply's artifact is on the stage. */
export function AskProvider({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [threadOpen, setThreadOpen] = useState(false);
  const [staged, setStaged] = useState<Turn | null>(null);
  const [shown, setShown] = useState(0);
  const [proposals, setProposals] = useState<Record<string, ProposalState>>({});
  const nextId = useRef(1);
  const { pathname } = useLocation();

  const ask = useCallback(
    (prompt: string, context?: string) => {
      const q = prompt.trim();
      if (!q) return;
      const a = answer(q, context);
      const reply: Turn = { id: nextId.current + 1, role: 'copilot', ...a };
      setTurns((t) => [...t, { id: nextId.current, role: 'you', text: q }, reply]);
      nextId.current += 2;
      setThreadOpen(true);
      if (a.artifact === 'proposal' && a.strategyId) {
        setProposals((p) => ({ ...p, [a.strategyId as string]: 'open' }));
        if (pathname.startsWith(`/g/strategies/${a.strategyId}`)) {
          setStaged(null);
          return;
        }
      }
      setStaged(reply);
    },
    [pathname]
  );

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
        document.getElementById('g-ask')?.focus();
      }
      if (e.key === 'Escape') {
        setThreadOpen(false);
        setStaged(null);
      }
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
      staged,
      stage: setStaged,
      proposals,
      setProposal: (id, s) => setProposals((p) => ({ ...p, [id]: s })),
    }),
    [turns, shown, ask, threadOpen, staged, proposals]
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

/** The Ask composer at the foot of the left column, where the sign-in button sits. */
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
  return (
    <div className="grid gap-2.5">
      {!threadOpen && turns.length === 0 && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => submit(s)}
              className="h-7 rounded-full border border-line px-2.5 text-[12px] text-fg-2 transition-colors hover:border-line-strong hover:text-fg"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      {!threadOpen && turns.length > 0 && (
        <button
          type="button"
          onClick={() => setThreadOpen(true)}
          className="flex items-center justify-between rounded-[8px] border border-line px-3 py-2 text-left text-[12.5px] text-fg-2 hover:border-line-strong hover:text-fg"
        >
          <span className="truncate">{turns[turns.length - 2]?.text}</span>
          <span className="ml-3 flex-none font-mono text-[10.5px] uppercase tracking-[0.08em] text-fg-3">
            {turns.length / 2} {turns.length === 2 ? 'question' : 'questions'}
          </span>
        </button>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(q);
        }}
        className="flex h-12 items-center gap-2.5 rounded-[10px] border border-line-strong bg-canvas pl-3.5 pr-1.5 transition-colors focus-within:border-fg-3"
      >
        <Mono className="text-fg-3">Ask</Mono>
        <input
          id="g-ask"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder ?? 'Ask about your account, or describe a strategy'}
          aria-label="Ask Copilot"
          className="min-w-0 flex-1 bg-transparent text-[14px] text-fg outline-none placeholder:text-fg-3"
        />
        <button
          type="submit"
          aria-label="Send"
          className="grid h-9 w-9 flex-none place-items-center rounded-[8px] bg-fg text-canvas"
        >
          <ArrowUp />
        </button>
      </form>
    </div>
  );
}

const ARTIFACT_LABEL: Record<NonNullable<Turn['artifact']>, string> = {
  today: 'Today by session',
  proposal: 'Proposed edit',
  draft: 'New draft',
  explain: 'Outline and last backtest',
};

/** The conversation, in the left column in place of the page's essentials. */
export function Thread({ back }: { back: string }) {
  const { turns, shown, setThreadOpen, staged, stage } = useAsk();
  const end = useRef<HTMLSpanElement>(null);
  const last = turns[turns.length - 1];
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [shown, turns.length]);

  return (
    <div className="animate-rise">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-medium text-fg-3">Copilot</span>
        <button
          type="button"
          onClick={() => {
            setThreadOpen(false);
            stage(null);
          }}
          className="text-[12px] font-medium text-fg-2 underline decoration-line-strong underline-offset-4 hover:text-fg"
        >
          Back to {back}
        </button>
      </div>
      {turns.map((t) => {
        const streaming = t.id === last?.id && t.role === 'copilot';
        const text = streaming ? t.text.slice(0, shown) : t.text;
        const done = !streaming || shown >= t.text.length;
        const onStage = staged?.id === t.id;
        return (
          <div key={t.id} className="border-b border-line py-3.5 last-of-type:border-b-0">
            <Mono className={t.role === 'you' ? 'text-fg-3' : 'text-fg'}>
              {t.role === 'you' ? 'You' : 'Copilot'}
            </Mono>
            <p
              className={`m-0 mt-1.5 text-[13.5px] leading-[1.55] ${t.role === 'you' ? 'text-fg-2' : 'text-fg'}`}
            >
              {text}
              {!done && (
                <span className="ml-0.5 inline-block h-3.5 w-[6px] translate-y-0.5 animate-pulse bg-fg" />
              )}
            </p>
            {done && t.artifact && (
              <button
                type="button"
                onClick={() => stage(onStage ? null : t)}
                className={`mt-2.5 flex w-full animate-rise items-center gap-3 rounded-[8px] border px-3 py-2 text-left text-[12.5px] transition-colors ${
                  onStage
                    ? 'border-fg-3 bg-sunk text-fg'
                    : 'border-line text-fg-2 hover:border-line-strong'
                }`}
              >
                <span className="min-w-0 flex-1 truncate">
                  {ARTIFACT_LABEL[t.artifact]}
                  {t.strategyId && (
                    <span className="text-fg-3"> · {strategyById(t.strategyId)?.name}</span>
                  )}
                </span>
                <span className="flex-none font-mono text-[10.5px] uppercase tracking-[0.08em] text-fg-3">
                  {onStage
                    ? 'On the right'
                    : t.artifact === 'proposal' && !t.strategyId
                      ? ''
                      : 'Show'}
                </span>
              </button>
            )}
          </div>
        );
      })}
      <span ref={end} className="block" />
    </div>
  );
}
