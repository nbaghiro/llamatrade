import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Ticker } from '../../components/ui/TreeRow';
import {
  ACCOUNT,
  BACKTESTS,
  pct,
  SESSIONS,
  signedUsd,
  strategyById,
  usd,
  type Strategy,
} from '../data';

import {
  AskContext,
  useAsk,
  type Artifact,
  type AskApi,
  type ProposalState,
  type Turn,
} from './askContext';
import {
  ASSET_CLASSES,
  DRIFT,
  FUND_NAME,
  FUND_TODAY,
  lastBacktest,
  PROPOSALS,
  pts,
  pts2,
  sessionActivity,
  sessionValues,
  sessionWindow,
  tone,
} from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf } from './outlineModel';
import {
  Button,
  ClassBar,
  Delta,
  Figure,
  Figures,
  ModeTag,
  Mono,
  Panel,
  Spark,
  WeightBar,
} from './ui';

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

type Answer = Pick<Turn, 'text' | 'artifact' | 'strategyId' | 'sessionId'>;

function parseContext(context?: string): { strategyId?: string; sessionId?: string; kind: string } {
  if (!context) return { kind: 'none' };
  const [kind, ref] = context.includes(':') ? context.split(':') : ['strategy', context];
  if (kind === 'session') {
    const s = SESSIONS.find((x) => x.id === ref);
    return { kind, sessionId: ref, strategyId: s?.strategyId };
  }
  if (kind === 'backtest') {
    return { kind, strategyId: BACKTESTS.find((b) => b.id === ref)?.strategyId };
  }
  return { kind, strategyId: kind === 'strategy' ? ref : undefined };
}

function answer(prompt: string, context?: string): Answer {
  const p = prompt.toLowerCase();
  const c = parseContext(context);

  if (/gold|safer|lower|edit|change|tweak|top 4|improve/.test(p)) {
    const id =
      c.strategyId && PROPOSALS[c.strategyId]
        ? c.strategyId
        : /momentum|sector|top 4/.test(p)
          ? 'momentum-sectors'
          : 'recession-radar';
    const prop = PROPOSALS[id];
    return {
      text: `Here is an edit to ${strategyById(id)?.name}. ${prop.note}. Over the same two years it gives up a little return for a smaller worst drop.`,
      artifact: 'proposal',
      strategyId: id,
    };
  }
  if (/draft|build|new|trend|create|write/.test(p))
    return {
      text: 'This draft holds QQQ while it closes above its 100-day average and moves to T-bills when it falls below. It checks at each close. A quick backtest is under the outline.',
      artifact: 'draft',
    };
  if (/drift|target|rebalanc/.test(p))
    return {
      text: 'All-Weather has moved off its targets since the last rebalance. VGLT is 3.9 points over its 40% target and GLD is 0.7 under. It rebalances on Dec 1, or you can rebalance it now.',
      artifact: 'drift',
      strategyId: 'all-weather',
    };
  if (/fill|order|trade|bought|sold/.test(p))
    return {
      text: 'Two sessions traded this week. Momentum Sectors reset its weights on Nov 16, and Recession Radar moved from SPY to TLT and GLD on Nov 13 when SPY closed under its 200-day average.',
      artifact: 'fills',
    };
  if (c.sessionId) {
    const s = SESSIONS.find((x) => x.id === c.sessionId);
    const st = s && strategyById(s.strategyId);
    if (s && st) {
      const { w, since } = sessionValues(s);
      return {
        text: s.holds.length
          ? `${st.name} holds ${s.holds.map((h) => h.symbol).join(', ')}. ${st.summary} It is ${pts(since * 100)} since it started on ${s.started}, against ${pts(w.bench[w.bench.length - 1])} for SPY.`
          : `${st.name} stopped on ${s.stoppedOn} and holds cash. It ended ${pts(since * 100)} from its start.`,
        artifact: 'session',
        sessionId: s.id,
        strategyId: st.id,
      };
    }
  }
  if (c.kind === 'portfolio' || /class|risk|exposure|asset/.test(p)) {
    const top = ASSET_CLASSES[0];
    return {
      text: `${top.name} are the largest part of the account at ${((top.value / ACCOUNT.total) * 100).toFixed(1)}%, held by All-Weather and Recession Radar. The stopped Tech Momentum session left ${usd(ASSET_CLASSES[ASSET_CLASSES.length - 1].value)} in cash.`,
      artifact: 'classes',
    };
  }
  if (c.strategyId && !/today|down|account/.test(p)) {
    const s = strategyById(c.strategyId);
    const b = lastBacktest(c.strategyId);
    return {
      text: `${s?.name} ${s?.summary.charAt(0).toLowerCase()}${s?.summary.slice(1)}${b ? ` Version ${b.version} returned ${pts(b.ret * 100)} over two years, against ${pts(b.spy * 100)} for SPY.` : ''}`,
      artifact: 'explain',
      strategyId: c.strategyId,
    };
  }
  return {
    text: `The account is down ${signedUsd(ACCOUNT.today).slice(1)} today, ${pct(ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today), 2).slice(1)}. All three running sessions fell. Recession Radar lost the most as TLT and GLD slipped.`,
    artifact: 'today',
  };
}

const scopeOf = (path: string) => path.replace(/\/+$/, '') || '/d';

export function AskProvider({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const scope = scopeOf(pathname);
  const [threads, setThreads] = useState<Record<string, Turn[]>>({});
  const [proposals, setProposals] = useState<Record<string, ProposalState>>({});
  const input = useRef<HTMLInputElement | null>(null);
  const nextId = useRef(1);

  const ask = useCallback(
    (prompt: string, context?: string) => {
      const q = prompt.trim();
      if (!q) return;
      const turn: Turn = {
        id: nextId.current++,
        q,
        at: '12:04 ET',
        born: Date.now(),
        ...answer(q, context),
      };
      setThreads((t) => ({ ...t, [scope]: [...(t[scope] ?? []), turn] }));
    },
    [scope]
  );

  const focusComposer = useCallback(() => {
    input.current?.focus();
    input.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, []);

  const api = useMemo<AskApi>(
    () => ({
      scope,
      thread: threads[scope] ?? [],
      ask,
      remove: (id) =>
        setThreads((t) => ({ ...t, [scope]: (t[scope] ?? []).filter((x) => x.id !== id) })),
      clear: () => setThreads((t) => ({ ...t, [scope]: [] })),
      focusComposer,
      register: (el) => {
        input.current = el;
      },
      proposals,
      setProposal: (id, s) => setProposals((p) => ({ ...p, [id]: s })),
    }),
    [scope, threads, ask, focusComposer, proposals]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        focusComposer();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [focusComposer]);

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

/** The Ask composer: the one lifted panel on Today, a slim line at the top of other pages. */
export function Composer({
  size = 'sm',
  context,
  placeholder,
  suggestions = [],
  reads,
}: {
  size?: 'hero' | 'sm';
  context?: string;
  placeholder?: string;
  suggestions?: string[];
  reads?: string[];
}) {
  const { ask, register } = useAsk();
  const [q, setQ] = useState('');
  const submit = (text: string) => {
    ask(text, context);
    setQ('');
  };
  const hint = placeholder ?? 'Ask about your account, or describe a strategy';

  if (size === 'sm')
    return (
      <div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(q);
          }}
          className="flex h-11 items-center gap-3 rounded-full border border-line-strong bg-canvas pl-4 pr-1.5 transition-colors focus-within:border-fg-3"
        >
          <Mono className="text-fg-3">Ask</Mono>
          <input
            ref={register}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={hint}
            aria-label="Ask Copilot"
            className="min-w-0 flex-1 bg-transparent text-[14px] text-fg outline-none placeholder:text-fg-3"
          />
          <kbd className="hidden rounded-[4px] border border-line px-1.5 font-mono text-[10.5px] leading-[18px] text-fg-3 md:block">
            ⌘K
          </kbd>
          <button
            type="submit"
            aria-label="Send"
            className="grid h-8 w-8 flex-none place-items-center rounded-full bg-fg text-canvas"
          >
            <ArrowUp />
          </button>
        </form>
        {suggestions.length > 0 && <Suggestions items={suggestions} onPick={submit} />}
      </div>
    );

  return (
    <div>
      <Panel>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(q);
          }}
        >
          <div className="flex items-center gap-4 px-5 pb-3 pt-5 md:px-7 md:pt-6">
            <input
              ref={register}
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={hint}
              aria-label="Ask Copilot"
              className="min-w-0 flex-1 bg-transparent text-[18px] tracking-[-0.015em] text-fg outline-none placeholder:text-fg-3 md:text-[23px]"
            />
          </div>
          <div className="flex items-center gap-3 px-5 pb-4 md:px-7">
            {reads && (
              <span className="hidden min-w-0 flex-1 items-center gap-2 truncate md:flex">
                <Mono className="text-fg-3">Reads</Mono>
                {reads.map((r) => (
                  <span
                    key={r}
                    className="whitespace-nowrap rounded-[4px] bg-sunk px-1.5 py-0.5 font-mono text-[11px] text-fg-2"
                  >
                    {r}
                  </span>
                ))}
              </span>
            )}
            <span className="ml-auto flex items-center gap-3">
              <kbd className="hidden rounded-[4px] border border-line px-1.5 font-mono text-[10.5px] leading-[18px] text-fg-3 md:block">
                ⌘K
              </kbd>
              <button
                type="submit"
                aria-label="Send"
                className="grid h-10 w-10 flex-none place-items-center rounded-full bg-fg text-canvas"
              >
                <ArrowUp />
              </button>
            </span>
          </div>
        </form>
      </Panel>
      {suggestions.length > 0 && <Suggestions items={suggestions} onPick={submit} />}
    </div>
  );
}

function Suggestions({ items, onPick }: { items: string[]; onPick: (s: string) => void }) {
  return (
    <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 px-1">
      {items.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onPick(s)}
          className="group inline-flex items-center gap-1.5 text-[13px] text-fg-3 transition-colors hover:text-fg"
        >
          <span aria-hidden="true" className="font-mono text-[11px] text-fg-3 group-hover:text-fg">
            ↳
          </span>
          {s}
        </button>
      ))}
    </div>
  );
}

/** The conversation as sections of the page: each question, its answer and its artifact. */
export function Brief({ context, gutter = true }: { context?: string; gutter?: boolean }) {
  const { thread, ask, clear } = useAsk();
  const [q, setQ] = useState('');
  if (thread.length === 0) return null;
  const cols = gutter ? 'md:grid-cols-[88px_minmax(0,1fr)]' : '';
  return (
    <div className="mt-12">
      {thread.map((t, i) => (
        <Section key={t.id} turn={t} n={i + 1} cols={cols} />
      ))}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(q, context);
          setQ('');
        }}
        className={`grid items-center gap-x-8 gap-y-2 border-t border-line pt-5 ${cols}`}
      >
        <Mono className="hidden text-fg-3 md:block">
          {String(thread.length + 1).padStart(2, '0')}
        </Mono>
        <div className="flex items-center gap-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask a follow-up"
            aria-label="Ask a follow-up"
            className="min-w-0 flex-1 bg-transparent text-[16px] text-fg outline-none placeholder:text-fg-3"
          />
          <button
            type="button"
            onClick={clear}
            className="text-[12.5px] text-fg-3 transition-colors hover:text-fg"
          >
            Clear brief
          </button>
        </div>
      </form>
    </div>
  );
}

function Section({ turn, n, cols }: { turn: Turn; n: number; cols: string }) {
  const { remove } = useAsk();
  const fresh = useRef(Date.now() - turn.born < 1000);
  const len = turn.text.length;
  const [shown, setShown] = useState(fresh.current ? -1 : len);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!fresh.current) return;
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    let iv = 0;
    const t = window.setTimeout(() => {
      let s = 0;
      iv = window.setInterval(() => {
        s = Math.min(len, s + 3);
        setShown(s);
        if (s >= len) {
          window.clearInterval(iv);
          fresh.current = false;
        }
      }, 16);
    }, 520);
    return () => {
      window.clearTimeout(t);
      window.clearInterval(iv);
    };
  }, [len]);

  const done = shown >= len;
  return (
    <section
      ref={ref}
      className={`grid scroll-mt-24 gap-x-8 gap-y-3 border-t border-line pb-12 pt-8 ${cols}`}
    >
      <div className="flex items-baseline gap-3 md:block">
        <Mono className="text-fg">{String(n).padStart(2, '0')}</Mono>
        <span className="font-mono text-[11px] text-fg-3 md:mt-2 md:block">{turn.at}</span>
      </div>
      <div className="min-w-0">
        <div className="flex items-start justify-between gap-4">
          <h2 className="m-0 text-[21px] font-semibold leading-snug tracking-[-0.02em] text-fg md:text-[24px]">
            {turn.q}
          </h2>
          <button
            type="button"
            aria-label="Remove from brief"
            onClick={() => remove(turn.id)}
            className="mt-1 grid h-7 w-7 flex-none place-items-center rounded-full text-fg-3 transition-colors hover:bg-sunk hover:text-fg"
          >
            <svg viewBox="0 0 10 10" aria-hidden="true" className="h-2.5 w-2.5">
              <path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth="1.4" />
            </svg>
          </button>
        </div>
        {shown < 0 ? (
          <p className="m-0 mt-3 inline-flex items-center gap-2 text-[13px] text-fg-3">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-fg" />
            Reading the account
          </p>
        ) : (
          <p className="m-0 mt-3 max-w-[700px] text-[15.5px] leading-[1.6] text-fg-2">
            {turn.text.slice(0, shown)}
            {!done && (
              <span className="ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-pulse bg-fg" />
            )}
          </p>
        )}
        {done && turn.artifact && (
          <div className="mt-7 animate-rise">
            <ArtifactView turn={turn} kind={turn.artifact} />
          </div>
        )}
      </div>
    </section>
  );
}

function Actions({ children }: { children: ReactNode }) {
  return <div className="mt-5 flex flex-wrap items-center gap-2">{children}</div>;
}

function Rows({ children }: { children: ReactNode }) {
  return <div className="border-t border-line">{children}</div>;
}

function BacktestFigures({ ret, spy, sharpe, worst }: Record<string, number>) {
  return (
    <Figures>
      <Figure label="Total return" sub={`SPY ${pts(spy)}`}>
        <span className={tone(ret)}>{pts(ret)}</span>
      </Figure>
      <Figure label="Sharpe" sub="SPY 0.77">
        {sharpe.toFixed(2)}
      </Figure>
      <Figure label="Max drawdown" sub="SPY −20.4%">
        {pts(worst)}
      </Figure>
    </Figures>
  );
}

function ArtifactView({ turn, kind }: { turn: Turn; kind: Artifact }) {
  const nav = useNavigate();
  const { setProposal, proposals } = useAsk();
  const [queued, setQueued] = useState(false);

  if (kind === 'today')
    return (
      <>
        <Rows>
          {SESSIONS.filter((s) => !s.stoppedOn).map((s) => {
            const st = strategyById(s.strategyId);
            return (
              <div
                key={s.id}
                className="grid grid-cols-[minmax(0,1fr)_88px] items-center gap-4 border-b border-line py-3 text-[13.5px] md:grid-cols-[minmax(0,1fr)_72px_120px_minmax(0,1fr)_100px_70px]"
              >
                <span className="truncate font-medium text-fg">{st?.name}</span>
                <span className="hidden md:block">
                  <ModeTag mode={s.mode} />
                </span>
                <span className="hidden md:block">
                  <Spark values={sessionWindow(s).main.slice(-15)} width={110} height={24} />
                </span>
                <span className="hidden truncate font-mono text-[11.5px] text-fg-3 md:block">
                  {s.holds.map((h) => `${h.symbol} ${pts2(FUND_TODAY[h.symbol] ?? 0)}`).join('  ')}
                </span>
                <Delta v={s.today} className="text-right">
                  {signedUsd(s.today)}
                </Delta>
                <Delta v={s.today} className="hidden text-right text-fg-3 md:block">
                  {pct(s.today / (s.value - s.today), 2)}
                </Delta>
              </div>
            );
          })}
        </Rows>
        <Actions>
          <Button onClick={() => nav('/d/sessions')}>Open sessions</Button>
          <Button variant="quiet" onClick={() => nav('/d/portfolio')}>
            Holdings by asset class
          </Button>
        </Actions>
      </>
    );

  if (kind === 'proposal' && turn.strategyId) {
    const st = strategyById(turn.strategyId);
    const prop = PROPOSALS[turn.strategyId];
    if (!st || !prop) return null;
    const b = lastBacktest(st.id);
    const state = proposals[st.id];
    const items = diffItems(
      itemsOf(st.name, st.cadence, st.rules),
      itemsOf(st.name, st.cadence, prop.rules)
    );
    return (
      <>
        <div className="border-y border-line">
          <OutlineView strategy={st} items={items} compact />
        </div>
        <div className="mt-3 font-mono text-[11.5px] tabular-nums text-fg-3">
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
          {state === 'dismissed' ? (
            <span className="text-[13px] text-fg-3">Discarded.</span>
          ) : (
            <>
              <Button
                variant="primary"
                onClick={() => {
                  setProposal(st.id, 'applied');
                  nav(`/d/strategies/${st.id}`);
                }}
              >
                Apply as version {prop.version}
              </Button>
              <Button
                onClick={() => {
                  setProposal(st.id, 'open');
                  nav(`/d/strategies/${st.id}`);
                }}
              >
                Open in builder
              </Button>
              <Button variant="quiet" onClick={() => setProposal(st.id, 'dismissed')}>
                Discard
              </Button>
            </>
          )}
        </Actions>
      </>
    );
  }

  if (kind === 'draft')
    return (
      <>
        <div className="border-y border-line">
          <OutlineView
            strategy={DRAFT}
            items={itemsOf(DRAFT.name, DRAFT.cadence, DRAFT.rules)}
            compact
          />
        </div>
        <div className="mt-5">
          <BacktestFigures ret={27.6} spy={21.9} sharpe={0.81} worst={-11.8} />
          <div className="mt-2 text-[11.5px] text-fg-3">
            Quick backtest · Nov 2024 to Nov 2026 · $25,000 · benchmark SPY
          </div>
        </div>
        <Actions>
          <Button variant="primary" onClick={() => nav('/d/strategies')}>
            Save as draft
          </Button>
          <Button onClick={() => nav('/d/backtests')}>Full backtest</Button>
        </Actions>
      </>
    );

  if (kind === 'explain' && turn.strategyId) {
    const st = strategyById(turn.strategyId);
    if (!st) return null;
    const b = lastBacktest(st.id);
    return (
      <>
        <div className="border-y border-line">
          <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} compact />
        </div>
        {b && (
          <div className="mt-5">
            <BacktestFigures
              ret={b.ret * 100}
              spy={b.spy * 100}
              sharpe={b.sharpe}
              worst={b.worst * 100}
            />
          </div>
        )}
        <Actions>
          <Button onClick={() => nav(`/d/strategies/${st.id}`)}>Open in builder</Button>
          {b && (
            <Button variant="quiet" onClick={() => nav(`/d/backtests/${b.id}`)}>
              Last backtest
            </Button>
          )}
        </Actions>
      </>
    );
  }

  if (kind === 'drift')
    return (
      <>
        <div className="grid grid-cols-[52px_minmax(0,1fr)_64px_64px] gap-4 border-b border-line pb-2 text-[11.5px] font-medium text-fg-3 md:grid-cols-[52px_160px_minmax(0,1fr)_72px_72px_80px]">
          <span>Fund</span>
          <span className="hidden md:block" />
          <span>Holds against target</span>
          <span className="text-right">Target</span>
          <span className="text-right">Holds</span>
          <span className="hidden text-right md:block">Drift</span>
        </div>
        {DRIFT.map((d) => (
          <div
            key={d.symbol}
            className="grid grid-cols-[52px_minmax(0,1fr)_64px_64px] items-center gap-4 border-b border-line py-2.5 text-[13px] md:grid-cols-[52px_160px_minmax(0,1fr)_72px_72px_80px]"
          >
            <Ticker symbol={d.symbol} />
            <span className="hidden truncate text-fg-3 md:block">{FUND_NAME[d.symbol]}</span>
            <WeightBar value={d.holds} target={d.target} />
            <span className="text-right font-mono tabular-nums text-fg-3">
              {d.target.toFixed(1)}%
            </span>
            <span className="text-right font-mono tabular-nums text-fg">{d.holds.toFixed(1)}%</span>
            <span
              className={`hidden text-right font-mono tabular-nums md:block ${Math.abs(d.holds - d.target) >= 2 ? 'text-fg' : 'text-fg-3'}`}
            >
              {d.holds - d.target >= 0 ? '+' : '−'}
              {Math.abs(d.holds - d.target).toFixed(1)} pts
            </span>
          </div>
        ))}
        <Actions>
          <Button variant="primary" disabled={queued} onClick={() => setQueued(true)}>
            {queued ? 'Rebalance queued for the next open' : 'Rebalance now'}
          </Button>
          <Button onClick={() => nav('/d/sessions/s-aw')}>Open session</Button>
        </Actions>
      </>
    );

  if (kind === 'fills') {
    const rows = ['s-ms', 's-rr'].flatMap((id) => {
      const s = SESSIONS.find((x) => x.id === id);
      if (!s) return [];
      const name = strategyById(s.strategyId)?.name ?? '';
      return sessionActivity(s)
        .filter((a) => !a.what.startsWith('Started'))
        .map((a) => ({ ...a, name, id }));
    });
    return (
      <>
        <Rows>
          {rows.map((r, i) => (
            <div
              key={i}
              className="grid grid-cols-[56px_minmax(0,1fr)] items-baseline gap-4 border-b border-line py-2.5 text-[13px] md:grid-cols-[56px_170px_180px_minmax(0,1fr)]"
            >
              <span className="font-mono text-[12px] text-fg-3">{r.when}</span>
              <span className="hidden truncate text-fg-2 md:block">{r.name}</span>
              <span className="text-fg">{r.what}</span>
              <span className="truncate text-fg-3 max-md:col-start-2">{r.detail}</span>
            </div>
          ))}
        </Rows>
        <Actions>
          <Button onClick={() => nav('/d/sessions/s-ms')}>Momentum Sectors session</Button>
          <Button variant="quiet" onClick={() => nav('/d/sessions/s-rr')}>
            Recession Radar session
          </Button>
        </Actions>
      </>
    );
  }

  if (kind === 'session' && turn.sessionId) {
    const s = SESSIONS.find((x) => x.id === turn.sessionId);
    if (!s) return null;
    return (
      <>
        <Rows>
          {s.holds.length === 0 && (
            <p className="m-0 border-b border-line py-3 text-[13px] text-fg-3">All cash.</p>
          )}
          {s.holds.map((h) => (
            <div
              key={h.symbol}
              className="grid grid-cols-[52px_minmax(0,1fr)_100px] items-center gap-4 border-b border-line py-2.5 text-[13px] md:grid-cols-[52px_minmax(0,1fr)_160px_110px_70px]"
            >
              <Ticker symbol={h.symbol} on />
              <span className="truncate text-fg-3">{FUND_NAME[h.symbol]}</span>
              <span className="hidden md:block">
                <WeightBar value={h.weight} />
              </span>
              <span className="text-right font-mono tabular-nums text-fg">
                {usd((s.value * h.weight) / 100)}
              </span>
              <Delta
                v={FUND_TODAY[h.symbol] ?? 0}
                className="hidden text-right text-[12px] md:block"
              >
                {pts2(FUND_TODAY[h.symbol] ?? 0)}
              </Delta>
            </div>
          ))}
        </Rows>
        {turn.strategyId && (
          <Actions>
            <Button onClick={() => nav(`/d/strategies/${turn.strategyId}`)}>Open strategy</Button>
          </Actions>
        )}
      </>
    );
  }

  if (kind === 'classes')
    return (
      <>
        <ClassBar />
        <Actions>
          <Button onClick={() => nav('/d/portfolio')}>Open portfolio</Button>
        </Actions>
      </>
    );

  return null;
}
