import { money } from '@llamatrade/core/format';
import { router } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { Animated, RefreshControl, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { AnnotatedCurve } from '../../src/charts/AnnotatedCurve';
import { Lanes } from '../../src/charts/Lanes';
import { useHomeData } from '../../src/home/data';
import { DaySheet, type DaySheetSubject } from '../../src/home/DaySheet';
import { toChartLanes } from '../../src/home/laneView';
import {
  accountSplit,
  attentionItems,
  blendEquity,
  closedRecap,
  displayName,
  fillsOn,
  homeMode,
  periodStart,
  PERIODS,
  plannedRebalances,
  sessionLanes,
  sessionRows,
  timeline,
  type Attention,
  type Period,
  type Point,
  type SessionRow,
} from '../../src/home/model';
import { OfflineStrip } from '../../src/home/OfflineStrip';
import {
  AttentionTray,
  DayChange,
  HomeTopRow,
  SearchButton,
  SectionHead,
  SessionsByAccount,
  SplitBlock,
  TimelineCard,
  type ChartFilter,
} from '../../src/home/parts';
import { ClosedRecap, FirstVisit } from '../../src/home/states';
import { dayLabel, hm } from '../../src/home/when';
import { HeaderActions } from '../../src/shell/HeaderActions';
import { useAuthStore } from '../../src/stores/auth';
import { makeStyles, space, useTheme } from '../../src/theme';
import { Canvas, Card, Loading, Notice, PanelError, Segmented, Text } from '../../src/ui';

const LABEL_W = 28;
const DAY = 86_400_000;

/** Home (home/phone B list first, with layout2 A's curve and lanes, hero B, sessions D, activity B, attention2 C). */
export default function HomeScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const insets = useSafeAreaInsets();
  const d = useHomeData();
  const user = useAuthStore((st) => st.user);
  const [filter, setFilter] = useState<ChartFilter>('both');
  const [period, setPeriod] = useState<Period>('3M');
  const [sheet, setSheet] = useState<DaySheetSubject | null>(null);
  const scrollY = useRef(new Animated.Value(0)).current;
  const onScroll = useMemo(
    () => Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], { useNativeDriver: true }),
    [scrollY],
  );

  const rows = useMemo(() => sessionRows(d.sessions), [d.sessions]);
  const split = useMemo(() => accountSplit(d.sessions, d.paperCash, d.liveCash), [d.sessions, d.paperCash, d.liveCash]);
  const planned = useMemo(() => plannedRebalances(d.sessions, d.fills, d.now), [d.sessions, d.fills, d.now]);
  const entries = useMemo(() => timeline(d.fills, planned, d.sessions, d.now), [d.fills, planned, d.sessions, d.now]);
  const attention = useMemo(() => attentionItems(d.frozen, d.rejected), [d.frozen, d.rejected]);
  const mode = homeMode({ loaded: d.loaded, strategyCount: d.strategyCount, sessionCount: d.sessions.length, marketOpen: d.marketOpen });

  const shown = useMemo(
    () => d.sessions.filter((x) => filter === 'both' || x.mode === filter),
    [d.sessions, filter],
  );
  const curve = useMemo(() => blendEquity(shown.map((x) => x.equity), shown.map((x) => x.allocated)), [shown]);
  const from = useMemo(() => {
    const p = periodStart(period, d.now);
    const first = curve[0]?.t ?? d.now - 30 * DAY;
    return p === null ? first : Math.max(p, first);
  }, [period, d.now, curve]);
  const until = d.now + 14 * DAY;
  const bench = useMemo(() => rebasedBenchmark(d.benchmark, curve, from), [d.benchmark, curve, from]);

  const lanesIn = useMemo(
    () => sessionLanes(shown, d.fills, planned.filter((p) => shown.some((x) => x.id === p.sessionId))),
    [shown, d.fills, planned],
  );
  const lanes = toChartLanes(lanesIn);

  const nextFor = (r: SessionRow): string | null => {
    const p = planned.find((x) => x.sessionId === r.id);
    if (!p) return null;
    const label = dayLabel(p.day, d.now);
    return label === 'Today' ? 'today' : label;
  };

  const openSession = (r: { sessionId: string | null; strategyId: string }) => {
    if (r.sessionId) router.push({ pathname: '/sessions/[id]', params: { id: r.sessionId } });
    else router.push({ pathname: '/strategy/[id]', params: { id: r.strategyId } });
  };
  const openById = (executionId: string) => {
    const x = d.sessions.find((y) => y.id === executionId);
    if (x) openSession(x);
  };
  const owner = (f: { sessionId: string; strategyId: string }) => {
    const x = d.sessions.find((y) => (y.sessionId ? y.sessionId === f.sessionId : y.strategyId === f.strategyId));
    return { name: x ? displayName(x.name) : '', mode: x?.mode ?? null };
  };
  const openDay = (day: number, executionId: string | null) => {
    const x = executionId ? d.sessions.find((y) => y.id === executionId) : undefined;
    setSheet({
      day,
      session: x ? { name: displayName(x.name), sessionId: x.sessionId, mode: x.mode } : null,
      fills: fillsOn(d.fills, day, x),
      owner,
    });
  };
  const review = (a: Attention) => {
    if (a.kind === 'frozen') openById(a.executionId);
    else router.push({ pathname: '/sessions/order/[id]', params: { id: a.orderId } });
  };

  const compactOpacity = scrollY.interpolate({ inputRange: [90, 140], outputRange: [0, 1], extrapolate: 'clamp' });
  const firstName = user?.firstName || null;
  const closed = mode === 'closed';

  return (
    <Canvas art="bold" artSeed="home-ordinary-day" scrollY={scrollY}>
      <SafeAreaView edges={['top']} style={s.flex}>
        <Animated.ScrollView
          contentContainerStyle={s.body}
          showsVerticalScrollIndicator={false}
          onScroll={onScroll}
          scrollEventThrottle={16}
          refreshControl={<RefreshControl refreshing={d.refreshing} onRefresh={d.refresh} tintColor={c.fg3} />}
        >
          <HomeTopRow />
          <OfflineStrip />
          {mode === 'loading' && !d.error ? (
            <Loading label="Loading your account" />
          ) : d.error && !d.loaded ? (
            <PanelError title="Couldn't load your account" detail={d.error} onRetry={d.refresh} />
          ) : mode === 'first' ? (
            <FirstVisit name={firstName} />
          ) : (
            <>
              {d.error ? <Notice title="Couldn't refresh." detail={`${d.error} Pull down to try again.`} /> : null}
              <View style={s.hero}>
                <Text variant="label" tone="fg3">
                  TOTAL EQUITY · {split.live > 0 && split.paper > 0 ? 'PAPER AND LIVE' : split.live > 0 ? 'LIVE' : 'PAPER'}
                </Text>
                <Text variant="hero">{money(d.totalEquity, 2)}</Text>
                <DayChange amount={d.dayPnl} percent={d.dayPnlPercent} suffix={closed ? 'at the last close' : 'today'} />
              </View>

              {split.total > 0 ? <SplitBlock split={split} filter={filter} onFilter={setFilter} /> : null}

              <View>
                <AttentionTray items={attention} onReview={review} />
                {curve.length > 1 ? (
                  <View style={s.chart}>
                    <AnnotatedCurve
                      series={curve}
                      benchmark={bench}
                      from={from}
                      until={closed ? d.now : until}
                      now={d.now}
                      inset={LABEL_W}
                      height={150}
                      onPressNow={() => openDay(d.now, null)}
                      accessibilityLabel={`${filter === 'both' ? 'Sessions' : filter === 'live' ? 'Live sessions' : 'Paper sessions'}, value over time, with SPY dashed`}
                    />
                    {lanes.length ? (
                      <View style={s.lanes}>
                        <Lanes
                          lanes={lanes}
                          from={from}
                          until={closed ? d.now : until}
                          now={d.now}
                          labelWidth={LABEL_W}
                          onPressMarker={(lane, m) => (m.kind === 'fill' ? openDay(m.t, lane.key) : openById(lane.key))}
                          onPressLane={(lane) => openById(lane.key)}
                        />
                      </View>
                    ) : null}
                    <View style={s.chartFoot}>
                      <Segmented
                        options={PERIODS.map((p) => ({ key: p, label: p }))}
                        value={period}
                        onChange={setPeriod}
                      />
                      <Text variant="caption" tone="fg3" style={s.legend}>
                        Sessions' value, SPY dashed. Dots are fills; hollow dots are planned rebalances.
                      </Text>
                    </View>
                  </View>
                ) : (
                  <Card>
                    <Text variant="small" tone="fg2">
                      The curve appears once a session has a day of history.
                    </Text>
                  </Card>
                )}
              </View>

              {closed ? (
                <ClosedRecap
                  recap={closedRecap(d.sessions)}
                  nextOpen={d.marketNextOpen}
                  now={d.now}
                  waiting={rows.filter((r) => r.state === 'frozen').map((r) => r.title)}
                  onOpen={openById}
                />
              ) : null}

              {rows.length ? (
                <>
                  <SectionHead title="Sessions" link="See all" onPress={() => router.push('/sessions')} />
                  <SessionsByAccount rows={rows} split={split} nextFor={nextFor} onOpen={openSession} />
                </>
              ) : (
                <Card>
                  <Text variant="bodyStrong">No sessions yet</Text>
                  <Text variant="small" tone="fg2">
                    Backtest a strategy, then start it on paper from its page.
                  </Text>
                </Card>
              )}

              {!closed ? (
                <>
                  <SectionHead title="Today and next" link="Activity" onPress={() => router.push('/portfolio/activity')} />
                  <TimelineCard entries={entries} now={d.now} onOpenSession={openById} />
                </>
              ) : null}
              <Text variant="caption" tone="fg3" style={s.asOf}>
                {d.equityAsOf ? `Figures from ${asOfLabel(d.equityAsOf.getTime(), d.now)}.` : ''}
              </Text>
            </>
          )}
        </Animated.ScrollView>
        {mode === 'open' || mode === 'closed' ? (
          <Animated.View pointerEvents="box-none" style={[s.compact, { paddingTop: insets.top, opacity: compactOpacity }]}>
            <View style={s.compactRow}>
              <Text variant="numStrong">{money(d.totalEquity, 2)}</Text>
              <DayChange amount={d.dayPnl} percent={d.dayPnlPercent} />
              <View style={s.flex} />
              <SearchButton color={c.fg2} />
              <HeaderActions />
            </View>
          </Animated.View>
        ) : null}
      </SafeAreaView>
      <DaySheet subject={sheet} onClose={() => setSheet(null)} />
    </Canvas>
  );
}

/** "16:00 today" or "16:00, Nov 17". */
function asOfLabel(t: number, now: number): string {
  const day = dayLabel(t, now);
  return day === 'Today' || day === 'Yesterday' ? `${hm(t)} ${day.toLowerCase()}` : `${hm(t)}, ${day}`;
}

/** SPY's percent curve as values on the sessions' scale, starting where the curve starts. */
function rebasedBenchmark(bench: readonly { timestamp: string; value: number }[], curve: readonly Point[], from: number): Point[] {
  if (bench.length < 2 || curve.length < 2) return [];
  const pts = bench.map((b) => ({ t: new Date(b.timestamp).getTime(), v: b.value })).filter((p) => Number.isFinite(p.t));
  const start = pts.find((p) => p.t >= from);
  const base = curve.find((p) => p.t >= from);
  if (!start || !base) return [];
  return pts.filter((p) => p.t >= from).map((p) => ({ t: p.t, v: (base.v * (1 + p.v / 100)) / (1 + start.v / 100) }));
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  body: { paddingHorizontal: space.gutter, paddingTop: 6, paddingBottom: 40, gap: space.gap },
  hero: { gap: 4, marginTop: 6 },
  chart: { gap: 8, padding: 8, marginHorizontal: -8, borderRadius: 12, backgroundColor: t.c.canvas + "b3" },
  lanes: { marginTop: 4 },
  chartFoot: { gap: 8, alignItems: 'center', marginTop: 4 },
  legend: { textAlign: 'center' },
  asOf: { textAlign: 'center', marginTop: 4 },
  compact: { position: 'absolute', top: 0, left: 0, right: 0, backgroundColor: t.c.canvas, borderBottomWidth: 1, borderColor: t.c.line },
  compactRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: space.gutter, paddingVertical: 8 },
}));
