import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { yDomain } from '../../lib/chart/scale';
import {
  monthTicks,
  pctAt,
  timeArea,
  timeFraction,
  timePath,
  tickLabel,
} from '../../lib/chart/timeScale';
import { LaneLegend, LaneMarker } from '../charts';
import { Money, Pct } from '../ui/Num';
import { StatusMark } from '../ui/StatusMark';

import type { SessionRow } from './sessionRows';
import { etDayLabel, type FillDay, type Series } from './timeline';

export interface TimelineSession {
  row: SessionRow;
  series: Series;
  /** Days with fills, oldest first. */
  days: FillDay[];
  /** Fills today, for the numbered dot at Now. */
  fillsToday: number;
  next: Date | null;
  ended: Date | null;
}

export interface TimelineGroup {
  key: string;
  heading: ReactNode;
  total: number | null;
  sessions: TimelineSession[];
}

interface SessionTimelineProps {
  groups: readonly TimelineGroup[];
  start: Date;
  now: Date;
  nowLabel: string;
  /** Rows without curves, for long lists. */
  compact?: boolean;
}

const VIEW_W = 1000;
const CURVE_H = 30;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const GRID = 'grid grid-cols-[minmax(0,320px)_minmax(0,1fr)_180px]';

const utcLabel = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCDate()}`;

/** Every session on one date axis, its curve and rebalances, then its next run after Now (list2 A). */
export function SessionTimeline({
  groups,
  start,
  now,
  nowLabel,
  compact = false,
}: SessionTimelineProps) {
  const spanDays = (now.getTime() - start.getTime()) / 86_400_000;
  const ticks = monthTicks(start, now, 5);
  const fillsToday = groups.reduce(
    (n, g) => n + g.sessions.reduce((m, s) => m + s.fillsToday, 0),
    0
  );
  return (
    <div className="panel-rim px-5 pb-1.5 pt-3">
      <div className={GRID}>
        <span />
        <div className="relative h-6">
          {fillsToday > 0 && (
            <span className="absolute right-3 top-0.5 inline-flex h-[18px] items-center gap-[5px] whitespace-nowrap rounded-full border border-accent/45 bg-accent-soft px-[7px] font-mono text-[10.5px] font-medium text-fg">
              <b className="grid h-[13px] min-w-[13px] place-items-center rounded-full bg-accent px-0.5 text-[8.5px] font-semibold text-canvas">
                {fillsToday}
              </b>
              {fillsToday === 1 ? 'Fill today' : 'Fills today'}
            </span>
          )}
        </div>
        <div className="relative h-6 border-l-[1.5px] border-fg bg-sunk/70">
          <span className="absolute left-0 top-0.5 z-[5] -translate-x-1/2 whitespace-nowrap rounded bg-fg px-1.5 py-px font-mono text-[10px] font-semibold text-canvas">
            {nowLabel}
          </span>
          <span className="absolute right-2 top-1 text-[11px] text-fg-3">Next run</span>
        </div>
      </div>
      {groups.map((g) => (
        <section key={g.key} aria-label={typeof g.heading === 'string' ? g.heading : undefined}>
          <div className={`${GRID} border-t border-line`}>
            <div className="flex items-center justify-between gap-3 py-2.5 pr-4">
              <div className="flex min-w-0 items-center gap-2 text-[12.5px] text-fg-2">
                {g.heading}
              </div>
              {g.total !== null && <Money value={g.total} className="text-[13px] font-semibold" />}
            </div>
            <span />
            <span className="border-l-[1.5px] border-fg bg-sunk/70" />
          </div>
          {g.sessions.map((s) => (
            <TimelineRow key={s.row.session.id} s={s} start={start} now={now} compact={compact} />
          ))}
        </section>
      ))}
      <div className={`${GRID} border-t border-line`}>
        <div className="flex h-7 items-center">
          <LaneLegend
            items={[
              { shape: 'ring', label: 'Rebalance' },
              { shape: 'start', label: 'Start' },
              { shape: 'planned', label: 'Planned' },
            ]}
            className="flex-nowrap"
          />
        </div>
        <div className="relative h-7">
          {ticks.map((t) => (
            <span
              key={t.getTime()}
              className="absolute top-[6px] -translate-x-1/2 whitespace-nowrap font-mono text-[10.5px] text-fg-3"
              style={{ left: pctAt(t, start, now) }}
            >
              {tickLabel(t, spanDays)}
            </span>
          ))}
        </div>
        <span className="border-l-[1.5px] border-fg bg-sunk/70" />
      </div>
    </div>
  );
}

function TimelineRow({
  s,
  start,
  now,
  compact,
}: {
  s: TimelineSession;
  start: Date;
  now: Date;
  compact: boolean;
}) {
  const { row } = s;
  const f = row.figures;
  const stopped = !row.view.open;
  const risk = row.view.attention;
  const href = `/trading/${row.session.id}`;
  const startedAt = row.startedAt;
  const inWindow = (d: Date) => d.getTime() >= start.getTime() && d.getTime() <= now.getTime();
  const lineFrom = startedAt && startedAt > start ? startedAt : start;
  const lineTo = s.ended && s.ended < now ? s.ended : now;
  const domain = yDomain([s.series.values]);
  const path = compact
    ? ''
    : timePath(s.series.dates, s.series.values, start, now, domain, VIEW_W, CURVE_H);
  const area = compact
    ? ''
    : timeArea(s.series.dates, s.series.values, start, now, domain, VIEW_W, CURVE_H);
  const tone = risk ? 'risk' : stopped ? 'muted' : 'accent';
  const lineClass = risk ? 'border-risk' : stopped ? 'border-fg-3/45' : 'border-accent/60';
  const rowH = compact ? 'h-12' : 'h-[62px]';
  const stateLabel = [
    row.view.label === 'Stopped' && s.ended ? `Stopped ${etDayLabel(s.ended)}` : row.view.label,
    row.version ? `version ${row.version}` : null,
    row.rebalance ? row.rebalance.toLowerCase() : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className={`${GRID} group border-t border-line hover:bg-sunk/40`}>
      <Link to={href} className={`flex ${rowH} items-center justify-between gap-3 pr-4`}>
        <div className="min-w-0">
          <div
            className={`truncate text-[13px] font-semibold ${risk ? 'text-risk' : stopped ? 'text-fg-2' : 'text-fg'} group-hover:underline`}
          >
            {row.name}
          </div>
          <StatusMark state={row.view.mark} label={stateLabel} className="mt-0.5 text-[11.5px]" />
        </div>
        <div className="flex-none text-right">
          {f.equity === null ? (
            <span className="text-fg-3">·</span>
          ) : (
            <Money value={f.equity} className={`text-[13px] ${stopped ? 'text-fg-2' : ''}`} />
          )}
          <div className="text-[11px]">
            {stopped ? (
              f.totalPct !== null && (
                <span className="num">
                  <Pct value={f.totalPct} pnl dp={1} /> <span className="text-fg-3">overall</span>
                </span>
              )
            ) : f.today !== null ? (
              <span className="num">
                <Money value={f.today} pnl />
                {f.todayPct !== null && (
                  <>
                    {' · '}
                    <Pct value={f.todayPct} pnl />
                  </>
                )}
              </span>
            ) : null}
          </div>
        </div>
      </Link>
      <div className={`relative ${rowH} min-w-0`}>
        {!compact && path && (
          <svg
            aria-hidden="true"
            viewBox={`0 0 ${VIEW_W} ${CURVE_H}`}
            preserveAspectRatio="none"
            width="100%"
            height={CURVE_H}
            className="absolute inset-x-0 top-1.5 block overflow-visible"
          >
            {area && (
              <path
                d={area}
                fill={risk ? 'rgb(var(--risk) / 0.08)' : 'rgb(var(--accent) / 0.08)'}
              />
            )}
            <path
              d={path}
              fill="none"
              stroke={
                risk ? 'rgb(var(--risk))' : stopped ? 'rgb(var(--fg-3))' : 'rgb(var(--accent))'
              }
              strokeWidth={1.4}
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        )}
        <div className={`absolute inset-x-0 ${compact ? 'top-1/2' : 'bottom-[9px]'} h-0`}>
          {lineTo > lineFrom && (
            <i
              aria-hidden="true"
              className={`absolute top-0 border-t-[1.5px] ${lineClass}`}
              style={{
                left: pctAt(lineFrom, start, now),
                width: `${((timeFraction(lineTo, start, now) - timeFraction(lineFrom, start, now)) * 100).toFixed(3)}%`,
              }}
            />
          )}
          {startedAt && inWindow(startedAt) && (
            <LaneMarker
              shape="start"
              tone={tone}
              positioned
              title={`Started ${etDayLabel(startedAt)}`}
              style={{ left: pctAt(startedAt, start, now), top: 0 }}
            />
          )}
          {s.days
            .filter((d) => inWindow(d.at))
            .map((d) => (
              <LaneMarker
                key={d.key}
                shape="ring"
                tone={tone}
                positioned
                title={`${etDayLabel(d.at)}: ${d.orders.length} ${d.orders.length === 1 ? 'fill' : 'fills'}`}
                style={{ left: pctAt(d.at, start, now), top: 0 }}
              />
            ))}
          {s.fillsToday > 0 && (
            <LaneMarker
              shape="dot"
              count={s.fillsToday}
              tone={tone}
              positioned
              title={`${s.fillsToday} today`}
              style={{ left: '100%', top: 0 }}
            />
          )}
          {s.ended && inWindow(s.ended) && (
            <LaneMarker
              shape="stop"
              positioned
              title={`Stopped ${etDayLabel(s.ended)}`}
              style={{ left: pctAt(s.ended, start, now), top: 0 }}
            />
          )}
        </div>
      </div>
      <Link
        to={href}
        className={`relative flex ${rowH} flex-col justify-center border-l-[1.5px] border-fg bg-sunk/70 px-3`}
      >
        <NextRun s={s} now={now} />
      </Link>
    </div>
  );
}

function NextRun({ s, now }: { s: TimelineSession; now: Date }) {
  const { row } = s;
  if (row.state === 'frozen') {
    return (
      <>
        <b className="font-mono text-[12px] font-semibold text-risk">Held</b>
        <span className="truncate text-[11.5px] text-fg-2">Waits until resolved</span>
      </>
    );
  }
  if (!row.view.open) {
    return (
      <>
        <b className="font-mono text-[12px] font-semibold text-fg-3">Nothing scheduled</b>
        <span className="truncate text-[11.5px] text-fg-3">
          {row.state === 'error' ? 'Stopped by an error' : 'Stopped'}
        </span>
      </>
    );
  }
  if (row.state === 'paused') {
    return (
      <>
        <b className="font-mono text-[12px] font-semibold text-fg-2">Paused</b>
        <span className="truncate text-[11.5px] text-fg-3">Rebalances skipped until resumed</span>
      </>
    );
  }
  const today = s.next && utcLabel(s.next) === etDayLabel(now);
  return (
    <>
      <b className="font-mono text-[12px] font-semibold text-fg">
        {s.next
          ? today
            ? 'Today'
            : utcLabel(s.next)
          : row.rebalance === 'Daily'
            ? 'Each day'
            : 'On schedule'}
      </b>
      <span className="truncate text-[11.5px] text-fg-2">
        {row.rebalance ? `${row.rebalance} rebalance` : 'Next rebalance'}
      </span>
      <LaneMarker shape="planned" positioned style={{ left: 'calc(100% - 14px)', top: '50%' }} />
    </>
  );
}
