import type { CurvePoint } from '@llamatrade/core/chart';
import { Clock, RefreshCw } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, formatPct, pnlTone } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { AnnotatedCurve, type CurveLane, type LaneEvent } from '../charts';
import { ModeBadge, PaperLiveSplit, Segmented, StatList, type StatItem } from '../ui';

import {
  curveWindow,
  dayLabel,
  etDay,
  HOME_RANGES,
  weekdayLabel,
  type EquitySeries,
  type Fill,
  type HomeRange,
  type HomeSession,
  type MarketPhase,
  type ScheduleRow,
} from './homeModel';
import {
  curvePins,
  laneEvents,
  laneFuture,
  laneSpans,
  mergedEvents,
  type LaneWindow,
} from './lanes';

const RANGE_LABEL: Record<HomeRange, string> = { '1M': '1M', '3M': '3M', '1Y': '1Y', ALL: 'All' };
const RANGE_WORDS: Record<HomeRange, string> = {
  '1M': '1 month',
  '3M': '3 months',
  '1Y': '1 year',
  ALL: 'Since start',
};

/** A signed figure in a soft gain or loss chip. */
export function Chg({ children, value }: { children: ReactNode; value: number }) {
  const tone = pnlTone(value);
  const cls =
    tone === 'gain'
      ? 'bg-gain/10 text-gain'
      : tone === 'loss'
        ? 'bg-loss/10 text-loss'
        : 'bg-sunk text-fg-2';
  return (
    <span className={`rounded-[4px] px-1.5 py-px font-mono text-[12.5px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <div className="font-mono text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
      {children}
    </div>
  );
}

function Fig({ label, children, tone }: { label: string; children: ReactNode; tone?: string }) {
  return (
    <div className="min-w-0">
      <Label>{label}</Label>
      <div
        className={`mt-1 font-mono text-[15px] font-semibold tracking-[-0.02em] ${tone ?? 'text-fg'}`}
      >
        {children}
      </div>
    </div>
  );
}

const toneClass = (v: number | null) =>
  v === null
    ? 'text-fg-3'
    : pnlTone(v) === 'gain'
      ? 'text-gain'
      : pnlTone(v) === 'loss'
        ? 'text-loss'
        : 'text-fg';

export interface HeroFigures {
  /** "paper and live", "paper" or "live". */
  kinds: string;
  total: number;
  today: number | null;
  todayPct: number | null;
  cash: number | null;
  live: number;
  paper: number;
  showSplit: boolean;
  /** Set when the figures are from an earlier load that couldn't refresh. */
  staleSince: Date | null;
  onRetry: () => void;
  retrying: boolean;
}

/** The figure row at the top of the hero panel: total, today, the range and SPY, cash, and the split. */
function HeroHead({
  figures,
  phase,
  range,
  onRange,
  accountReturn,
  benchReturn,
  hasBench,
}: {
  figures: HeroFigures;
  phase: MarketPhase;
  range: HomeRange;
  onRange: (r: HomeRange) => void;
  accountReturn: number | null;
  benchReturn: number | null;
  hasBench: boolean;
}) {
  return (
    <div className="flex flex-wrap items-start gap-x-9 gap-y-4 px-5 pb-2 pt-4">
      <div className="min-w-0">
        <Label>
          {phase.open ? 'Total equity' : 'Equity at the close'} · {figures.kinds}
        </Label>
        <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-mono text-[34px] font-semibold leading-none tracking-[-0.04em] text-fg">
            {formatMoney(figures.total)}
          </span>
          {figures.today !== null && (
            <span className="flex items-center gap-1.5">
              <Chg value={figures.today}>{formatMoney(figures.today, { signed: true })}</Chg>
              {figures.todayPct !== null && (
                <Chg value={figures.todayPct}>{formatPct(figures.todayPct, { signed: true })}</Chg>
              )}
              <span className="text-[11.5px] text-fg-3">today</span>
            </span>
          )}
        </div>
        {figures.staleSince && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-fg-2">
            <Clock aria-hidden="true" className="h-3.5 w-3.5 text-fg-3" />
            From {etClock(figures.staleSince)}. Couldn&apos;t refresh.
            <button
              type="button"
              onClick={figures.onRetry}
              disabled={figures.retrying}
              className="btn btn-secondary btn-sm"
            >
              <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
              Try again
            </button>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-x-7 gap-y-3 pt-[3px]">
        <Fig label={RANGE_WORDS[range]} tone={toneClass(accountReturn)}>
          {accountReturn === null
            ? 'Not enough history'
            : formatPct(accountReturn, { signed: true })}
        </Fig>
        {hasBench && (
          <Fig label="SPY, same period">
            {benchReturn === null ? 'No data' : formatPct(benchReturn, { signed: true })}
          </Fig>
        )}
        {figures.cash !== null && <Fig label="Cash">{formatMoney(figures.cash)}</Fig>}
        {figures.showSplit && (
          <PaperLiveSplit
            live={figures.live}
            paper={figures.paper}
            className="pl-0 lg:border-l lg:border-line lg:pl-7"
          />
        )}
      </div>
      <div className="ml-auto flex flex-col items-end gap-2">
        <Segmented<HomeRange>
          label="Range"
          value={range}
          onChange={onRange}
          options={HOME_RANGES.map((r) => ({ key: r, label: RANGE_LABEL[r] }))}
        />
        <div className="flex items-center gap-3.5 text-[11.5px] text-fg-2">
          <span className="inline-flex items-center gap-1.5">
            <i aria-hidden="true" className="inline-block w-3.5 border-t-2 border-accent" />
            Sessions
          </span>
          {hasBench && (
            <span className="inline-flex items-center gap-1.5">
              <i
                aria-hidden="true"
                className="inline-block w-3.5 border-t-[1.5px] border-dashed border-fg-3"
              />
              SPY
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function NextRows({
  rows,
  phase,
  now,
}: {
  rows: readonly ScheduleRow[];
  phase: MarketPhase;
  now: Date;
}) {
  const shown = rows.slice(0, 6);
  return (
    <ul className="m-0 grid list-none gap-[7px] p-0 text-[12px]">
      {!phase.open &&
        phase.nextOpen &&
        etDay(phase.nextOpen).getTime() !== etDay(now).getTime() && (
          <li className="flex gap-2">
            <span className="w-[52px] flex-none font-mono text-fg-3">
              {dayLabel(etDay(phase.nextOpen))}
            </span>
            <span className="min-w-0 truncate text-fg-2">Market opens</span>
          </li>
        )}
      {shown.map((r) => (
        <li key={`${r.kind}-${r.day.getTime()}`} className="flex gap-2">
          <span className="w-[52px] flex-none font-mono text-fg-3">{dayLabel(r.day)}</span>
          <span className="min-w-0 truncate">
            {r.kind === 'closed' ? (
              <span className="text-fg-3">Market closed</span>
            ) : r.kind === 'early' ? (
              <span className="text-fg-3">Closes 13:00</span>
            ) : (
              <>
                {r.sessions.length === 1 ? r.sessions[0].name : `${r.sessions.length} sessions`}
                {r.sessions.length === 1 && r.sessions[0].mode === 'live' && (
                  <ModeBadge mode="live" size="sm" className="ml-1.5 align-[1px]" />
                )}
              </>
            )}
          </span>
        </li>
      ))}
      {shown.length === 0 && <li className="text-fg-3">Nothing scheduled</li>}
    </ul>
  );
}

function laneOf(s: HomeSession, fills: readonly Fill[], w: LaneWindow): CurveLane {
  return {
    id: s.id,
    label: s.name,
    badge: <ModeBadge mode={s.mode} size="sm" />,
    tone:
      s.state === 'frozen'
        ? 'risk'
        : s.state === 'stopped' || s.state === 'error'
          ? 'muted'
          : 'default',
    href: s.href,
    spans: laneSpans(s, w),
    events: laneEvents(s, fills, w),
    future: laneFuture(s, w),
  };
}

export interface HomeHeroProps {
  figures: HeroFigures;
  series: EquitySeries;
  benchmark: readonly CurvePoint[];
  shown: readonly HomeSession[];
  rest: readonly HomeSession[];
  fills: readonly Fill[];
  schedule: readonly ScheduleRow[];
  phase: MarketPhase;
  now: Date;
  /** Shown in place of the curve when there is under two days of history. */
  noHistory: ReactNode;
}

/** home/layout2 A: the figures, then one annotated equity curve with a lane per session. */
export function HomeHero({
  figures,
  series,
  benchmark,
  shown,
  rest,
  fills,
  schedule,
  phase,
  now,
  noHistory,
}: HomeHeroProps) {
  const [range, setRange] = useState<HomeRange>('3M');
  const [expanded, setExpanded] = useState(false);
  const lastSnapshot = series.dates[series.dates.length - 1];
  // After the close, a snapshot taken that evening still belongs on the line.
  const endMs = phase.open
    ? now.getTime()
    : Math.max(phase.close.getTime(), lastSnapshot?.getTime() ?? 0);
  const end = useMemo(() => new Date(endMs), [endMs]);
  const todayMs = etDay(end).getTime();
  const win = useMemo(
    () => curveWindow(series, benchmark, range, end),
    [series, benchmark, range, end]
  );
  const w: LaneWindow = useMemo(
    () => ({
      start: win.start,
      end,
      today: new Date(todayMs),
      futureEnd: new Date(todayMs + 14 * 86_400_000),
    }),
    [win.start, end, todayMs]
  );
  const today = w.today;
  const bySession = useMemo(() => {
    const m = new Map<string, Fill[]>();
    for (const f of fills) m.set(f.sessionId, [...(m.get(f.sessionId) ?? []), f]);
    return m;
  }, [fills]);

  const inWindow = fills.filter(
    (f) => f.at.getTime() >= win.start.getTime() && f.at.getTime() <= end.getTime()
  );
  const todayCount = fills.filter((f) => etDay(f.at).getTime() === today.getTime()).length;
  const lanesShown = expanded ? [...shown, ...rest] : shown;
  const lanes: CurveLane[] = lanesShown.map((s) => laneOf(s, bySession.get(s.id) ?? [], w));
  if (rest.length && !expanded) {
    const merged: LaneEvent[] = mergedEvents(
      rest.map((s) => laneEvents(s, bySession.get(s.id) ?? [], w))
    );
    const planned = mergedEvents(rest.map((s) => laneFuture(s, w).events ?? []));
    lanes.push({
      id: 'more',
      label: (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="text-accent hover:underline"
        >
          {rest.length} more
        </button>
      ),
      tone: 'default',
      events: merged,
      future: planned.length ? { events: planned } : {},
    });
  }
  const rebalanceDays = new Set(inWindow.map((f) => `${f.sessionId}:${etDay(f.at).getTime()}`))
    .size;

  const stats: StatItem[] = [
    { label: 'High', value: win.high === null ? 'No data' : formatMoney(win.high, { dp: 0 }) },
    { label: 'Low', value: win.low === null ? 'No data' : formatMoney(win.low, { dp: 0 }) },
    {
      label: 'Max drawdown',
      value: win.maxDrawdown === null ? 'No data' : formatPct(win.maxDrawdown),
      tone: win.maxDrawdown !== null && win.maxDrawdown < 0 ? 'loss' : undefined,
    },
    { label: 'Fills in range', value: String(inWindow.length) },
    { label: 'Rebalances', value: String(rebalanceDays) },
  ];

  const sameDay = today.getTime() === etDay(now).getTime();
  const nowLabel = phase.open
    ? `Now ${etClock(now)}`
    : `Closed ${sameDay ? phase.closeClock : weekdayLabel(today).slice(0, 3)}`;

  return (
    <section aria-label="Account equity" className="panel-rim">
      <HeroHead
        figures={figures}
        phase={phase}
        range={range}
        onRange={setRange}
        accountReturn={win.accountReturn}
        benchReturn={win.benchReturn}
        hasBench={win.bench !== null}
      />
      <div className="px-5 pb-1.5 pt-2">
        {win.dates.length < 2 ? (
          noHistory
        ) : (
          <AnnotatedCurve
            label={`Value of the sessions, ${RANGE_WORDS[range].toLowerCase()}`}
            dates={win.dates}
            values={win.values}
            benchmark={win.bench ?? undefined}
            start={win.start}
            end={end}
            now={{ label: nowLabel }}
            future={{
              end: w.futureEnd,
              title: 'Next two weeks',
              content: <NextRows rows={schedule} phase={phase} now={now} />,
            }}
            pins={curvePins(lanesShown, todayCount, w)}
            side={<StatList items={stats} />}
            lanes={lanes}
            legend={[
              { shape: 'ring', label: 'Rebalance' },
              { shape: 'planned', label: 'Planned' },
            ]}
            tooltip={(i) => (
              <>
                {dayLabel(etDay(win.dates[i]))} · {formatMoney(win.values[i])}
                {win.bench &&
                  ` · SPY ${formatPct(win.bench[i] / win.values[0] - 1, { signed: true })}`}
              </>
            )}
          />
        )}
        {expanded && rest.length > 0 && (
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="mb-2 text-[12px] text-accent hover:underline"
          >
            Show the five largest only
          </button>
        )}
      </div>
    </section>
  );
}

export function NoHistory({ firstSession }: { firstSession?: boolean }) {
  return (
    <div className="grid min-h-[200px] place-content-center gap-1 rounded-[8px] border border-dashed border-line px-6 text-center text-[13px]">
      <b className="font-semibold text-fg">No daily history yet</b>
      <span className="text-fg-2">
        {firstSession
          ? 'Daily history starts at the close.'
          : 'The account line appears after two daily snapshots. '}
        <Link to="/portfolio" className="text-accent hover:underline">
          Open Portfolio
        </Link>
      </span>
    </div>
  );
}
