import { ChevronRight } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, formatPct, pnlTone } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { Sparkline } from '../charts';
import { useWidth } from '../charts/useWidth';

import type { HeroFigures } from './HomeHead';
import { Chg, Label } from './HomeHead';
import {
  dayLabel,
  etDay,
  fillTitle,
  type EquitySeries,
  type Fill,
  type HomeSession,
  type MarketPhase,
  type ScheduleRow,
} from './homeModel';
import { FillsFailed, SideTag } from './HomePanels';

function Section({
  title,
  link,
  children,
}: {
  title: string;
  link?: { to: string; label: string };
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title} className="grid gap-2">
      <div className="flex items-baseline justify-between px-0.5">
        <h2 className="m-0 text-[15px] font-semibold">{title}</h2>
        {link && (
          <Link to={link.to} className="text-[13px] text-accent">
            {link.label}
          </Link>
        )}
      </div>
      <div className="overflow-hidden rounded-panel border border-line bg-panel">{children}</div>
    </section>
  );
}

function stateWords(s: HomeSession, today: Date, due: ReadonlySet<string>): string {
  const kind = s.mode === 'live' ? 'Live' : 'Paper';
  if (s.state === 'frozen') return `${kind} · frozen`;
  if (s.state === 'stopped' || s.state === 'error')
    return `${kind} · stopped${s.stoppedAt ? ` ${dayLabel(etDay(s.stoppedAt))}` : ''}`;
  if (s.state === 'paused') return `${kind} · paused`;
  if (due.has(s.id) && today) return `${kind} · rebalances today`;
  return `${kind} · running`;
}

function WideSpark({ values }: { values: readonly number[] }) {
  const [ref, width] = useWidth<HTMLDivElement>(340);
  return (
    <div ref={ref}>
      <Sparkline values={values} width={width} height={92} label="Account equity" />
    </div>
  );
}

/** home/phone B: the total and today, then one row per session, today's fills and what's next. */
export function HomePhone({
  figures,
  series,
  sessions,
  dueToday,
  fills,
  fillsError,
  onRetryFills,
  retrying,
  schedule,
  phase,
  now,
}: {
  figures: HeroFigures;
  series: EquitySeries;
  sessions: readonly HomeSession[];
  dueToday: readonly HomeSession[];
  fills: readonly Fill[];
  fillsError: boolean;
  onRetryFills: () => void;
  retrying: boolean;
  schedule: readonly ScheduleRow[];
  phase: MarketPhase;
  now: Date;
}) {
  const topRef = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const el = topRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([e]) => setScrolled(!e.isIntersecting), {
      rootMargin: '-56px 0px 0px 0px',
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const due = new Set(dueToday.map((s) => s.id));
  const recent = series.values.slice(-90);
  const byId = new Map(sessions.map((s) => [s.id, s]));

  return (
    <div className="grid gap-5 pb-16 md:hidden">
      {scrolled && (
        <div className="fixed inset-x-0 top-14 z-30 flex items-center gap-2.5 border-b border-line bg-canvas/95 px-4 py-2.5 backdrop-blur">
          <span className="font-mono text-[16px] font-semibold">{formatMoney(figures.total)}</span>
          {figures.todayPct !== null && (
            <span
              className={`font-mono text-[13px] ${pnlTone(figures.todayPct * 100) === 'loss' ? 'text-loss' : pnlTone(figures.todayPct * 100) === 'gain' ? 'text-gain' : 'text-fg-3'}`}
            >
              {formatPct(figures.todayPct, { signed: true })}
            </span>
          )}
        </div>
      )}
      <div ref={topRef}>
        <Label>
          {phase.open ? 'Total equity' : 'Equity at the close'} · {figures.kinds}
        </Label>
        <div className="mt-1.5 font-mono text-[32px] font-semibold leading-none tracking-[-0.04em]">
          {formatMoney(figures.total)}
        </div>
        {figures.today !== null && (
          <div className="mt-2 flex items-center gap-1.5">
            <Chg value={figures.today}>{formatMoney(figures.today, { signed: true })}</Chg>
            {figures.todayPct !== null && (
              <Chg value={figures.todayPct * 100}>
                {formatPct(figures.todayPct, { signed: true })}
              </Chg>
            )}
            <span className="text-[13px] text-fg-3">today</span>
          </div>
        )}
        {figures.staleSince && (
          <div className="mt-2 flex items-center gap-2 text-[12.5px] text-fg-2">
            From {etClock(figures.staleSince)}. Couldn&apos;t refresh.
            <button type="button" onClick={figures.onRetry} className="text-accent">
              Try again
            </button>
          </div>
        )}
      </div>
      {recent.length > 1 && <WideSpark values={recent} />}
      <Link
        to="/portfolio/activity"
        className="-mt-2 inline-flex items-center gap-1 justify-self-start text-[13.5px] text-fg-2 hover:text-fg"
      >
        Cash and every fill
        <ChevronRight aria-hidden="true" className="h-4 w-4 text-fg-3" />
      </Link>

      <Section title="Sessions" link={{ to: '/trading', label: 'See all' }}>
        {sessions.length === 0 ? (
          <p className="m-0 px-4 py-4 text-[14px] text-fg-3">No sessions in this account.</p>
        ) : (
          <ul className="m-0 list-none p-0">
            {sessions.map((s) => {
              const stopped = s.state === 'stopped' || s.state === 'error';
              return (
                <li key={s.id} className="border-b border-line last:border-b-0">
                  <Link to={s.href} className="flex items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div
                        className={`truncate text-[14.5px] font-semibold ${stopped ? 'text-fg-2' : 'text-fg'}`}
                      >
                        {s.name}
                      </div>
                      <div
                        className={`truncate text-[12.5px] ${s.state === 'frozen' ? 'text-risk' : 'text-fg-3'}`}
                      >
                        {stateWords(s, now, due)}
                      </div>
                    </div>
                    <Sparkline
                      values={s.curve}
                      width={62}
                      height={24}
                      tone={stopped ? 'neutral' : 'accent'}
                    />
                    <div className="w-[92px] flex-none text-right">
                      <div className="font-mono text-[13px]">
                        {s.value === null ? 'No value' : formatMoney(s.value)}
                      </div>
                      <div
                        className={`font-mono text-[12px] ${s.todayPct === null || stopped ? 'text-fg-3' : pnlTone(s.todayPct * 100) === 'gain' ? 'text-gain' : pnlTone(s.todayPct * 100) === 'loss' ? 'text-loss' : 'text-fg-3'}`}
                      >
                        {s.todayPct === null || stopped
                          ? '0.00%'
                          : formatPct(s.todayPct, { signed: true })}
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section
        title={phase.open ? 'Today' : 'Last session'}
        link={{ to: '/portfolio/activity', label: 'History' }}
      >
        {fillsError ? (
          <FillsFailed onRetry={onRetryFills} retrying={retrying} />
        ) : fills.length === 0 ? (
          <p className="m-0 px-4 py-4 text-[14px] text-fg-3">No orders filled.</p>
        ) : (
          <ul className="m-0 list-none p-0">
            {fills.slice(0, 6).map((f) => (
              <li
                key={f.id}
                className="flex items-center gap-3 border-b border-line px-4 py-3 last:border-b-0"
              >
                <SideTag side={f.side} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[14px]">{fillTitle(f)}</div>
                  <div className="truncate text-[12.5px] text-fg-3">
                    {byId.get(f.sessionId)?.name ?? 'Session'} · {etClock(f.at)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Next">
        <ul className="m-0 list-none p-0 text-[14px]">
          {phase.open &&
            dueToday.map((s) => (
              <li key={s.id} className="flex gap-3 border-b border-line px-4 py-3">
                <span className="w-[54px] flex-none font-mono text-[12px] text-fg-3">Today</span>
                <span>{s.name} rebalances</span>
              </li>
            ))}
          {phase.open && (
            <li className="flex gap-3 border-b border-line px-4 py-3">
              <span className="w-[54px] flex-none font-mono text-[12px] text-fg-3">
                {phase.closeClock}
              </span>
              <span>The market closes</span>
            </li>
          )}
          {!phase.open && phase.nextOpen && (
            <li className="flex gap-3 border-b border-line px-4 py-3">
              <span className="w-[54px] flex-none font-mono text-[12px] text-fg-3">
                {dayLabel(etDay(phase.nextOpen))}
              </span>
              <span>The market opens at 09:30 ET</span>
            </li>
          )}
          {schedule.slice(0, 4).map((r) => (
            <li
              key={`${r.kind}-${r.day.getTime()}`}
              className="flex gap-3 border-b border-line px-4 py-3 last:border-b-0"
            >
              <span className="w-[54px] flex-none font-mono text-[12px] text-fg-3">
                {dayLabel(r.day)}
              </span>
              <span className="min-w-0">
                {r.kind === 'closed'
                  ? `Closed for ${r.name ?? 'a holiday'}`
                  : r.kind === 'early'
                    ? 'Closes early at 13:00'
                    : r.sessions.length === 1
                      ? `${r.sessions[0].name} rebalances`
                      : `${r.sessions.length} sessions rebalance`}
                {r.sessions.some((s) => s.state === 'frozen') && (
                  <span className="text-risk"> · waits on review</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
