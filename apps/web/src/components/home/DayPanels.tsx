import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import { marketDay } from '../../lib/marketHolidays';
import { useWidth } from '../charts/useWidth';
import { CopilotMark } from '../common/Logo';

import { movedSummary, type NextEntry } from './dayModel';
import { dayLabel, signedPct, toneFill, type HomeSession, type MarketPhase } from './homeModel';
import { HomeCard } from './HomePanels';

const DAY = 86_400_000;
const AX = 'fill-fg-3 font-mono text-[11px]';
const done = (s: HomeSession) => s.state === 'stopped' || s.state === 'error';
const shortName = (name: string) => name.replace(/ Portfolio$/, '');

export interface MovedProps {
  sessions: readonly HomeSession[];
  today: number | null;
  todayPct: number | null;
  /** SPY's move on the day, as a fraction. */
  spy: number | null;
  phase: MarketPhase;
  /** "today", or "on Friday" when the last close was on an earlier day. */
  when: string;
  hotSession: string | null;
  onHover: (sessionId: string | null) => void;
}

/** home/moved: each running session's change on the day, in dollars and as a share, against SPY. */
export function MovedToday({
  sessions,
  today,
  todayPct,
  spy,
  phase,
  when,
  hotSession,
  onHover,
}: MovedProps) {
  const [ref, W] = useWidth<HTMLDivElement>(560);
  const rows = sessions
    .filter((s) => !done(s) && s.today !== null && s.todayPct !== null)
    .map((s) => ({ s, usd: s.today ?? 0, pct: (s.todayPct ?? 0) * 100 }))
    .sort((a, b) => a.usd - b.usd);
  const spyPct = spy === null ? null : spy * 100;
  const accPct = todayPct === null ? null : todayPct * 100;
  const maxUsd = Math.max(...rows.map((r) => Math.abs(r.usd)), 1) * 1.12;
  const maxPct = Math.max(
    1,
    Math.ceil(Math.abs(spyPct ?? 0)),
    Math.ceil(Math.abs(accPct ?? 0)),
    ...rows.map((r) => Math.ceil(Math.abs(r.pct)))
  );
  const Hh = 52 + (rows.length + 1) * 28;
  const nameW = Math.min(150, W * 0.26);
  const mid = nameW + (W - nameW) * 0.45;
  const barL = nameW;
  const barR = barL + (W - nameW) * 0.3;
  const pL = mid + 60;
  const pR = W - 56;
  const pZero = (pL + pR) / 2;
  const rowY = (k: number) => 32 + k * 28;
  const bx = (v: number) => barR - (Math.abs(v) / maxUsd) * (barR - barL);
  const px = (v: number) => pZero + (v / maxPct) * ((pR - pL) / 2);
  const bt = Hh - 24;
  const ty = rowY(rows.length) + 2;
  const title = phase.open ? 'What moved today' : 'How the day closed';
  return (
    <HomeCard title={title} sub="By session, against SPY">
      {rows.length === 0 ? (
        <p className="m-0 px-5 py-6 text-[13px] text-fg-3">
          No running session has a figure for {when} yet. Figures appear once Alpaca reports the
          day&apos;s values.
        </p>
      ) : (
        <div className="px-5 pt-2" ref={ref} onMouseLeave={() => onHover(null)}>
          <svg
            viewBox={`0 0 ${W} ${Hh}`}
            height={Hh}
            className="block w-full overflow-visible"
            role="img"
            aria-label={`Change by session ${when}`}
          >
            <text className={AX} x={barR} y="10" textAnchor="end">
              Dollars
            </text>
            <text className={AX} x={pR} y="10" textAnchor="end">
              Percent of session
            </text>
            <line className="stroke-line-strong" x1={barR} x2={barR} y1="18" y2={bt} />
            <line className="stroke-line-strong" x1={px(0)} x2={px(0)} y1="18" y2={bt} />
            <text className={AX} x={px(0)} y={Hh - 6} textAnchor="middle">
              0%
            </text>
            {spyPct !== null && (
              <>
                <line
                  className="stroke-fg-3 [stroke-dasharray:3_3]"
                  x1={px(spyPct)}
                  x2={px(spyPct)}
                  y1="18"
                  y2={bt}
                />
                <text
                  className={AX}
                  x={px(spyPct) + (spyPct < 0 ? -4 : 4)}
                  y={Hh - 6}
                  textAnchor={spyPct < 0 ? 'end' : 'start'}
                >
                  SPY {signedPct(spyPct)}
                </text>
              </>
            )}
            {rows.map((r, k) => {
              const yy = rowY(k);
              const hot = hotSession === r.s.id;
              const tone = toneFill(r.usd);
              return (
                <g key={r.s.id} onMouseEnter={() => onHover(r.s.id)}>
                  <rect x="0" y={yy - 13} width={W} height="26" fill="transparent" />
                  <text
                    className={`text-[12.5px] ${hot ? 'fill-fg font-medium' : 'fill-fg-2'}`}
                    x="0"
                    y={yy + 4}
                  >
                    {shortName(r.s.name).slice(0, 22)}
                  </text>
                  <rect
                    className={hot ? 'fill-fg' : 'fill-fg-3'}
                    x={bx(r.usd)}
                    y={yy - 5}
                    width={barR - bx(r.usd)}
                    height="10"
                    rx="1.5"
                  />
                  <text className={`font-mono text-[11.5px] ${tone}`} x={barR + 8} y={yy + 4}>
                    {formatMoney(r.usd, { signed: true })}
                  </text>
                  <line className="stroke-line-strong" x1={px(0)} x2={px(r.pct)} y1={yy} y2={yy} />
                  <circle
                    className={hot ? 'fill-accent' : 'fill-fg'}
                    cx={px(r.pct)}
                    cy={yy}
                    r="4"
                  />
                  <text
                    className={`font-mono text-[11.5px] ${tone}`}
                    x={W}
                    y={yy + 4}
                    textAnchor="end"
                  >
                    {signedPct(r.pct)}
                  </text>
                </g>
              );
            })}
            <line className="stroke-line" x1="0" x2={W} y1={ty - 14} y2={ty - 14} />
            <text className="fill-fg text-[12.5px] font-medium" x="0" y={ty + 4}>
              Account
            </text>
            {today !== null && (
              <text
                className={`font-mono text-[11.5px] ${toneFill(today)}`}
                x={barR + 8}
                y={ty + 4}
              >
                {formatMoney(today, { signed: true })}
              </text>
            )}
            {accPct !== null && (
              <>
                <circle
                  className="fill-panel stroke-fg [stroke-width:1.5]"
                  cx={px(accPct)}
                  cy={ty}
                  r="4"
                />
                <text
                  className={`font-mono text-[11.5px] ${toneFill(accPct)}`}
                  x={W}
                  y={ty + 4}
                  textAnchor="end"
                >
                  {signedPct(accPct)}
                </text>
              </>
            )}
          </svg>
        </div>
      )}
      <div className="flex items-start gap-2.5 border-t border-line px-5 py-3.5 text-[12.5px] text-fg-2">
        <CopilotMark className="mt-px h-[15px] w-[15px] flex-none text-fg-3" />
        <span>{movedSummary(rows, spy, !phase.open)}</span>
      </div>
    </HomeCard>
  );
}

const DAYS = 14;

function Timeline({
  entries,
  today,
  hotSession,
}: {
  entries: readonly NextEntry[];
  today: Date;
  hotSession: string | null;
}) {
  const [ref, W] = useWidth<HTMLDivElement>(560);
  const Hh = 54;
  const dw = W / DAYS;
  const cx = (k: number) => dw * k + dw / 2;
  const base = 26;
  const days = Array.from({ length: DAYS }, (_, k) => new Date(today.getTime() + k * DAY));
  const marks = entries.filter((e) => e.sessions.length > 0);
  return (
    <div className="px-5 pt-2" ref={ref}>
      <svg
        viewBox={`0 0 ${W} ${Hh}`}
        height={Hh}
        className="block w-full overflow-visible"
        role="img"
        aria-label="The next two weeks"
      >
        <line className="stroke-line-strong" x1="0" x2={W} y1={base} y2={base} />
        {days.map((d, k) => {
          const md = marketDay(d);
          const weekend = d.getUTCDay() === 0 || d.getUTCDay() === 6;
          const lab = k === 0 || d.getUTCDate() === 1 ? dayLabel(d) : String(d.getUTCDate());
          return (
            <g key={k}>
              {md.closed ? (
                <rect
                  className="fill-sunk stroke-line"
                  x={k * dw + 1}
                  y={base - 4}
                  width={dw - 2}
                  height="8"
                  rx="1.5"
                />
              ) : (
                <line
                  className="stroke-line-strong"
                  x1={cx(k)}
                  x2={cx(k)}
                  y1={base - 3}
                  y2={base + 3}
                />
              )}
              {!weekend && (
                <text
                  className={AX}
                  x={k === 0 ? 0 : cx(k)}
                  y={Hh - 4}
                  textAnchor={k === 0 ? 'start' : 'middle'}
                  opacity={md.closed ? 0.55 : 1}
                >
                  {lab}
                </text>
              )}
            </g>
          );
        })}
        {marks.map((e, j) => {
          const k = Math.round((e.day.getTime() - today.getTime()) / DAY);
          if (k < 0 || k >= DAYS) return null;
          const prev = marks[j - 1];
          const crowded = prev !== undefined && (e.day.getTime() - prev.day.getTime()) / DAY < 3;
          const hot = hotSession !== null && e.sessions.some((s) => s.id === hotSession);
          return (
            <g key={e.key}>
              {!crowded && (
                <text
                  className={`font-mono text-[10.5px] ${hot ? 'fill-fg' : 'fill-fg-2'}`}
                  x={k === 0 ? cx(k) - 5 : cx(k)}
                  y="10"
                  textAnchor={k === 0 ? 'start' : 'middle'}
                >
                  Rebalance
                </text>
              )}
              <circle
                cx={cx(k)}
                cy={base}
                r="4.5"
                className={`${hot ? 'fill-fg' : 'fill-panel'} stroke-fg [stroke-width:1.5]`}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export interface ComingNextProps {
  entries: readonly NextEntry[];
  today: Date;
  hotSession: string | null;
  onHover: (sessionId: string | null) => void;
}

/** home/next: the next two weeks on a line, then each scheduled step. */
export function ComingNext({ entries, today, hotSession, onHover }: ComingNextProps) {
  const closedDay = Array.from(
    { length: DAYS },
    (_, k) => new Date(today.getTime() + k * DAY)
  ).find((d) => marketDay(d).name !== null && marketDay(d).closed);
  return (
    <HomeCard
      title="What comes next"
      sub={`Through ${dayLabel(new Date(today.getTime() + (DAYS - 1) * DAY))}`}
      right={
        closedDay && (
          <span className="text-[12.5px] text-fg-3">Market closed {dayLabel(closedDay)}</span>
        )
      }
    >
      <Timeline entries={entries} today={today} hotSession={hotSession} />
      {entries.length === 0 ? (
        <p className="m-0 border-t border-line px-5 py-5 text-[13px] text-fg-3">
          No rebalances are scheduled in the next two weeks.
        </p>
      ) : (
        <ul className="m-0 mt-2 list-none p-0" onMouseLeave={() => onHover(null)}>
          {entries.slice(0, 6).map((e) => {
            const one = e.sessions.length === 1 ? e.sessions[0] : null;
            const hot = hotSession !== null && e.sessions.some((s) => s.id === hotSession);
            const body = (
              <>
                <span className="w-[112px] flex-none font-mono text-[12px] text-fg">
                  {e.when}
                  {e.at && <span className="block text-fg-3">{e.at}</span>}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-fg">{e.title}</span>
                  <span
                    className={`block truncate text-[12.5px] ${e.risk ? 'text-risk' : 'text-fg-2'}`}
                  >
                    {e.detail}
                  </span>
                </span>
                {one && <ChevronRight aria-hidden="true" className="h-4 w-4 flex-none text-fg-3" />}
              </>
            );
            const cls = `flex items-center gap-4 border-t border-line px-5 py-3 ${hot ? 'bg-sunk/75' : ''}`;
            return (
              <li key={e.key} onMouseEnter={() => onHover(one?.id ?? null)}>
                {one ? (
                  <Link to={one.href} className={`${cls} hover:bg-sunk/70`}>
                    {body}
                  </Link>
                ) : (
                  <div className={cls}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </HomeCard>
  );
}
