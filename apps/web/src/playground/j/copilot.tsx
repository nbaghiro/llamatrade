import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { ACCOUNT, pct, SESSIONS, signedUsd, strategyById } from '../data';

import { useAsk, type Turn } from './askContext';
import { DRAFT, lastBacktest, PROPOSALS, pts, sessionWindow, tone } from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf } from './outlineModel';
import { Button, Delta, Figure, Figures, ModeTag, PanelFoot, PanelHead, Spark } from './ui';

function Block({ children }: { children: ReactNode }) {
  return (
    <section className="rounded-[10px] border border-line bg-canvas p-4 md:p-5">{children}</section>
  );
}

/** What a Copilot reply made, set inside the conversation under the reply. */
export function ArtifactBlock({ turn }: { turn: Turn }) {
  const nav = useNavigate();
  const { setProposal, setThreadOpen } = useAsk();
  const go = (to: string) => {
    setThreadOpen(false);
    nav(to);
  };

  if (turn.artifact === 'today')
    return (
      <Block>
        <PanelHead
          eyebrow="Today by session"
          title="Every running session fell"
          meta={`Account ${signedUsd(ACCOUNT.today)} · prices Nov 20, 12:04 ET`}
        />
        <div className="mt-[18px] border-t border-line">
          {SESSIONS.filter((s) => !s.stoppedOn).map((s) => {
            const st = strategyById(s.strategyId);
            return (
              <div
                key={s.id}
                className="grid grid-cols-[minmax(0,1fr)_56px_84px] items-center md:grid-cols-[minmax(0,1fr)_64px_100px_96px_64px] gap-3 border-b border-line py-3 text-[13px]"
              >
                <span className="truncate text-fg">{st?.name}</span>
                <ModeTag mode={s.mode} />
                <span className="hidden md:block">
                  <Spark values={sessionWindow(s).main.slice(-15)} width={96} height={22} />
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
        </div>
        <PanelFoot flush note="Recession Radar holds TLT and GLD, which both fell today.">
          <Button onClick={() => go('/j?s=s-rr')}>Recession Radar session</Button>
          <Button variant="quiet" onClick={() => go('/j/portfolio?v=all')}>
            Holdings
          </Button>
        </PanelFoot>
      </Block>
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
      <Block>
        <PanelHead
          eyebrow="Proposed edit"
          title={`${st.name}, version ${prop.version}`}
          meta={prop.note}
        />
        <div className="mt-[18px]">
          <Figures>
            <Figure label="Total return" sub={b ? `v${st.version} ${pts(b.ret * 100)}` : undefined}>
              <span className={tone(prop.effect.ret)}>{pts(prop.effect.ret * 100)}</span>
            </Figure>
            <Figure
              label="Max drawdown"
              sub={b ? `v${st.version} ${pts(b.worst * 100)}` : undefined}
            >
              {pts(prop.effect.worst * 100)}
            </Figure>
            <Figure label={`Against v${st.version}`} sub="smaller worst drop">
              {b
                ? `${(prop.effect.worst - b.worst) * 100 >= 0 ? '+' : '−'}${Math.abs((prop.effect.worst - b.worst) * 100).toFixed(1)} pts`
                : '·'}
            </Figure>
          </Figures>
        </div>
        <div className="-mx-4 mt-4 border-y border-line md:-mx-5">
          <OutlineView strategy={st} items={items} />
        </div>
        <PanelFoot
          flush
          note="Quick backtest over Nov 2024 to Nov 2026 against the current version."
        >
          <Button
            variant="primary"
            onClick={() => {
              setProposal(st.id, 'applied');
              go(`/j/strategies/${st.id}`);
            }}
          >
            Apply as v{prop.version}
          </Button>
          <Button
            onClick={() => {
              setProposal(st.id, 'open');
              go(`/j/strategies/${st.id}`);
            }}
          >
            Open in builder
          </Button>
          <Button
            variant="quiet"
            onClick={() => {
              setProposal(st.id, 'dismissed');
              setThreadOpen(false);
            }}
          >
            Discard
          </Button>
        </PanelFoot>
      </Block>
    );
  }

  if (turn.artifact === 'draft')
    return (
      <Block>
        <PanelHead
          eyebrow="New draft · quick backtest"
          title={DRAFT.name}
          meta="Nov 2024 to Nov 2026 · $25,000 · benchmark SPY"
        />
        <div className="mt-[18px]">
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
        </div>
        <div className="-mx-4 mt-4 border-y border-line md:-mx-5">
          <OutlineView strategy={DRAFT} items={itemsOf(DRAFT.name, DRAFT.cadence, DRAFT.rules)} />
        </div>
        <PanelFoot
          flush
          note="Quick backtest of the draft. Save it to edit the outline or run a full backtest."
        >
          <Button variant="primary" onClick={() => go('/j/strategies')}>
            Save as draft
          </Button>
          <Button onClick={() => go('/j/backtests')}>Full backtest</Button>
        </PanelFoot>
      </Block>
    );

  if (turn.artifact === 'explain' && turn.strategyId) {
    const st = strategyById(turn.strategyId);
    if (!st) return null;
    const b = lastBacktest(st.id);
    return (
      <Block>
        <PanelHead eyebrow="Outline and last backtest" title={st.name} meta={st.summary} />
        {b && (
          <div className="mt-[18px]">
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
        <div className="-mx-4 mt-4 border-y border-line md:-mx-5">
          <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} />
        </div>
        <PanelFoot
          flush
          note={b ? `Last backtest ran ${b.ran}, ${b.range}.` : 'Not backtested yet.'}
        >
          <Button onClick={() => go(`/j/strategies/${st.id}`)}>Open in builder</Button>
          {b && (
            <Button variant="quiet" onClick={() => go(`/j/backtests/${b.id}`)}>
              Last backtest
            </Button>
          )}
        </PanelFoot>
      </Block>
    );
  }
  return null;
}
