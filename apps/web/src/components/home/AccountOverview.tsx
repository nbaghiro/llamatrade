import type { CurvePoint } from '@llamatrade/core/chart';
import { num, toDate } from '@llamatrade/core/format';
import { marketDataClient } from '@llamatrade/core/net';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { useOnline } from '../../hooks/useOnline';
import { inScope, type AccountScope } from '../../lib/scope';
import { useSessionRows } from '../shell/useSessionRows';
import { LoadingLabel, PanelError, SkeletonChart, SkeletonFigure, SkeletonRows } from '../ui';

import {
  ACCOUNT_LINE,
  accountRows,
  modeLine,
  sessionLine,
  type SessionSource,
} from './accountRows';
import { AccountTree } from './AccountTree';
import { nextEntries } from './dayModel';
import { ComingNext, MovedToday } from './DayPanels';
import { HomeHead, NoHistory, type HeroFigures } from './HomeHead';
import {
  benchDayMove,
  blendEquity,
  defaultRange,
  etDay,
  fillsOf,
  homeSessions,
  marketPhase,
  opensWords,
  rebalancingToday,
  sessionsLine,
  snapshotDayMove,
  splitByMode,
  todayLine,
  upcoming,
  type DailyBars,
  type HomeRange,
} from './homeModel';
import { FillsFailed } from './HomePanels';
import { HomePhone } from './HomePhone';
import { PerfCard, type PerfSelection } from './PerfCard';
import { blendedPoints, lineAlong, monthOf, perfWindow } from './perfModel';
import { definitionKey, useSessionDefinitions } from './useSessionDefinitions';

const capitalize = (s: string) => (s ? `${s[0].toUpperCase()}${s.slice(1)}` : s);

const longDate = (d: Date) =>
  d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

/** "" for today's close, else "on Friday ". */
function closedWhen(close: Date, today: Date): string {
  const day = etDay(close);
  if (day.getTime() === today.getTime()) return '';
  const weekday = new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: 'UTC' }).format(
    day
  );
  return `on ${weekday} `;
}

/**
 * Re-renders every half minute so the market phase stays current. Offline it holds at the
 * moment the connection dropped, since the figures on screen are from then.
 */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  const { online, offlineSince } = useOnline();
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return !online && offlineSince ? offlineSince : now;
}

/** SPY's latest daily bars, for its move on the day shown. */
function useSpyBars(): DailyBars | null {
  const [bars, setBars] = useState<DailyBars | null>(null);
  useEffect(() => {
    let live = true;
    marketDataClient
      .getSnapshots({ symbols: ['SPY'] })
      .then((res) => {
        const snap = res.snapshots.SPY;
        const at = toDate(snap?.dailyBar?.timestamp);
        if (!live || !snap || !at) return;
        setBars({
          at,
          close: num(snap.dailyBar?.close),
          previousClose: num(snap.previousDailyBar?.close),
        });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return bars;
}

function LoadingOverview() {
  return (
    <>
      <LoadingLabel>Loading the account</LoadingLabel>
      <div className="panel-rim grid gap-4 p-5">
        <SkeletonFigure />
        <SkeletonChart height={260} />
      </div>
      <div className="rounded-panel border border-line bg-panel">
        <SkeletonRows rows={6} cols={4} />
      </div>
    </>
  );
}

/** The account against SPY, as a tree of sessions and their rules, and what moved and comes next. */
export function AccountOverview({ scope }: { scope: AccountScope }) {
  const fetchDashboard = useDashboardStore((s) => s.fetchDashboard);
  const dashLoaded = useDashboardStore((s) => s.loaded);
  const dashLoading = useDashboardStore((s) => s.loading);
  const dashError = useDashboardStore((s) => s.error);
  const strategies = useDashboardStore((s) => s.strategies);
  const totalEquity = useDashboardStore((s) => s.totalEquity);
  const dayPnl = useDashboardStore((s) => s.dayPnl);
  const dayPnlPercent = useDashboardStore((s) => s.dayPnlPercent);
  const freeCash = useDashboardStore((s) => s.freeCash);
  const benchmarkCurve = useDashboardStore((s) => s.benchmarkCurve);

  const tradingLoaded = useTradingStore((s) => s.loaded);
  const tradingLoading = useTradingStore((s) => s.loading);
  const tradingError = useTradingStore((s) => s.error);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const orders = useTradingStore((s) => s.orders);
  const positions = useTradingStore((s) => s.positions);
  const fullStrategies = useStrategiesStore((s) => s.strategies);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);

  const rows = useSessionRows();
  const now = useNow();
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const refresh = useCallback(() => {
    fetchDashboard()
      .then(() => {
        if (!useDashboardStore.getState().error) setFetchedAt(new Date());
      })
      .catch(() => undefined);
  }, [fetchDashboard]);

  useEffect(refresh, [refresh]);
  useEffect(() => {
    if (!tradingLoaded && !tradingLoading) loadBlotter().catch(() => undefined);
  }, [tradingLoaded, tradingLoading, loadBlotter]);

  // Session names, rebalance schedules and the rules in the account tree come from the strategies.
  useEffect(() => {
    if (useStrategiesStore.getState().strategies.length === 0) {
      fetchStrategies().catch(() => undefined);
    }
  }, [fetchStrategies]);

  const sessions = useMemo(() => homeSessions(rows, strategies), [rows, strategies]);
  const phase = marketPhase(now);
  const today = etDay(phase.open ? now : phase.close);
  const nowDayMs = etDay(now).getTime();
  const nowDay = useMemo(() => new Date(nowDayMs), [nowDayMs]);

  const spyBars = useSpyBars();
  const closeDay = etDay(phase.close);
  const spyDay = phase.open
    ? snapshotDayMove(spyBars, nowDay)
    : (benchDayMove(benchmarkCurve, closeDay) ?? snapshotDayMove(spyBars, closeDay));

  const scoped = useMemo(
    () => sessions.filter((s) => inScope(scope, s.mode === 'live')),
    [sessions, scope]
  );
  const scopedIds = useMemo(() => new Set(scoped.map((s) => s.id)), [scoped]);
  const fills = useMemo(
    () => fillsOf(orders).filter((f) => scopedIds.has(f.sessionId)),
    [orders, scopedIds]
  );
  const series = useMemo(() => blendEquity(scoped), [scoped]);
  const schedule = useMemo(() => upcoming(scoped, nowDay), [scoped, nowDay]);
  const dueToday = phase.open ? rebalancingToday(scoped, nowDay) : [];
  const dayFills = fills.filter((f) => etDay(f.at).getTime() === today.getTime());

  const modes = new Set(scoped.map((s) => s.mode));
  const scopedSplit = splitByMode(scoped);
  const allScope = scope === 'all' || scoped.length === sessions.length;
  const scopedToday = scoped.reduce((sum, s) => sum + (s.today ?? 0), 0);
  const scopedTotal = scopedSplit.live + scopedSplit.paper;
  const figures: HeroFigures = {
    kinds: modes.size === 2 ? 'paper and live' : modes.has('live') ? 'live' : 'paper',
    total: allScope ? totalEquity || scopedTotal : scopedTotal,
    today: allScope ? dayPnl : scoped.some((s) => s.today !== null) ? scopedToday : null,
    todayPct: allScope
      ? dayPnlPercent / 100
      : scopedTotal - scopedToday > 0
        ? scopedToday / (scopedTotal - scopedToday)
        : null,
    cash: allScope ? freeCash : null,
    live: scopedSplit.live,
    paper: scopedSplit.paper,
    showSplit: modes.size === 2,
    staleSince: dashError && fetchedAt ? fetchedAt : null,
    onRetry: refresh,
    retrying: dashLoading,
  };
  const dashFailed = Boolean(dashError) && !fetchedAt;

  // The chart's range, and the tree row whose line it draws while hovered or kept.
  const [range, setRange] = useState<HomeRange>(() => defaultRange(phase));
  const [hover, setHover] = useState<string | null>(null);
  const [pin, setPin] = useState<string | null>(null);
  const [panelSession, setPanelSession] = useState<string | null>(null);

  const lastSnapshot = series.dates[series.dates.length - 1];
  // After the close, a snapshot taken that evening still belongs on the line.
  const endMs = phase.open
    ? now.getTime()
    : Math.max(phase.close.getTime(), lastSnapshot?.getTime() ?? 0);
  const perf = useMemo(
    () => perfWindow(series, benchmarkCurve, scoped, fills, range, new Date(endMs)),
    [series, benchmarkCurve, scoped, fills, range, endMs]
  );

  const definitions = useSessionDefinitions(rows);
  const sources = useMemo(() => {
    const out = new Map<string, SessionSource>();
    for (const row of rows) {
      const strategy = fullStrategies.find((s) => s.id === row.session.strategyId);
      const dsl =
        definitions.get(definitionKey(row.session.strategyId, row.version)) || strategy?.dslCode;
      const parsed = dsl ? fromDSLString(dsl) : null;
      out.set(row.session.id, {
        strategyId: row.session.strategyId,
        version: row.version,
        tree: parsed?.tree ?? null,
        positions: positions
          .filter((p) => p.sessionId === row.session.id)
          .map((p) => ({ symbol: p.symbol, value: Math.abs(num(p.marketValue)) }))
          .filter((p) => p.value > 0),
      });
    }
    return out;
  }, [rows, fullStrategies, definitions, positions]);

  const treeRows = useMemo(
    () =>
      accountRows({
        sessions: scoped,
        sources,
        total: figures.total,
        today: figures.today,
        day: nowDay,
      }),
    [scoped, sources, figures.total, figures.today, nowDay]
  );

  const points = useMemo(() => {
    const out = new Map<string, CurvePoint[]>();
    out.set(ACCOUNT_LINE, blendedPoints(scoped));
    for (const mode of ['live', 'paper'] as const) {
      out.set(modeLine(mode), blendedPoints(scoped.filter((s) => s.mode === mode)));
    }
    for (const s of scoped) out.set(sessionLine(s.id), [...s.equity]);
    return out;
  }, [scoped]);
  const months = useMemo(() => {
    const out = new Map<string, ReturnType<typeof monthOf>>();
    for (const [key, list] of points) out.set(key, monthOf(list, benchmarkCurve, new Date(endMs)));
    return out;
  }, [points, benchmarkCurve, endMs]);

  const activeRow = treeRows.find((r) => r.id === (hover ?? pin));
  const activeLine = activeRow?.lineKey;
  const selection: PerfSelection | null = useMemo(() => {
    if (!perf || !activeLine || activeLine === ACCOUNT_LINE) return null;
    const list = points.get(activeLine);
    const owner = treeRows.find((r) => r.lineKey === activeLine && r.kind !== 'rule');
    if (!list || list.length === 0 || !owner) return null;
    return { label: owner.label ?? '', line: lineAlong(perf.dates, list) };
  }, [perf, activeLine, points, treeRows]);
  const hotSession = activeRow?.sessionId ?? panelSession;
  const entries = nextEntries(schedule, dueToday, phase, nowDay);

  const subParts = [
    phase.open
      ? sessionsLine(sessions)
      : `the market closed ${closedWhen(phase.close, nowDay)}at ${phase.closeClock} and opens ${phase.nextOpen ? opensWords(phase.nextOpen, now) : 'on the next trading day'}`,
    phase.open ? todayLine(sessions, nowDay) : null,
  ].filter(Boolean);
  const dayWords = phase.open
    ? 'today'
    : closeDay.getTime() === nowDay.getTime()
      ? 'today'
      : closedWhen(phase.close, nowDay).trim();

  const ready = tradingLoaded && dashLoaded;
  const fillsError = Boolean(tradingError);
  const retryFills = () => {
    loadBlotter().catch(() => undefined);
  };

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
      <div className="hidden md:block">
        <HomeHead
          figures={figures}
          date={longDate(now)}
          sub={capitalize(subParts.join(' · '))}
          spy={{ value: spyDay, when: dayWords }}
          open={phase.open}
          failed={
            ready && dashFailed ? (
              <p className="m-0 mt-2 text-[13px] text-fg-2">
                Account figures couldn&apos;t be loaded.
              </p>
            ) : undefined
          }
        />
      </div>
      {!ready ? (
        <LoadingOverview />
      ) : (
        <>
          <div className="hidden gap-4 md:grid">
            {dashFailed ? (
              <div className="panel-rim">
                <PanelError
                  title="Account figures couldn't be loaded"
                  cause="The portfolio service didn't answer."
                  unaffected="Running sessions keep trading, and the panels below still update."
                  onRetry={refresh}
                  retrying={dashLoading}
                />
              </div>
            ) : (
              <PerfCard
                perf={perf}
                range={range}
                onRange={setRange}
                selection={selection}
                hotSession={hotSession}
                empty={<NoHistory />}
              />
            )}
            <AccountTree
              rows={treeRows}
              months={months}
              hover={hover}
              pin={pin}
              hotSession={panelSession}
              onHover={setHover}
              onPin={setPin}
            />
            {fillsError && (
              <div className="rounded-panel border border-line bg-panel">
                <FillsFailed onRetry={retryFills} retrying={tradingLoading} />
              </div>
            )}
            <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-2">
              <MovedToday
                sessions={scoped}
                today={figures.today}
                todayPct={figures.todayPct}
                spy={spyDay}
                phase={phase}
                when={dayWords}
                hotSession={hotSession}
                onHover={setPanelSession}
              />
              <ComingNext
                entries={entries}
                today={nowDay}
                hotSession={hotSession}
                onHover={setPanelSession}
              />
            </div>
          </div>
          {dashFailed && (
            <div className="md:hidden">
              <PanelError
                title="Account figures couldn't be loaded"
                cause="The portfolio service didn't answer."
                onRetry={refresh}
                retrying={dashLoading}
              />
            </div>
          )}
          <HomePhone
            figures={figures}
            series={series}
            sessions={scoped}
            dueToday={dueToday}
            fills={dayFills}
            fillsError={fillsError}
            onRetryFills={retryFills}
            retrying={tradingLoading}
            schedule={schedule}
            phase={phase}
            now={now}
          />
        </>
      )}
    </div>
  );
}
