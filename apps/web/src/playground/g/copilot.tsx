import { useNavigate } from 'react-router-dom';

import { ACCOUNT, pct, SESSIONS, signedUsd, strategyById } from '../data';

import { useAsk, type Turn } from './askContext';
import { DRAFT, lastBacktest, PROPOSALS, pts, sessionWindow, tone } from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf } from './outlineModel';
import {
  Button,
  Delta,
  Figure,
  Figures,
  ModeTag,
  PanelFoot,
  PanelHead,
  Spark,
  StageCard,
} from './ui';

function Close() {
  const { stage } = useAsk();
  return (
    <Button variant="quiet" onClick={() => stage(null)} aria-label="Close and go back to the page">
      Close
    </Button>
  );
}

/** What a Copilot reply made, on the stage in place of the page's panel. */
export function ArtifactPanel({ turn }: { turn: Turn }) {
  const nav = useNavigate();
  const { setProposal, stage } = useAsk();
  const go = (to: string) => {
    stage(null);
    nav(to);
  };

  if (turn.artifact === 'today')
    return (
      <StageCard>
        <PanelHead
          eyebrow="From Copilot"
          title="Today by session"
          meta={`Account ${signedUsd(ACCOUNT.today)} · prices Nov 20, 12:04 ET`}
          right={<Close />}
        />
        <div className="mt-[18px] border-t border-line">
          {SESSIONS.filter((s) => !s.stoppedOn).map((s) => {
            const st = strategyById(s.strategyId);
            return (
              <div
                key={s.id}
                className="grid grid-cols-[minmax(0,1fr)_64px_100px_96px_64px] items-center gap-3 border-b border-line py-3 text-[13px]"
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
        </div>
        <PanelFoot note="Recession Radar holds TLT and GLD, which both fell today.">
          <Button onClick={() => go('/g?s=s-rr')}>Recession Radar session</Button>
          <Button variant="quiet" onClick={() => go('/g/portfolio?v=all')}>
            Holdings
          </Button>
        </PanelFoot>
      </StageCard>
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
      <StageCard>
        <PanelHead
          eyebrow="From Copilot · proposed edit"
          title={`${st.name}, version ${prop.version}`}
          meta={prop.note}
          right={<Close />}
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
        <div className="-mx-5 mt-[18px] border-y border-line md:-mx-7 md:px-2">
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
              go(`/g/strategies/${st.id}`);
            }}
          >
            Apply as v{prop.version}
          </Button>
          <Button
            onClick={() => {
              setProposal(st.id, 'open');
              go(`/g/strategies/${st.id}`);
            }}
          >
            Open in builder
          </Button>
          <Button
            variant="quiet"
            onClick={() => {
              setProposal(st.id, 'dismissed');
              stage(null);
            }}
          >
            Discard
          </Button>
        </PanelFoot>
      </StageCard>
    );
  }

  if (turn.artifact === 'draft')
    return (
      <StageCard>
        <PanelHead
          eyebrow="From Copilot · new draft"
          title={DRAFT.name}
          meta="Nov 2024 to Nov 2026 · $25,000 · benchmark SPY"
          right={<Close />}
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
        <div className="-mx-5 mt-[18px] border-y border-line md:-mx-7 md:px-2">
          <OutlineView strategy={DRAFT} items={itemsOf(DRAFT.name, DRAFT.cadence, DRAFT.rules)} />
        </div>
        <PanelFoot
          flush
          note="Quick backtest of the draft. Save it to edit the outline or run a full backtest."
        >
          <Button variant="primary" onClick={() => go('/g/strategies')}>
            Save as draft
          </Button>
          <Button onClick={() => go('/g/backtests')}>Full backtest</Button>
        </PanelFoot>
      </StageCard>
    );

  if (turn.artifact === 'explain' && turn.strategyId) {
    const st = strategyById(turn.strategyId);
    if (!st) return null;
    const b = lastBacktest(st.id);
    return (
      <StageCard>
        <PanelHead eyebrow="From Copilot" title={st.name} meta={st.summary} right={<Close />} />
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
        <div className="-mx-5 mt-[18px] border-y border-line md:-mx-7 md:px-2">
          <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} />
        </div>
        <PanelFoot
          flush
          note={b ? `Last backtest ran ${b.ran}, ${b.range}.` : 'Not backtested yet.'}
        >
          <Button onClick={() => go(`/g/strategies/${st.id}`)}>Open in builder</Button>
          {b && (
            <Button variant="quiet" onClick={() => go(`/g/backtests/${b.id}`)}>
              Last backtest
            </Button>
          )}
        </PanelFoot>
      </StageCard>
    );
  }
  return null;
}
