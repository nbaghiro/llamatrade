import { Fragment, useState } from 'react';
import { Link } from 'react-router-dom';

import { signedUsd, stateLabel, usd, type Strategy } from '../data';

import { useAsk } from './askContext';
import { activeSession, lastBacktest, pts, strategySpark, tone } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import { Button, Chevron, Delta, Label, LinkButton, ModeTag, Spark } from './ui';

const COLS =
  'grid-cols-[22px_minmax(0,1fr)_90px] md:grid-cols-[22px_minmax(0,1fr)_120px_120px_112px_84px_150px]';

export function LedgerHead({ spark = 'Since start' }: { spark?: string }) {
  return (
    <div
      className={`grid ${COLS} items-end gap-4 border-b border-line pb-2 text-[11.5px] font-medium text-fg-3`}
    >
      <span />
      <span>Strategy</span>
      <span className="hidden md:block">{spark}</span>
      <span className="hidden text-right md:block">Value</span>
      <span className="text-right">Today</span>
      <span className="hidden md:block">Mode</span>
      <span className="hidden md:block">Next</span>
    </div>
  );
}

function Expanded({ s }: { s: Strategy }) {
  const { ask } = useAsk();
  const b = lastBacktest(s.id);
  const ses = activeSession(s.id);
  return (
    <div className="grid gap-6 border-b border-line py-6 pl-0 pr-0 md:grid-cols-[minmax(0,1fr)_300px] md:pl-[38px]">
      <div className="min-w-0 overflow-x-auto border-y border-line">
        <OutlineView strategy={s} items={itemsOf(s.name, s.cadence, s.rules)} />
      </div>
      <div className="grid content-start gap-4 px-4 md:px-0 md:pr-4">
        <div>
          <Label>Last backtest</Label>
          {b ? (
            <>
              <div className="mt-1 flex items-baseline gap-3">
                <span
                  className={`font-mono text-[26px] tracking-[-0.03em] tabular-nums ${tone(b.ret)}`}
                >
                  {pts(b.ret * 100)}
                </span>
                <span className="font-mono text-[11.5px] tabular-nums text-fg-3">
                  SPY {pts(b.spy * 100)}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-2 border-y border-line font-mono text-[12.5px] tabular-nums">
                <div className="py-2">
                  <Label className="block font-sans">Max drawdown</Label>
                  {pts(b.worst * 100)}
                </div>
                <div className="border-l border-line py-2 pl-3">
                  <Label className="block font-sans">Sharpe</Label>
                  {b.sharpe.toFixed(2)}
                </div>
              </div>
              <div className="mt-2 text-[11.5px] text-fg-3">
                v{b.version} · {b.range} · ran {b.ran}
              </div>
            </>
          ) : (
            <p className="m-0 mt-1 text-[13px] text-fg-2">Not backtested yet.</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <LinkButton to={b ? `/d/backtests/${b.id}` : '/d/backtests'} variant="primary">
            Backtest
          </LinkButton>
          {ses ? (
            <LinkButton to={`/d/sessions/${ses.id}`}>Open session</LinkButton>
          ) : (
            <Button>Start session</Button>
          )}
          <Button variant="quiet" onClick={() => ask(`Explain ${s.name}`, s.id)}>
            Ask
          </Button>
        </div>
        <Link to={`/d/strategies/${s.id}`} className="text-[12.5px] text-fg-2 hover:text-fg">
          Open in builder →
        </Link>
      </div>
    </div>
  );
}

/** Strategies as ledger rows that open in place to their outline, last backtest and actions. */
export function StrategyLedger({
  rows,
  initiallyOpen,
}: {
  rows: Strategy[];
  initiallyOpen?: string;
}) {
  const [open, setOpen] = useState<string | null>(initiallyOpen ?? null);
  return (
    <div>
      {rows.map((s) => {
        const ses = activeSession(s.id);
        const spark = strategySpark(s);
        const isOpen = open === s.id;
        return (
          <Fragment key={s.id}>
            <div
              role="button"
              tabIndex={0}
              aria-expanded={isOpen}
              onClick={() => setOpen(isOpen ? null : s.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setOpen(isOpen ? null : s.id);
                }
              }}
              className={`grid ${COLS} cursor-pointer items-center gap-4 border-b border-line py-3 transition-colors hover:bg-panel/70 ${isOpen ? 'bg-panel/60' : ''}`}
            >
              <span className="grid h-5 w-5 place-items-center text-fg-3">
                <Chevron open={isOpen} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[14.5px] font-medium text-fg">{s.name}</span>
                <span className="block truncate text-[12.5px] text-fg-3">
                  v{s.version} · {s.cadence} · {stateLabel(s)}
                </span>
              </span>
              <span className="hidden md:block">
                {spark ? (
                  <Spark values={spark} width={112} height={26} />
                ) : (
                  <span className="text-[12px] text-fg-3">No history</span>
                )}
              </span>
              <span className="hidden text-right font-mono text-[13.5px] tabular-nums text-fg md:block">
                {ses ? usd(ses.value) : ''}
              </span>
              <span className="text-right">
                {ses ? (
                  <Delta v={ses.today} className="text-[13.5px]">
                    {signedUsd(ses.today)}
                  </Delta>
                ) : (
                  <span />
                )}
              </span>
              <span className="hidden md:block">
                {ses ? (
                  <ModeTag mode={ses.mode} />
                ) : (
                  <span className="text-[12.5px] text-fg-3">Off</span>
                )}
              </span>
              <span className="hidden truncate text-[12.5px] text-fg-2 md:block">
                {ses?.next ?? (s.state === 'draft' ? 'Finish the draft' : 'Not running')}
              </span>
            </div>
            {isOpen && <Expanded s={s} />}
          </Fragment>
        );
      })}
    </div>
  );
}
