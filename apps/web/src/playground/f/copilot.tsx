import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { ACCOUNT, BACKTESTS, pct, SESSIONS, signedUsd, strategyById, type Strategy } from '../data';

import { PerfChart } from './chart';
import { CommandBar } from './command';
import { results } from './commands';
import {
  CopilotContext,
  useCopilot,
  type Action,
  type CopilotApi,
  type ProposalState,
  type Turn,
} from './copilotContext';
import { lastBacktest, PROPOSALS, pts, quickBacktest, sessionWindow, to, tone } from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf } from './outlineModel';
import { Button, Delta, ModeTag, Mono, Spark, Stats } from './ui';

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

type Reply = Omit<Turn, 'id' | 'role'>;

function answer(prompt: string, context?: string): Reply {
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
      text: `${s?.name} ${s?.summary.charAt(0).toLowerCase()}${s?.summary.slice(1)}`,
      artifact: 'explain',
      strategyId: context,
    };
  }
  return {
    text: `The account is down ${signedUsd(ACCOUNT.today).slice(1)} today. All three running sessions fell; Recession Radar lost the most as TLT and GLD slipped.`,
    artifact: 'today',
  };
}

const SEED: Turn[] = [
  { id: 1, role: 'you', text: 'Why is the account down today?' },
  { id: 2, role: 'copilot', ...answer('Why is the account down today?') },
];

export function CopilotProvider({ children }: { children: ReactNode }) {
  const nav = useNavigate();
  const { pathname } = useLocation();
  const onToday = pathname === to() || pathname === to('/');
  const pageContext = useMemo(() => {
    const [, kind, id] = pathname.replace(to(), '').split('/');
    if (kind === 'strategies' && id) return id;
    if (kind === 'sessions' && id) return SESSIONS.find((s) => s.id === id)?.strategyId;
    if (kind === 'backtests' && id) return BACKTESTS.find((b) => b.id === id)?.strategyId;
    return undefined;
  }, [pathname]);
  const [turns, setTurns] = useState<Turn[]>(SEED);
  const [streamId, setStreamId] = useState<number | null>(null);
  const [bar, setBar] = useState<{ open: boolean; context?: string }>({ open: false });
  const [proposals, setProposals] = useState<Record<string, ProposalState>>({});
  const nextId = useRef(3);

  const add = useCallback(
    (you: string, reply: Reply) => {
      const id = nextId.current;
      nextId.current += 2;
      setTurns((t) => [
        ...t,
        { id, role: 'you', text: you },
        { id: id + 1, role: 'copilot', ...reply },
      ]);
      setStreamId(id + 1);
      if (onToday) {
        setBar({ open: false });
        window.setTimeout(
          () => document.getElementById('f-copilot')?.scrollIntoView({ block: 'nearest' }),
          30
        );
      } else setBar((b) => ({ ...b, open: true }));
    },
    [onToday]
  );

  const run = useCallback(
    (a: Action) => {
      if (a.type === 'go') {
        setBar({ open: false });
        nav(a.to);
        return;
      }
      if (a.type === 'ask') {
        add(a.prompt, answer(a.prompt, a.context));
        return;
      }
      const s = strategyById(a.strategyId);
      add(`backtest ${s?.name.toLowerCase()} ${a.years}y`, {
        text: `${s?.name}, version ${s?.version}, over the past ${a.years} years from $25,000, against SPY.`,
        artifact: 'backtest',
        strategyId: a.strategyId,
        years: a.years,
      });
    },
    [add, nav]
  );

  const api = useMemo<CopilotApi>(
    () => ({
      turns,
      streamId,
      doneStreaming: () => setStreamId(null),
      run,
      submit: (q, context) => {
        const top = results(q, context)[0];
        if (q.trim() && top) run(top.action);
      },
      openBar: (context) => setBar({ open: true, context }),
      closeBar: () => setBar({ open: false }),
      proposals,
      setProposal: (id, s) => setProposals((p) => ({ ...p, [id]: s })),
    }),
    [turns, streamId, run, proposals]
  );

  useEffect(() => {
    document.documentElement.toggleAttribute('data-fbar', bar.open);
  }, [bar.open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing =
        e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setBar((b) => ({ open: !b.open }));
        return;
      }
      if (e.key === 'Escape') {
        setBar({ open: false });
        return;
      }
      if (typing || bar.open || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === '/') {
        e.preventDefault();
        setBar({ open: true });
      }
      const page = ['1', '2', '3', '4', '5'].indexOf(e.key);
      if (page >= 0) nav(to(['', '/strategies', '/backtests', '/sessions', '/portfolio'][page]));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [bar.open, nav]);

  return (
    <CopilotContext.Provider value={api}>
      {children}
      {bar.open && (
        <CommandBar
          context={bar.context ?? pageContext}
          showThread={!onToday}
          onClose={api.closeBar}
        />
      )}
    </CopilotContext.Provider>
  );
}

/** One turn: who said it, the text (streamed when new) and its inline artifact. */
export function TurnView({ turn, onGo }: { turn: Turn; onGo?: () => void }) {
  const { streamId, doneStreaming } = useCopilot();
  const streaming = turn.id === streamId;
  const [shown, setShown] = useState(streaming ? 0 : turn.text.length);
  const len = turn.text.length;

  useEffect(() => {
    if (!streaming) return;
    setShown(0);
    const t = window.setInterval(() => {
      setShown((s) => {
        if (s >= len) {
          window.clearInterval(t);
          doneStreaming();
          return s;
        }
        return Math.min(len, s + 3);
      });
    }, 16);
    return () => window.clearInterval(t);
  }, [streaming, len, doneStreaming]);

  const done = !streaming || shown >= len;
  const you = turn.role === 'you';
  return (
    <div className="grid grid-cols-[64px_minmax(0,1fr)] gap-3 py-2.5">
      <Mono className={`pt-[4px] ${you ? 'text-fg-3' : 'text-fg'}`}>{you ? 'You' : 'Copilot'}</Mono>
      <div className="min-w-0">
        <p
          className={`m-0 max-w-[720px] text-[13.5px] leading-[1.55] ${you ? 'font-mono text-[12.5px] text-fg-2' : 'text-fg'}`}
        >
          {streaming ? turn.text.slice(0, shown) : turn.text}
          {!done && (
            <span className="ml-0.5 inline-block h-3.5 w-[6px] translate-y-0.5 animate-pulse bg-fg" />
          )}
        </p>
        {done && turn.artifact && (
          <div className="mt-2.5 animate-rise">
            <ArtifactView turn={turn} onGo={onGo} />
          </div>
        )}
      </div>
    </div>
  );
}

function Box({ children }: { children: ReactNode }) {
  return <div className="overflow-hidden rounded-[6px] border border-line">{children}</div>;
}

function Actions({ children }: { children: ReactNode }) {
  return <div className="mt-2.5 flex flex-wrap items-center gap-2">{children}</div>;
}

function ArtifactView({ turn, onGo }: { turn: Turn; onGo?: () => void }) {
  const nav = useNavigate();
  const { setProposal, proposals } = useCopilot();
  const go = (path: string) => {
    onGo?.();
    nav(to(path));
  };

  if (turn.artifact === 'today')
    return (
      <>
        <Box>
          {SESSIONS.filter((s) => !s.stoppedOn).map((s) => {
            const st = strategyById(s.strategyId);
            return (
              <button
                type="button"
                key={s.id}
                onClick={() => go(`/sessions/${s.id}`)}
                className="grid h-8 w-full grid-cols-[minmax(0,1fr)_52px_80px] items-center gap-3 border-b border-line px-3 text-left text-[12.5px] last:border-b-0 hover:bg-panel md:grid-cols-[minmax(0,1fr)_64px_96px_96px_64px]"
              >
                <span className="truncate text-fg">{st?.name}</span>
                <ModeTag mode={s.mode} />
                <span className="hidden md:block">
                  <Spark values={sessionWindow(s).main.slice(-15)} width={96} height={18} />
                </span>
                <Delta v={s.today} className="text-right">
                  {signedUsd(s.today)}
                </Delta>
                <Delta v={s.today} className="hidden text-right text-fg-3 md:block">
                  {pct(s.today / (s.value - s.today), 2)}
                </Delta>
              </button>
            );
          })}
        </Box>
        <Actions>
          <Button onClick={() => go('/sessions')}>Open sessions</Button>
          <Button variant="quiet" onClick={() => go('/portfolio')}>
            Holdings by asset class
          </Button>
        </Actions>
      </>
    );

  if (turn.artifact === 'backtest' && turn.strategyId && turn.years) {
    const st = strategyById(turn.strategyId);
    const b = lastBacktest(turn.strategyId);
    if (!st || !b) return null;
    const r = quickBacktest(b, turn.years);
    return (
      <>
        <Box>
          <Stats
            className="border-b border-line"
            items={[
              {
                label: 'Return',
                value: <span className={tone(r.ret)}>{pts(r.ret * 100)}</span>,
                sub: `SPY ${pts(r.spy * 100)}`,
              },
              { label: 'Max drawdown', value: pts(r.worst * 100) },
              { label: 'Sharpe', value: r.sharpe.toFixed(2) },
              {
                label: 'Ending',
                value: `$${Math.round(25000 * (1 + r.ret)).toLocaleString('en-US')}`,
              },
            ]}
          />
          <div className="px-3 pb-2 pt-3">
            <PerfChart w={r.w} height={150} mainLabel={st.name} ddHeight={36} />
          </div>
        </Box>
        <div className="mt-1.5 font-mono text-[10.5px] text-fg-3">
          Sample run · past results do not predict future returns
        </div>
        <Actions>
          <Button variant="primary" onClick={() => go(`/backtests/${b.id}`)}>
            Open full result
          </Button>
          <Button onClick={() => go(`/strategies/${st.id}`)}>Open in builder</Button>
        </Actions>
      </>
    );
  }

  if (turn.artifact === 'proposal' && turn.strategyId) {
    const st = strategyById(turn.strategyId);
    const prop = PROPOSALS[turn.strategyId];
    if (!st || !prop) return null;
    const b = lastBacktest(st.id);
    const state = proposals[st.id] ?? 'open';
    const items = diffItems(
      itemsOf(st.name, st.cadence, st.rules),
      itemsOf(st.name, st.cadence, prop.rules)
    );
    return (
      <>
        <Box>
          <OutlineView strategy={st} items={items} compact />
        </Box>
        <div className="mt-1.5 font-mono text-[11px] tabular-nums text-fg-3">
          v{prop.version}{' '}
          <span className={tone(prop.effect.ret)}>{pts(prop.effect.ret * 100)}</span> · worst{' '}
          {pts(prop.effect.worst * 100)}
          {b && (
            <>
              {' · '}v{st.version} {pts(b.ret * 100)} · worst {pts(b.worst * 100)}
            </>
          )}
        </div>
        <Actions>
          {state === 'dismissed' ? (
            <span className="font-mono text-[11px] text-fg-3">Discarded</span>
          ) : (
            <>
              <Button
                variant="primary"
                onClick={() => {
                  setProposal(st.id, 'applied');
                  go(`/strategies/${st.id}`);
                }}
              >
                Apply as v{prop.version}
              </Button>
              <Button
                onClick={() => {
                  setProposal(st.id, 'open');
                  go(`/strategies/${st.id}`);
                }}
              >
                Review in builder
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

  if (turn.artifact === 'draft')
    return (
      <>
        <Box>
          <OutlineView
            strategy={DRAFT}
            items={itemsOf(DRAFT.name, DRAFT.cadence, DRAFT.rules)}
            compact
          />
          <Stats
            className="border-t border-line"
            items={[
              {
                label: 'Return',
                value: <span className="text-gain">+27.6%</span>,
                sub: 'SPY +21.9%',
              },
              { label: 'Sharpe', value: '0.81', sub: 'SPY 0.77' },
              { label: 'Max drawdown', value: '−11.8%', sub: 'SPY −20.4%' },
            ]}
          />
        </Box>
        <div className="mt-1.5 font-mono text-[10.5px] text-fg-3">
          Quick backtest · Nov 2024 to Nov 2026 · $25,000 · sample
        </div>
        <Actions>
          <Button variant="primary" onClick={() => go('/strategies')}>
            Save as draft
          </Button>
          <Button onClick={() => go('/backtests')}>Full backtest</Button>
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
          {b && (
            <Stats
              className="border-t border-line"
              items={[
                {
                  label: 'Last backtest',
                  value: <span className={tone(b.ret)}>{pts(b.ret * 100)}</span>,
                  sub: `SPY ${pts(b.spy * 100)}`,
                },
                { label: 'Sharpe', value: b.sharpe.toFixed(2) },
                { label: 'Max drawdown', value: pts(b.worst * 100) },
              ]}
            />
          )}
        </Box>
        <Actions>
          <Button onClick={() => go(`/strategies/${st.id}`)}>Open in builder</Button>
          {b && (
            <Button variant="quiet" onClick={() => go(`/backtests/${b.id}`)}>
              Last backtest
            </Button>
          )}
        </Actions>
      </>
    );
  }
  return null;
}
