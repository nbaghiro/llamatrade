import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, pnlTone } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { PanelError, StatList } from '../ui';

import {
  etDay,
  fillTitle,
  weekdayLabel,
  type Fill,
  type HomeSession,
  type MarketPhase,
  type ScheduleRow,
} from './homeModel';

export function HomePanel({
  title,
  aside,
  children,
  className = '',
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label={title}
      className={`overflow-hidden rounded-panel border border-line bg-panel ${className}`}
    >
      <div className="flex min-h-[44px] items-center justify-between gap-3 border-b border-line px-4 text-[13px]">
        <b className="font-semibold">{title}</b>
        {aside && <span className="text-[12px] text-fg-3">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

export function SideTag({ side }: { side: Fill['side'] }) {
  return (
    <span className="inline-flex h-[19px] w-[38px] flex-none items-center justify-center rounded-[4px] border border-line font-mono text-[9.5px] font-semibold tracking-[0.05em] text-fg-2">
      {side === 'buy' ? 'BUY' : 'SELL'}
    </span>
  );
}

export function FillsFailed({ onRetry, retrying }: { onRetry: () => void; retrying: boolean }) {
  return (
    <PanelError
      title="Fills couldn't be loaded"
      cause="The trading service didn't answer. Fills are still recorded and will show here once it does."
      onRetry={onRetry}
      retrying={retrying}
    />
  );
}

export function TodayFills({
  fills,
  sessions,
  error,
  onRetry,
  retrying,
}: {
  fills: readonly Fill[];
  sessions: readonly HomeSession[];
  error: boolean;
  onRetry: () => void;
  retrying: boolean;
}) {
  const byId = new Map(sessions.map((s) => [s.id, s]));
  return (
    <HomePanel
      title="Today's fills"
      aside={!error && fills.length > 0 ? `${fills.length} filled` : undefined}
    >
      {error ? (
        <FillsFailed onRetry={onRetry} retrying={retrying} />
      ) : fills.length === 0 ? (
        <p className="m-0 px-4 py-5 text-[13px] text-fg-3">No orders have filled today.</p>
      ) : (
        <ul className="m-0 max-h-[300px] list-none overflow-y-auto p-0">
          {fills.map((f) => {
            const s = byId.get(f.sessionId);
            return (
              <li
                key={f.id}
                className="flex items-center gap-3 border-b border-line px-4 py-2.5 last:border-b-0"
              >
                <SideTag side={f.side} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] text-fg">{fillTitle(f)}</div>
                  <div className="truncate text-[11.5px] text-fg-3">
                    {s ? `${s.name} · ${s.mode}` : 'Session not shown'}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-[12.5px] text-fg">{formatMoney(f.amount)}</div>
                  <div className="font-mono text-[11px] text-fg-3">{etClock(f.at)}</div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </HomePanel>
  );
}

export function BeforeClose({ due, phase }: { due: readonly HomeSession[]; phase: MarketPhase }) {
  return (
    <HomePanel title="Before the close">
      <div className="grid gap-2.5 px-4 py-3.5 text-[13px]">
        {due.map((s) => (
          <div key={s.id} className="flex items-baseline gap-3">
            <Link
              to={s.href}
              className="min-w-0 flex-1 truncate font-medium text-fg hover:underline"
            >
              {s.name} rebalances today
            </Link>
            {s.state === 'frozen' && (
              <span className="text-[12px] text-risk">Waits for review</span>
            )}
          </div>
        ))}
        {due.length === 0 && (
          <p className="m-0 text-fg-3">No rebalances are scheduled for today.</p>
        )}
        <div className="flex items-baseline gap-3 border-t border-line pt-2.5 text-fg-2">
          <span className="flex-1">The market closes</span>
          <span className="font-mono text-[12.5px]">{phase.closeClock} ET</span>
        </div>
      </div>
    </HomePanel>
  );
}

const valueTone = (v: number) =>
  pnlTone(v) === 'gain' ? 'gain' : pnlTone(v) === 'loss' ? 'loss' : undefined;

export function TodayBySession({ sessions }: { sessions: readonly HomeSession[] }) {
  const rows = [...sessions].sort((a, b) => (b.today ?? -Infinity) - (a.today ?? -Infinity));
  return (
    <HomePanel
      title="Today by session"
      aside={
        <Link to="/trading" className="text-accent hover:underline">
          All sessions
        </Link>
      }
    >
      <div className="px-4 py-1.5">
        {rows.length === 0 ? (
          <p className="m-0 py-3.5 text-[13px] text-fg-3">No sessions in this account.</p>
        ) : (
          <StatList
            items={rows.map((s) => ({
              label: s.name,
              value:
                s.state === 'stopped' || s.state === 'error'
                  ? 'Stopped'
                  : s.today === null
                    ? 'No figure yet'
                    : formatMoney(s.today, { signed: true }),
              tone: s.today === null || s.state === 'stopped' ? undefined : valueTone(s.today),
            }))}
          />
        )}
      </div>
    </HomePanel>
  );
}

function closedMeta(s: HomeSession, fills: number): string {
  const kind = s.mode === 'live' ? 'Live' : 'Paper';
  if (s.state === 'stopped' || s.state === 'error') return `${kind} · stopped`;
  if (s.state === 'frozen') return `${kind} · frozen, prices still move`;
  if (s.state === 'paused') return `${kind} · paused`;
  return `${kind} · ${fills ? `${fills} ${fills === 1 ? 'fill' : 'fills'}` : 'no fills'}`;
}

/** home/quiet A: what each session added to the last trading day. */
export function HowTodayClosed({
  sessions,
  fills,
}: {
  sessions: readonly HomeSession[];
  fills: readonly Fill[];
}) {
  const rows = [...sessions].sort((a, b) => (b.today ?? -Infinity) - (a.today ?? -Infinity));
  const max = Math.max(1e-9, ...rows.map((s) => Math.abs(s.today ?? 0)));
  return (
    <HomePanel title="How the day closed" aside="Change by session">
      {rows.length === 0 ? (
        <p className="m-0 px-4 py-5 text-[13px] text-fg-3">No sessions in this account.</p>
      ) : (
        <ul className="m-0 list-none p-0">
          {rows.map((s) => {
            const t = s.today ?? 0;
            const n = fills.filter((f) => f.sessionId === s.id).length;
            return (
              <li
                key={s.id}
                className="grid grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_auto] items-center gap-4 border-b border-line px-4 py-2.5 last:border-b-0"
              >
                <div className="min-w-0">
                  <Link
                    to={s.href}
                    className="block truncate text-[13px] font-medium text-fg hover:underline"
                  >
                    {s.name}
                  </Link>
                  <div className="truncate text-[11.5px] text-fg-3">{closedMeta(s, n)}</div>
                </div>
                <div className="h-1.5">
                  <i
                    aria-hidden="true"
                    className={`block h-full rounded-full ${t < 0 ? 'bg-loss/60' : 'bg-accent/70'}`}
                    style={{ width: `${Math.max(0.5, (Math.abs(t) / max) * 100)}%` }}
                  />
                </div>
                <span
                  className={`text-right font-mono text-[12.5px] ${s.today === null ? 'text-fg-3' : t > 0 ? 'text-gain' : t < 0 ? 'text-loss' : 'text-fg-2'}`}
                >
                  {s.today === null ? 'No figure' : formatMoney(t, { signed: true })}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </HomePanel>
  );
}

function rowText(r: ScheduleRow): ReactNode {
  if (r.kind === 'closed') return `Closed for ${r.name ?? 'a market holiday'}.`;
  if (r.kind === 'early') return `The market closes early at 13:00 (${r.name ?? 'early close'}).`;
  const frozen = r.sessions.filter((s) => s.state === 'frozen');
  const names = r.sessions.map((s) => s.name);
  const list =
    names.length <= 2
      ? names.join(' and ')
      : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
  return (
    <>
      {list} {names.length === 1 ? 'rebalances' : 'rebalance'}.
      {frozen.length > 0 && (
        <span className="text-risk">
          {' '}
          {frozen.length === 1 ? `${frozen[0].name} waits` : 'Frozen sessions wait'} until the
          difference with Alpaca is reviewed.
        </span>
      )}
    </>
  );
}

/** home/quiet A: when the market opens, then what is scheduled, including holidays. */
export function NextList({ rows, phase }: { rows: readonly ScheduleRow[]; phase: MarketPhase }) {
  return (
    <HomePanel title="Next" aside="Next two weeks">
      <ul className="m-0 list-none px-4 py-1 text-[13px]">
        {phase.nextOpen && (
          <li className="flex gap-4 border-b border-line py-2.5">
            <span className="w-[86px] flex-none font-mono text-[12px] text-fg-3">
              {weekdayLabel(etDay(phase.nextOpen)).slice(0, 3)} 09:30
            </span>
            <span className="text-fg">The market opens.</span>
          </li>
        )}
        {rows.slice(0, 6).map((r) => (
          <li
            key={`${r.kind}-${r.day.getTime()}`}
            className="flex gap-4 border-b border-line py-2.5 last:border-b-0"
          >
            <span className="w-[86px] flex-none font-mono text-[12px] text-fg-3">
              {weekdayLabel(r.day)}
            </span>
            <span className="min-w-0 text-fg">{rowText(r)}</span>
          </li>
        ))}
        {rows.length === 0 && (
          <li className="py-2.5 text-fg-3">No rebalances are scheduled in the next two weeks.</li>
        )}
      </ul>
    </HomePanel>
  );
}
