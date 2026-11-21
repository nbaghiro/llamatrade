import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';

import { ACCOUNT, BACKTESTS, SESSIONS, signedUsd, STRATEGIES, strategyById } from '../data';

import { AskContext, useAsk, type AskApi, type ProposalState, type Turn } from './askContext';
import { ArtifactPanel } from './copilot';
import { PROPOSALS } from './model';
import { Inline, Mono } from './ui';

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

/** Holds the conversation, the streaming reply and whether the palette is open. */
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
      const sid = a.strategyId;
      setProposals((p) => ({ ...p, [sid]: 'open' }));
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
        setOpen((o) => !o);
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
      reset: () => setTurns([]),
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

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="grid h-[22px] min-w-[22px] place-items-center rounded-[5px] border border-line px-1.5 font-mono text-[10.5px] text-fg-3">
      {children}
    </kbd>
  );
}

/** The Ask line pinned above the card. It opens the palette in the same place. */
export function AskLine({ placeholder }: { placeholder: string }) {
  const { setOpen, turns } = useAsk();
  const lastQ = turns.length ? turns[turns.length - 2]?.text : undefined;
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-label="Ask Copilot"
      className="group flex h-12 w-full items-center gap-3 rounded-[10px] border border-line-strong bg-canvas pl-4 pr-2 text-left shadow-[0_10px_30px_-18px_rgb(0_0_0/0.35)] transition-colors hover:border-fg-3"
    >
      <Mono className="text-fg-3">Ask</Mono>
      <span className="min-w-0 flex-1 truncate text-[14px] text-fg-3 group-hover:text-fg-2">
        {lastQ ? (
          <>
            <span className="text-fg-2">{lastQ}</span>
            <span className="text-fg-3">
              {' '}
              · {turns.length / 2} {turns.length === 2 ? 'question' : 'questions'}, open to continue
            </span>
          </>
        ) : (
          placeholder
        )}
      </span>
      <span className="hidden sm:inline-flex">
        <Kbd>⌘K</Kbd>
      </span>
      <span className="grid h-8 w-8 flex-none place-items-center rounded-[8px] bg-fg text-canvas">
        <ArrowUp />
      </span>
    </button>
  );
}

interface Jump {
  label: string;
  kind: string;
  to: string;
}

const JUMPS: Jump[] = [
  ...STRATEGIES.map((s) => ({ label: s.name, kind: 'Strategy', to: `/k/strategies/${s.id}` })),
  ...SESSIONS.map((s) => ({
    label: `${strategyById(s.strategyId)?.name ?? ''} session`,
    kind: s.mode === 'live' ? 'Live' : 'Paper',
    to: `/k/sessions/${s.id}`,
  })),
  ...BACKTESTS.map((b) => ({
    label: `${strategyById(b.strategyId)?.name ?? ''} v${b.version} backtest`,
    kind: 'Backtest',
    to: `/k/backtests/${b.id}`,
  })),
  { label: 'Holdings by asset class', kind: 'Portfolio', to: '/k/portfolio?v=all' },
];

function PaletteInput({
  value,
  onChange,
  onSubmit,
  placeholder,
  big,
  onKeyDown,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  placeholder: string;
  big?: boolean;
  onKeyDown?: (e: ReactKeyboardEvent<HTMLInputElement>) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className={`flex items-center gap-3 pl-5 pr-2.5 ${big ? 'h-14' : 'h-12 rounded-[10px] border border-line-strong bg-canvas focus-within:border-fg-3'}`}
    >
      <Mono className="text-fg-3">Ask</Mono>
      <input
        id="k-ask"
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        aria-label="Ask Copilot"
        autoComplete="off"
        className={`min-w-0 flex-1 bg-transparent text-fg outline-none placeholder:text-fg-3 ${big ? 'text-[16px]' : 'text-[14px]'}`}
      />
      <button
        type="submit"
        aria-label="Send"
        className="grid h-8 w-8 flex-none place-items-center rounded-[8px] bg-fg text-canvas"
      >
        <ArrowUp />
      </button>
    </form>
  );
}

function Row({
  on,
  onClick,
  left,
  right,
}: {
  on: boolean;
  onClick: () => void;
  left: ReactNode;
  right?: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-3 rounded-[8px] px-3 py-2 text-left text-[13.5px] transition-colors ${
        on ? 'bg-sunk text-fg' : 'text-fg-2 hover:bg-sunk/60 hover:text-fg'
      }`}
    >
      <span className="min-w-0 truncate">{left}</span>
      {right && <span className="flex-none">{right}</span>}
    </button>
  );
}

/** First state of the palette: questions to ask and places to go, filtered as you type. */
function Commands({
  context,
  placeholder,
  suggestions,
}: {
  context?: string;
  placeholder: string;
  suggestions: string[];
}) {
  const { ask, setOpen } = useAsk();
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [cursor, setCursor] = useState(0);
  const needle = q.trim().toLowerCase();
  const asks = needle ? [q.trim()] : suggestions;
  const jumps = (
    needle ? JUMPS.filter((j) => j.label.toLowerCase().includes(needle)) : JUMPS.slice(0, 4)
  ).slice(0, 5);
  const total = asks.length + jumps.length;
  const run = (i: number) => {
    if (i < asks.length) {
      ask(asks[i], context);
      return;
    }
    const j = jumps[i - asks.length];
    if (!j) return;
    setOpen(false);
    nav(j.to);
  };
  return (
    <>
      <PaletteInput
        big
        value={q}
        onChange={(v) => {
          setQ(v);
          setCursor(0);
        }}
        onSubmit={() => run(cursor)}
        placeholder={placeholder}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setCursor((c) => (c + 1) % Math.max(1, total));
          }
          if (e.key === 'ArrowUp') {
            e.preventDefault();
            setCursor((c) => (c - 1 + total) % Math.max(1, total));
          }
        }}
      />
      <div className="grid gap-4 border-t border-line px-2.5 pb-3 pt-3">
        <div>
          <div className="px-3 pb-1.5 text-[11px] font-medium text-fg-3">
            {needle ? 'Ask Copilot' : 'Suggested'}
          </div>
          {asks.map((a, i) => (
            <Row
              key={a}
              on={cursor === i}
              onClick={() => run(i)}
              left={a}
              right={cursor === i ? <Kbd>↵</Kbd> : undefined}
            />
          ))}
        </div>
        {jumps.length > 0 && (
          <div>
            <div className="px-3 pb-1.5 text-[11px] font-medium text-fg-3">Go to</div>
            {jumps.map((j, i) => (
              <Row
                key={j.to}
                on={cursor === asks.length + i}
                onClick={() => run(asks.length + i)}
                left={j.label}
                right={<Mono className="text-fg-3">{j.kind}</Mono>}
              />
            ))}
          </div>
        )}
      </div>
      <div className="flex items-center gap-4 border-t border-line px-5 py-2.5 text-[11.5px] text-fg-3">
        <span className="inline-flex items-center gap-1.5">
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd> to move
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Kbd>↵</Kbd> to ask or open
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5">
          <Kbd>esc</Kbd> to close
        </span>
      </div>
    </>
  );
}

/** The palette once something is asked: the conversation, with what Copilot made inline. */
function Conversation({ context, back }: { context?: string; back: string }) {
  const { turns, shown, ask, setOpen, reset } = useAsk();
  const [q, setQ] = useState('');
  const end = useRef<HTMLDivElement>(null);
  const last = turns[turns.length - 1];
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' });
  }, [turns.length]);

  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <span className="inline-flex items-center gap-2.5">
          <Mono className="text-fg">Copilot</Mono>
          <span className="text-[12px] text-fg-3">
            {turns.length / 2} {turns.length === 2 ? 'question' : 'questions'}
          </span>
        </span>
        <span className="flex items-center gap-1">
          <button
            type="button"
            onClick={reset}
            className="h-7 rounded-full px-3 text-[12.5px] text-fg-3 hover:bg-sunk hover:text-fg"
          >
            New question
          </button>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="inline-flex h-7 items-center gap-2 rounded-full border border-line-strong px-3 text-[12.5px] font-medium text-fg hover:border-fg-3"
          >
            Back to {back}
            <Kbd>esc</Kbd>
          </button>
        </span>
      </div>
      <div className="px-5 md:px-7">
        {turns.map((t) => {
          const streaming = t.id === last?.id && t.role === 'copilot';
          const text = streaming ? t.text.slice(0, shown) : t.text;
          const done = !streaming || shown >= t.text.length;
          if (t.role === 'you')
            return (
              <div key={t.id} className="flex justify-end pt-5">
                <p className="m-0 max-w-[80%] rounded-[10px] bg-sunk px-3.5 py-2 text-[13.5px] text-fg">
                  {t.text}
                </p>
              </div>
            );
          return (
            <div key={t.id} className="pt-4">
              <p className="m-0 max-w-[640px] text-[14px] leading-[1.6] text-fg">
                {text}
                {!done && (
                  <span className="ml-0.5 inline-block h-3.5 w-[6px] translate-y-0.5 animate-pulse bg-fg" />
                )}
              </p>
              {done && t.artifact && (
                <div className="mt-4 animate-rise">
                  <Inline>
                    <ArtifactPanel turn={t} />
                  </Inline>
                </div>
              )}
            </div>
          );
        })}
        <div ref={end} className="h-5" />
      </div>
      <div className="border-t border-line px-5 py-3.5 md:px-7">
        <PaletteInput
          value={q}
          onChange={setQ}
          onSubmit={() => {
            ask(q, context);
            setQ('');
          }}
          placeholder="Ask a follow-up"
        />
      </div>
    </>
  );
}

/** ⌘K palette, centred over the card. It turns into the conversation in place. */
export function Palette({
  context,
  placeholder,
  suggestions,
  back,
}: {
  context?: string;
  placeholder: string;
  suggestions: string[];
  back: string;
}) {
  const { open, turns } = useAsk();
  if (!open) return null;
  return (
    <section
      role="dialog"
      aria-label="Ask Copilot"
      className="auth-card k-pop relative w-full overflow-hidden rounded-[14px] border bg-canvas"
    >
      {turns.length === 0 ? (
        <Commands context={context} placeholder={placeholder} suggestions={suggestions} />
      ) : (
        <Conversation context={context} back={back} />
      )}
    </section>
  );
}
