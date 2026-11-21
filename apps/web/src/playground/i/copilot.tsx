import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { ACCOUNT, pct, SESSIONS, signedUsd, strategyById, type Backtest } from '../data';

import { useAsk, type Turn } from './askContext';
import { PerfChart } from './chart';
import { backtestWindow, DRAFT, lastBacktest, PROPOSALS, pts, sessionWindow, tone } from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf } from './outlineModel';
import { Button, Delta, Figure, Figures, ModeTag, Mono, Spark } from './ui';

const DRAFT_RUN: Backtest = {
  id: 'draft',
  strategyId: DRAFT.id,
  version: 1,
  ran: 'just now',
  range: 'Nov 2024 to Nov 2026',
  ret: 0.276,
  spy: 0.219,
  worst: -0.118,
  sharpe: 0.81,
  seed: 83,
};

/** A card inside the conversation: what the reply made, with its actions in the foot. */
function Inset({
  label,
  title,
  meta,
  children,
  foot,
}: {
  label: string;
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  foot?: ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-[11px] border border-line-strong">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 pb-3 pt-3.5">
        <Mono className="text-fg-3">{label}</Mono>
        <span className="text-[14px] font-semibold text-fg">{title}</span>
        {meta && <span className="text-[12px] text-fg-3">{meta}</span>}
      </div>
      <div className="px-4">{children}</div>
      {foot && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-sunk/40 px-4 py-3">
          {foot}
        </div>
      )}
    </div>
  );
}

function Outline({ children }: { children: ReactNode }) {
  return <div className="-mx-4 border-t border-line px-1">{children}</div>;
}

/** What a Copilot reply made, inline under its answer. */
export function InlineArtifact({ turn }: { turn: Turn }) {
  const nav = useNavigate();
  const { setProposal, setOpen, proposals } = useAsk();
  const go = (to: string) => {
    setOpen(false);
    nav(to);
  };

  if (turn.artifact === 'today')
    return (
      <Inset
        label="Today"
        title="By session"
        meta={`Account ${signedUsd(ACCOUNT.today)} · prices Nov 20, 12:04 ET`}
        foot={
          <>
            <Button onClick={() => go('/i/sessions/s-rr')}>Recession Radar session</Button>
            <Button variant="quiet" onClick={() => go('/i/portfolio')}>
              Holdings
            </Button>
          </>
        }
      >
        <div className="border-t border-line">
          {SESSIONS.filter((s) => !s.stoppedOn).map((s) => {
            const st = strategyById(s.strategyId);
            return (
              <div
                key={s.id}
                className="grid grid-cols-[minmax(0,1fr)_64px_96px_80px_60px] items-center gap-3 border-b border-line py-2.5 text-[13px] last:border-b-0"
              >
                <span className="truncate text-fg">{st?.name}</span>
                <ModeTag mode={s.mode} />
                <Spark values={sessionWindow(s).main.slice(-15)} width={92} height={22} />
                <Delta v={s.today} className="text-right">
                  {signedUsd(s.today)}
                </Delta>
                <Delta v={s.today} className="text-right text-fg-3">
                  {pct(s.today / (s.value - s.today), 2)}
                </Delta>
              </div>
            );
          })}
        </div>
      </Inset>
    );

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
    const w = b
      ? (() => {
          const now = backtestWindow(b);
          const next = backtestWindow({ ...b, ret: prop.effect.ret, seed: b.seed + 6 });
          return { ...next, bench: now.main };
        })()
      : null;
    return (
      <Inset
        label="Proposed edit"
        title={`${st.name}, v${st.version} to v${prop.version}`}
        meta="quick backtest, Nov 2024 to Nov 2026"
        foot={
          state === 'open' ? (
            <>
              <Button
                variant="primary"
                onClick={() => {
                  setProposal(st.id, 'applied');
                  go(`/i/strategies/${st.id}`);
                }}
              >
                Apply as v{prop.version}
              </Button>
              <Button onClick={() => go(`/i/strategies/${st.id}`)}>Open in builder</Button>
              <Button variant="quiet" onClick={() => setProposal(st.id, 'dismissed')}>
                Discard
              </Button>
            </>
          ) : (
            <span className="text-[12.5px] text-fg-3">
              {state === 'applied' ? `Applied as v${prop.version}, not saved yet.` : 'Discarded.'}
            </span>
          )
        }
      >
        <Figures>
          <Figure label="Total return" sub={b ? `v${st.version} ${pts(b.ret * 100)}` : undefined}>
            <span className={tone(prop.effect.ret)}>{pts(prop.effect.ret * 100)}</span>
          </Figure>
          <Figure label="Max drawdown" sub={b ? `v${st.version} ${pts(b.worst * 100)}` : undefined}>
            {pts(prop.effect.worst * 100)}
          </Figure>
          <Figure label={`Against v${st.version}`} sub="pts, worst drop">
            {b
              ? `${(prop.effect.worst - b.worst) * 100 >= 0 ? '+' : '−'}${Math.abs((prop.effect.worst - b.worst) * 100).toFixed(1)}`
              : '·'}
          </Figure>
        </Figures>
        {w && (
          <div className="mt-3">
            <PerfChart
              w={w}
              height={120}
              mainLabel={`v${prop.version}`}
              benchLabel={`v${st.version}`}
              drawdownStrip={false}
            />
          </div>
        )}
        <div className="mt-3">
          <Outline>
            <OutlineView strategy={st} items={items} />
          </Outline>
        </div>
      </Inset>
    );
  }

  if (turn.artifact === 'draft') {
    const w = backtestWindow(DRAFT_RUN);
    return (
      <Inset
        label="New draft"
        title={DRAFT.name}
        meta="quick backtest · $25,000 · benchmark SPY"
        foot={
          <>
            <Button variant="primary" onClick={() => go('/i/strategies')}>
              Save as draft
            </Button>
            <Button onClick={() => go('/i/backtests')}>Full backtest</Button>
          </>
        }
      >
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
        <div className="mt-3">
          <PerfChart w={w} height={130} mainLabel={DRAFT.name} drawdownStrip={false} />
        </div>
        <div className="mt-3">
          <Outline>
            <OutlineView strategy={DRAFT} items={itemsOf(DRAFT.name, DRAFT.cadence, DRAFT.rules)} />
          </Outline>
        </div>
      </Inset>
    );
  }

  if (turn.artifact === 'explain' && turn.strategyId) {
    const st = strategyById(turn.strategyId);
    if (!st) return null;
    const b = lastBacktest(st.id);
    return (
      <Inset
        label="Strategy"
        title={st.name}
        meta={b ? `last backtest ran ${b.ran}, ${b.range}` : 'not backtested yet'}
        foot={
          <>
            <Button onClick={() => go(`/i/strategies/${st.id}`)}>Open in builder</Button>
            {b && (
              <Button variant="quiet" onClick={() => go(`/i/backtests/${b.id}`)}>
                Last backtest
              </Button>
            )}
          </>
        }
      >
        {b && (
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
        )}
        <div className="mt-3">
          <Outline>
            <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} />
          </Outline>
        </div>
      </Inset>
    );
  }
  return null;
}
