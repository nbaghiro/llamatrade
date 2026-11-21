import { Fragment, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { signedUsd, usd, type Strategy } from '../data';

import { useCopilot } from './copilotContext';
import { useListNav } from './keys';
import { activeSession, lastBacktest, pts, strategySpark, to, tone } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import { rowClass } from './styles';
import { Button, Caret, Delta, LinkButton, ModeTag, Mono, Spark, TableHead } from './ui';

const NARROW =
  'grid-cols-[16px_minmax(0,1fr)_84px] md:grid-cols-[16px_minmax(0,1fr)_64px_96px_104px_88px_minmax(0,150px)]';
const WIDE =
  'grid-cols-[16px_minmax(0,1fr)_84px] md:grid-cols-[16px_minmax(0,1fr)_72px_64px_96px_104px_88px_72px_64px_minmax(0,140px)]';

function Expanded({ s }: { s: Strategy }) {
  const { openBar } = useCopilot();
  const b = lastBacktest(s.id);
  const ses = activeSession(s.id);
  return (
    <div className="grid gap-3 border-b border-line bg-panel/50 p-3 md:grid-cols-[minmax(0,1fr)_240px]">
      <div className="min-w-0 overflow-x-auto rounded-[6px] border border-line bg-canvas">
        <OutlineView strategy={s} items={itemsOf(s.name, s.cadence, s.rules)} compact />
      </div>
      <div className="grid content-start gap-3">
        <div className="rounded-[6px] border border-line bg-canvas">
          <div className="flex h-8 items-center justify-between border-b border-line px-3">
            <Mono className="text-fg-3">Last backtest</Mono>
            {b && (
              <span className="font-mono text-[10.5px] text-fg-3">
                v{b.version} · {b.ran}
              </span>
            )}
          </div>
          {b ? (
            <div className="grid grid-cols-3 font-mono text-[12px] tabular-nums">
              <div className="px-3 py-2">
                <div className={tone(b.ret)}>{pts(b.ret * 100)}</div>
                <div className="text-[10.5px] text-fg-3">SPY {pts(b.spy * 100)}</div>
              </div>
              <div className="border-l border-line px-3 py-2">
                <div className="text-fg">{pts(b.worst * 100)}</div>
                <div className="text-[10.5px] text-fg-3">worst</div>
              </div>
              <div className="border-l border-line px-3 py-2">
                <div className="text-fg">{b.sharpe.toFixed(2)}</div>
                <div className="text-[10.5px] text-fg-3">sharpe</div>
              </div>
            </div>
          ) : (
            <p className="m-0 px-3 py-2 text-[12.5px] text-fg-3">Not backtested yet.</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <LinkButton to={to(`/strategies/${s.id}`)} variant="primary" k="e">
            Edit
          </LinkButton>
          {ses ? (
            <LinkButton to={to(`/sessions/${ses.id}`)} k="↵">
              Session
            </LinkButton>
          ) : (
            <LinkButton to={b ? to(`/backtests/${b.id}`) : to('/backtests')}>Backtest</LinkButton>
          )}
          <Button variant="quiet" onClick={() => openBar(s.id)}>
            Ask
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Strategies with their sessions on 32px rows; j/k to move, enter opens, e edits, space previews. */
export function Ledger({
  rows,
  wide = false,
  initiallyOpen,
}: {
  rows: Strategy[];
  wide?: boolean;
  initiallyOpen?: string;
}) {
  const nav = useNavigate();
  const [open, setOpen] = useState<string | null>(initiallyOpen ?? null);
  const openRow = useCallback(
    (i: number) => {
      const s = rows[i];
      if (!s) return;
      const ses = activeSession(s.id);
      nav(ses ? to(`/sessions/${ses.id}`) : to(`/strategies/${s.id}`));
    },
    [rows, nav]
  );
  const edit = useCallback(
    (i: number) => rows[i] && nav(to(`/strategies/${rows[i].id}`)),
    [rows, nav]
  );
  const toggle = useCallback(
    (i: number) => {
      const id = rows[i]?.id;
      if (id) setOpen((o) => (o === id ? null : id));
    },
    [rows]
  );
  const [sel, setSel] = useListNav(rows.length, { open: openRow, edit, toggle });
  const cols = wide ? WIDE : NARROW;

  return (
    <div>
      <TableHead cols={cols}>
        <span />
        <span>Strategy</span>
        {wide && <span className="hidden md:block">Cadence</span>}
        <span className="hidden md:block">Mode</span>
        <span className="hidden md:block">Since start</span>
        <span className="hidden text-right md:block">Value</span>
        <span className="text-right">Today</span>
        {wide && <span className="hidden text-right md:block">Backtest</span>}
        {wide && <span className="hidden text-right md:block">Worst</span>}
        <span className="hidden md:block">Next</span>
      </TableHead>
      {rows.map((s, i) => {
        const ses = activeSession(s.id);
        const b = lastBacktest(s.id);
        const spark = strategySpark(s);
        const isOpen = open === s.id;
        return (
          <Fragment key={s.id}>
            <div
              role="row"
              aria-selected={i === sel}
              onMouseEnter={() => setSel(i)}
              onClick={() => toggle(i)}
              onDoubleClick={() => openRow(i)}
              className={`${rowClass(i === sel)} ${cols}`}
            >
              <span className="grid place-items-center text-fg-3">
                <Caret open={isOpen} />
              </span>
              <span className="flex min-w-0 items-baseline gap-2">
                <span className="truncate font-medium text-fg">{s.name}</span>
                <span className="flex-none font-mono text-[10.5px] text-fg-3">v{s.version}</span>
                {s.state === 'draft' && <Mono className="flex-none text-fg-3">draft</Mono>}
              </span>
              {wide && (
                <span className="hidden font-mono text-[11.5px] text-fg-3 md:block">
                  {s.cadence}
                </span>
              )}
              <span className="hidden md:block">
                <ModeTag mode={ses?.mode} />
              </span>
              <span className="hidden md:block">
                {spark ? (
                  <Spark values={spark} width={88} height={18} />
                ) : (
                  <span className="font-mono text-[11px] text-fg-3">no history</span>
                )}
              </span>
              <span className="hidden text-right font-mono text-[12.5px] tabular-nums text-fg md:block">
                {ses ? usd(ses.value) : <span className="text-fg-3">·</span>}
              </span>
              <span className="text-right">
                {ses ? (
                  <Delta v={ses.today} className="text-[12.5px]">
                    {signedUsd(ses.today)}
                  </Delta>
                ) : (
                  <span className="font-mono text-[12px] text-fg-3">·</span>
                )}
              </span>
              {wide && (
                <span
                  className={`hidden text-right font-mono text-[12px] tabular-nums md:block ${b ? tone(b.ret) : 'text-fg-3'}`}
                >
                  {b ? pts(b.ret * 100) : '·'}
                </span>
              )}
              {wide && (
                <span className="hidden text-right font-mono text-[12px] tabular-nums text-fg-2 md:block">
                  {b ? pts(b.worst * 100) : '·'}
                </span>
              )}
              <span className="hidden truncate text-[12px] text-fg-2 md:block">
                {ses?.next ??
                  (s.state === 'draft'
                    ? 'Finish the draft'
                    : s.state === 'stopped'
                      ? `Stopped ${s.stoppedOn}`
                      : 'Never run')}
              </span>
            </div>
            {isOpen && <Expanded s={s} />}
          </Fragment>
        );
      })}
    </div>
  );
}
