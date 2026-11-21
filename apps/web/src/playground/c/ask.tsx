import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { ACCOUNT, pct, SESSIONS, signedUsd, strategyById, type Strategy } from '../data';

import { AskContext, useAsk, type AskApi, type ProposalState } from './askContext';
import { lastBacktest, PROPOSALS, pts, sessionWindow, tone } from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf } from './outlineModel';
import { Button, Delta, Figure, Figures, ModeTag, Mono, Spark } from './ui';

type Artifact = 'today' | 'proposal' | 'draft' | 'explain';

interface Turn {
  id: number;
  role: 'you' | 'copilot';
  text: string;
  artifact?: Artifact;
  strategyId?: string;
}

const DRAFT: Strategy = {
  id: 'qqq-trend',
  name: 'QQQ Trend',
  state: 'draft',
  version: 1,
  cadence: 'daily',
  summary: 'Holds QQQ above its 100-day average, T-bills below it.',
  seed: 83,
  versions: [],
  rules: [
    {
      parts: [
        'If',
        { kind: 'symbol', text: 'QQQ' },
        'closes above its',
        { kind: 'number', text: '100-day' },
        'average',
      ],
      funds: [{ symbol: 'QQQ', weight: '100%' }],
    },
    {
      parts: ['Otherwise hold', { kind: 'symbol', text: 'BIL' }],
      funds: [{ symbol: 'BIL', weight: '100%' }],
    },
  ],
};

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
      text: `Here is an edit to ${name}. ${prop.note}. In a backtest over the same two years it gives up a little return for a smaller worst drop.`,
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
      text: `${s?.name} ${s?.summary.charAt(0).toLowerCase()}${s?.summary.slice(1)} The outline and its last backtest are below.`,
      artifact: 'explain',
      strategyId: context,
    };
  }
  return {
    text: `The account is down ${signedUsd(ACCOUNT.today).slice(1)} today. All three running sessions fell, and Recession Radar lost the most as TLT and GLD slipped.`,
    artifact: 'today',
  };
}

export function AskProvider({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [open, setOpen] = useState(false);
  const [top, setTop] = useState(80);
  const [proposals, setProposals] = useState<Record<string, ProposalState>>({});
  const anchor = useRef<HTMLElement | null>(null);
  const nextId = useRef(1);

  const measure = useCallback(() => {
    const r = anchor.current?.getBoundingClientRect();
    setTop(Math.max(68, Math.min(r?.top ?? 80, 220)));
  }, []);

  const ask = useCallback(
    (prompt: string, context?: string) => {
      const q = prompt.trim();
      if (!q) return;
      measure();
      const a = answer(q, context);
      setTurns((t) => [
        ...t,
        { id: nextId.current++, role: 'you', text: q },
        { id: nextId.current++, role: 'copilot', ...a },
      ]);
      setOpen(true);
    },
    [measure]
  );

  const api = useMemo<AskApi>(
    () => ({
      ask,
      openSheet: () => {
        measure();
        setOpen(true);
      },
      register: (el) => {
        anchor.current = el;
      },
      proposals,
      setProposal: (id, s) => setProposals((p) => ({ ...p, [id]: s })),
    }),
    [ask, measure, proposals]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        measure();
        setOpen(true);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [measure]);

  return (
    <AskContext.Provider value={api}>
      {children}
      {open && <Sheet top={top} turns={turns} onClose={() => setOpen(false)} />}
    </AskContext.Provider>
  );
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

/** The Ask line at the top of every page; large and first on Today. */
export function AskLine({
  size = 'sm',
  context,
  placeholder,
  suggestions = [],
}: {
  size?: 'lg' | 'sm';
  context?: string;
  placeholder?: string;
  suggestions?: string[];
}) {
  const { ask, register } = useAsk();
  const [q, setQ] = useState('');
  const lg = size === 'lg';
  const submit = (text: string) => {
    ask(text, context);
    setQ('');
  };
  return (
    <div ref={register}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(q);
        }}
        className={`group flex items-center gap-3 border border-line-strong bg-canvas transition-colors focus-within:border-fg-3 ${
          lg ? 'h-[60px] rounded-[14px] pl-5 pr-2.5' : 'h-11 rounded-full pl-4 pr-1.5'
        }`}
      >
        <Mono className="text-fg-3">Ask</Mono>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder ?? 'Ask about your account, or describe a strategy'}
          aria-label="Ask Copilot"
          className={`min-w-0 flex-1 bg-transparent text-fg outline-none placeholder:text-fg-3 ${
            lg ? 'text-[18px] tracking-[-0.01em]' : 'text-[14px]'
          }`}
        />
        <kbd className="hidden rounded-[4px] border border-line px-1.5 font-mono text-[10.5px] leading-[18px] text-fg-3 md:block">
          ⌘K
        </kbd>
        <button
          type="submit"
          aria-label="Send"
          className={`grid flex-none place-items-center rounded-full bg-fg text-canvas ${lg ? 'h-10 w-10' : 'h-8 w-8'}`}
        >
          <ArrowUp />
        </button>
      </form>
      {suggestions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => submit(s)}
              className="h-7 rounded-full border border-line px-3 text-[12.5px] text-fg-2 transition-colors hover:border-line-strong hover:text-fg"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Sheet({ top, turns, onClose }: { top: number; turns: Turn[]; onClose: () => void }) {
  const { ask } = useAsk();
  const [q, setQ] = useState('');
  const last = turns[turns.length - 1];
  const [shown, setShown] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);
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
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [shown, turns.length]);

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-canvas/75"
      />
      <div className="relative mx-auto max-w-[1120px] px-4 md:px-10" style={{ paddingTop: top }}>
        <div
          role="dialog"
          aria-label="Copilot"
          className="animate-rise overflow-hidden rounded-[14px] border bg-canvas"
          style={{
            borderColor: 'color-mix(in srgb, rgb(var(--fg)) 26%, rgb(var(--line)))',
            boxShadow:
              '0 40px 120px -40px color-mix(in srgb, rgb(var(--fg)) 26%, transparent), 0 30px 60px -30px rgb(0 0 0 / 0.4)',
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask(q);
              setQ('');
            }}
            className="flex h-[60px] items-center gap-3 border-b border-line pl-5 pr-2.5"
          >
            <Mono className="text-fg-3">Ask</Mono>
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ask a follow-up"
              aria-label="Ask Copilot"
              className="min-w-0 flex-1 bg-transparent text-[16px] text-fg outline-none placeholder:text-fg-3"
            />
            <kbd className="rounded-[4px] border border-line px-1.5 font-mono text-[10.5px] leading-[18px] text-fg-3">
              esc
            </kbd>
            <button
              type="submit"
              aria-label="Send"
              className="grid h-10 w-10 place-items-center rounded-full bg-fg text-canvas"
            >
              <ArrowUp />
            </button>
          </form>
          <div
            ref={scroller}
            className="overflow-y-auto px-5 py-2"
            style={{ maxHeight: `calc(100vh - ${top + 110}px)` }}
          >
            {turns.length === 0 && (
              <p className="py-6 text-[13px] text-fg-3">
                Ask about the account, a session or a strategy, or describe a new one.
              </p>
            )}
            {turns.map((t) => {
              const streaming = t.id === lastId && t.role === 'copilot';
              const text = streaming ? t.text.slice(0, shown) : t.text;
              const done = !streaming || shown >= t.text.length;
              return (
                <div
                  key={t.id}
                  className="grid grid-cols-[76px_minmax(0,1fr)] gap-4 border-b border-line py-4 last:border-b-0"
                >
                  <Mono className={`pt-[5px] ${t.role === 'you' ? 'text-fg-3' : 'text-fg'}`}>
                    {t.role === 'you' ? 'You' : 'Copilot'}
                  </Mono>
                  <div className="min-w-0">
                    <p
                      className={`m-0 max-w-[720px] text-[14.5px] leading-[1.55] ${t.role === 'you' ? 'text-fg-2' : 'text-fg'}`}
                    >
                      {text}
                      {!done && (
                        <span className="ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-pulse bg-fg" />
                      )}
                    </p>
                    {done && t.artifact && (
                      <div className="mt-3 animate-rise">
                        <ArtifactView turn={t} onClose={onClose} />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function Box({ children }: { children: ReactNode }) {
  return <div className="rounded-[10px] border border-line px-4 py-1">{children}</div>;
}

function Actions({ children }: { children: ReactNode }) {
  return <div className="mt-3 flex flex-wrap items-center gap-2">{children}</div>;
}

function ArtifactView({ turn, onClose }: { turn: Turn; onClose: () => void }) {
  const nav = useNavigate();
  const { setProposal } = useAsk();
  const go = (to: string) => {
    onClose();
    nav(to);
  };

  if (turn.artifact === 'today')
    return (
      <>
        <Box>
          {SESSIONS.filter((s) => !s.stoppedOn).map((s) => {
            const st = strategyById(s.strategyId);
            return (
              <div
                key={s.id}
                className="grid grid-cols-[minmax(0,1fr)_64px_100px_96px_70px] items-center gap-3 border-b border-line py-2.5 text-[13px] last:border-b-0"
              >
                <span className="truncate text-fg">{st?.name}</span>
                <ModeTag mode={s.mode} />
                <Spark values={sessionWindow(s).main.slice(-15)} width={96} height={22} />
                <Delta v={s.today} className="text-right">
                  {signedUsd(s.today)}
                </Delta>
                <Delta v={s.today} className="text-right text-fg-3">
                  {pct(s.today / (s.value - s.today), 2)}
                </Delta>
              </div>
            );
          })}
        </Box>
        <Actions>
          <Button onClick={() => go('/c/sessions')}>Open sessions</Button>
          <Button variant="quiet" onClick={() => go('/c/portfolio')}>
            Holdings by asset class
          </Button>
        </Actions>
      </>
    );

  if (turn.artifact === 'proposal' && turn.strategyId) {
    const st = strategyById(turn.strategyId);
    const prop = PROPOSALS[turn.strategyId];
    if (!st || !prop) return null;
    const b = lastBacktest(st.id);
    const items = diffItems(
      itemsOf(st.name, st.cadence, st.rules),
      itemsOf(st.name, st.cadence, prop.rules)
    );
    return (
      <>
        <Box>
          <OutlineView strategy={st} items={items} compact />
        </Box>
        <div className="mt-2 font-mono text-[11.5px] tabular-nums text-fg-3">
          v{prop.version}{' '}
          <span className={tone(prop.effect.ret)}>{pts(prop.effect.ret * 100)}</span> · worst{' '}
          {pts(prop.effect.worst * 100)}
          {b && (
            <>
              {' · against '}v{st.version} {pts(b.ret * 100)} · worst {pts(b.worst * 100)}
            </>
          )}
        </div>
        <Actions>
          <Button
            variant="primary"
            onClick={() => {
              setProposal(st.id, 'applied');
              go(`/c/strategies/${st.id}`);
            }}
          >
            Apply as version {prop.version}
          </Button>
          <Button
            onClick={() => {
              setProposal(st.id, 'open');
              go(`/c/strategies/${st.id}`);
            }}
          >
            Open in builder
          </Button>
          <Button variant="quiet" onClick={() => setProposal(st.id, 'dismissed')}>
            Discard
          </Button>
        </Actions>
      </>
    );
  }

  if (turn.artifact === 'draft')
    return (
      <>
        <Box>
          <OutlineView
            strategy={DRAFT}
            items={itemsOf(DRAFT.name, DRAFT.cadence, DRAFT.rules)}
            compact
          />
        </Box>
        <div className="mt-3">
          <Figures>
            <Figure label="Total return" sub="SPY +21.9%">
              <span className="text-gain">+27.6%</span>
            </Figure>
            <Figure label="Sharpe" sub="SPY 0.77">
              0.81
            </Figure>
            <Figure label="Max drawdown" sub="SPY −20.4%">
              −11.8%
            </Figure>
          </Figures>
          <div className="mt-2 text-[11.5px] text-fg-3">
            Quick backtest · Nov 2024 to Nov 2026 · $25,000 · benchmark SPY
          </div>
        </div>
        <Actions>
          <Button variant="primary" onClick={() => go('/c/strategies')}>
            Save as draft
          </Button>
          <Button onClick={() => go('/c/backtests')}>Full backtest</Button>
        </Actions>
      </>
    );

  if (turn.artifact === 'explain' && turn.strategyId) {
    const st = strategyById(turn.strategyId);
    if (!st) return null;
    const b = lastBacktest(st.id);
    return (
      <>
        <Box>
          <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} compact />
        </Box>
        {b && (
          <div className="mt-3">
            <Figures>
              <Figure label="Total return" sub={`SPY ${pts(b.spy * 100)}`}>
                <span className={tone(b.ret)}>{pts(b.ret * 100)}</span>
              </Figure>
              <Figure label="Sharpe" sub="SPY 0.77">
                {b.sharpe.toFixed(2)}
              </Figure>
              <Figure label="Max drawdown" sub="SPY −20.4%">
                {pts(b.worst * 100)}
              </Figure>
            </Figures>
          </div>
        )}
        <Actions>
          <Button onClick={() => go(`/c/strategies/${st.id}`)}>Open in builder</Button>
          {b && (
            <Button variant="quiet" onClick={() => go(`/c/backtests/${b.id}`)}>
              Last backtest
            </Button>
          )}
        </Actions>
      </>
    );
  }
  return null;
}
