import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { Plus } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { FirstSession } from '../../components/home/FirstSession';
import { FirstVisit } from '../../components/home/FirstVisit';
import { holdingsOf, targetWeights } from '../../components/home/holdings';
import { HomeAttention } from '../../components/home/HomeAttention';
import { HomeHero, NoHistory, type HeroFigures } from '../../components/home/HomeHero';
import {
  attentionLine,
  blendEquity,
  etDay,
  fillsOf,
  foldSessions,
  homeSessions,
  homeStage,
  marketPhase,
  opensWords,
  rebalancingToday,
  sessionsLine,
  splitByMode,
  todayLine,
  upcoming,
} from '../../components/home/homeModel';
import {
  BeforeClose,
  HowTodayClosed,
  NextList,
  TodayBySession,
  TodayFills,
} from '../../components/home/HomePanels';
import { HomePhone } from '../../components/home/HomePhone';
import { useAttentionEntries } from '../../components/home/useAttentionEntries';
import { usePageScope } from '../../components/shell/usePageScope';
import { useSessionRows } from '../../components/shell/useSessionRows';
import {
  LoadingLabel,
  PageArt,
  PageHead,
  PanelError,
  ScopeControl,
  SkeletonChart,
  SkeletonFigure,
  SkeletonRows,
} from '../../components/ui';
import { inScope } from '../../lib/scope';
import { useAuthStore } from '../../store/auth';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

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

/** Re-renders every half minute so the Now marker and the market phase stay current. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

function LoadingHome() {
  return (
    <>
      <LoadingLabel>Loading Home</LoadingLabel>
      <div className="panel-rim grid gap-4 p-5">
        <SkeletonFigure />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[200px_minmax(0,1fr)]">
          <SkeletonRows rows={5} cols={2} />
          <SkeletonChart height={220} />
        </div>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-panel border border-line bg-panel">
            <SkeletonRows rows={3} cols={2} />
          </div>
        ))}
      </div>
    </>
  );
}

/** Home (home-decisions.md): the annotated curve, with first-visit and first-session stages. */
export default function DashboardPage() {
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
  const strategyCount = useDashboardStore((s) => s.strategyCount);
  const sessionCount = useDashboardStore((s) => s.sessionCount);
  const rejectedOrders = useDashboardStore((s) => s.rejectedOrders);

  const tradingLoaded = useTradingStore((s) => s.loaded);
  const tradingLoading = useTradingStore((s) => s.loading);
  const tradingError = useTradingStore((s) => s.error);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const orders = useTradingStore((s) => s.orders);
  const positions = useTradingStore((s) => s.positions);
  const fullStrategies = useStrategiesStore((s) => s.strategies);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);

  const user = useAuthStore((s) => s.user);
  const attention = useAttentionEntries();
  const rows = useSessionRows();
  const navigate = useNavigate();
  const createNew = useStrategyBuilderStore((s) => s.createNew);
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

  const sessions = useMemo(() => homeSessions(rows, strategies), [rows, strategies]);
  const phase = marketPhase(now);
  const today = etDay(phase.open ? now : phase.close);
  const nowDayMs = etDay(now).getTime();
  const nowDay = useMemo(() => new Date(nowDayMs), [nowDayMs]);

  const totals = useMemo(() => splitByMode(sessions), [sessions]);
  const { scope, setScope, options } = usePageScope('home', {
    all: totalEquity || totals.live + totals.paper,
    live: totals.live,
    paper: totals.paper,
  });
  const scoped = useMemo(
    () => sessions.filter((s) => inScope(scope, s.mode === 'live')),
    [sessions, scope]
  );
  const scopedIds = useMemo(() => new Set(scoped.map((s) => s.id)), [scoped]);
  const fills = useMemo(
    () => fillsOf(orders).filter((f) => scopedIds.has(f.sessionId)),
    [orders, scopedIds]
  );
  const dayFills = fills.filter((f) => etDay(f.at).getTime() === today.getTime());
  const series = useMemo(() => blendEquity(scoped), [scoped]);
  const schedule = useMemo(() => upcoming(scoped, nowDay), [scoped, nowDay]);
  const dueToday = phase.open ? rebalancingToday(scoped, nowDay) : [];
  const { shown, rest } = useMemo(() => foldSessions(scoped), [scoped]);

  const stage =
    tradingLoaded && !tradingError
      ? homeStage(sessions, nowDay)
      : sessionCount === 0
        ? 'firstVisit'
        : 'ordinary';

  // Session names and rebalance schedules come from the strategies.
  useEffect(() => {
    if (useStrategiesStore.getState().strategies.length === 0) {
      fetchStrategies().catch(() => undefined);
    }
  }, [fetchStrategies]);

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

  const name = user?.firstName?.trim();
  const named = (s: string) => `${s}${name ? `, ${name}` : ''}.`;
  const subParts = [
    phase.open
      ? sessionsLine(sessions)
      : `the market closed ${closedWhen(phase.close, nowDay)}at ${phase.closeClock} and opens ${phase.nextOpen ? opensWords(phase.nextOpen, now) : 'on the next trading day'}`,
    phase.open ? todayLine(sessions, nowDay) : null,
    attentionLine(attention.length),
  ].filter(Boolean);

  const ready = tradingLoaded && dashLoaded;
  const newStrategy = () => {
    createNew();
    navigate('/strategies/builder');
  };
  const retryFills = () => {
    loadBlotter().catch(() => undefined);
  };

  if (ready && stage === 'firstVisit') {
    return (
      <div className="page relative isolate grid grid-cols-[minmax(0,1fr)] gap-6">
        <PageArt shape="top" />
        <PageHead
          documentTitle="Home"
          title={
            <span className="block max-w-[900px] text-[30px] leading-[1.1] tracking-[-0.035em] md:text-[40px]">
              {named('Welcome')} How would you like to start?
            </span>
          }
          sub={
            <span className="text-[14px] md:text-[15px]">
              Each path ends in the same place: a strategy you can backtest, then run on Alpaca
              paper. You can connect Alpaca later.
            </span>
          }
          className="mt-4 md:mt-8"
        />
        <FirstVisit hasStrategies={(strategyCount ?? 0) > 0} />
      </div>
    );
  }

  if (ready && stage === 'firstSession') {
    const s = sessions[0];
    const strategy = fullStrategies.find((st) => st.id === rows[0]?.session.strategyId);
    const targets = targetWeights(strategy?.dslCode ?? '');
    const sleeveCash = rows[0]?.sleeve?.cash?.balance;
    const sessionFills = fillsOf(orders).filter((f) => f.sessionId === s.id);
    return (
      <div className="page relative isolate grid grid-cols-[minmax(0,1fr)] gap-4">
        <PageArt shape="top" />
        <PageHead
          documentTitle="Home"
          title={`Your first ${s.mode} session is running.`}
          sub={`${s.name} started ${s.startedAt ? (etDay(s.startedAt).getTime() === nowDay.getTime() ? 'today' : `on ${longDate(s.startedAt)}`) : 'recently'}${s.allocated ? ` with $${s.allocated.toLocaleString('en-US')} on Alpaca ${s.mode}` : ''}.`}
          attention={<HomeAttention entries={attention} />}
          actions={
            <Link to={s.href} className="btn btn-secondary">
              Open the session
            </Link>
          }
        />
        <FirstSession
          session={s}
          holdings={holdingsOf(
            positions.filter((p) => p.sessionId === s.id),
            targets
          )}
          cash={sleeveCash ? Number(sleeveCash.value) : null}
          fills={sessionFills}
          rejected={(rejectedOrders ?? []).filter((o) => o.sessionId === s.id).length}
          today={nowDay}
        />
      </div>
    );
  }

  const fillsError = Boolean(tradingError);
  const curve = (
    <HomeHero
      figures={figures}
      series={series}
      benchmark={benchmarkCurve}
      shown={shown}
      rest={rest}
      fills={fills}
      schedule={schedule}
      phase={phase}
      now={now}
      noHistory={<NoHistory />}
    />
  );

  return (
    <div className="page relative isolate grid grid-cols-[minmax(0,1fr)] gap-4">
      <PageArt shape="top" />
      <PageHead
        documentTitle="Home"
        title={longDate(now)}
        sub={capitalize(subParts.join(' · '))}
        attention={ready ? <HomeAttention entries={attention} /> : undefined}
        scope={
          options.length > 1 ? (
            <ScopeControl options={options} value={scope} onChange={setScope} />
          ) : undefined
        }
        actions={
          <div className="hidden items-center gap-2 md:flex">
            <Link to="/backtest" className="btn btn-secondary">
              Run a backtest
            </Link>
            <button type="button" onClick={newStrategy} className="btn btn-primary">
              <Plus aria-hidden="true" className="h-4 w-4" />
              New strategy
            </button>
          </div>
        }
      />
      {!ready ? (
        <LoadingHome />
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
              curve
            )}
            {phase.open ? (
              <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-3">
                <TodayFills
                  fills={dayFills}
                  sessions={sessions}
                  error={fillsError}
                  onRetry={retryFills}
                  retrying={tradingLoading}
                />
                <BeforeClose due={dueToday} phase={phase} />
                <TodayBySession sessions={scoped} />
              </div>
            ) : (
              <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
                <HowTodayClosed sessions={scoped} fills={dayFills} />
                <NextList rows={schedule} phase={phase} />
              </div>
            )}
          </div>
          {dashFailed ? (
            <div className="md:hidden">
              <PanelError
                title="Account figures couldn't be loaded"
                cause="The portfolio service didn't answer."
                onRetry={refresh}
                retrying={dashLoading}
              />
            </div>
          ) : null}
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
