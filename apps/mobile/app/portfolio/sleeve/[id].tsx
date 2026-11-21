import { money, qty } from '@llamatrade/core/format';
import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router, useLocalSearchParams } from 'expo-router';
import { Clock } from 'lucide-react-native';
import { useEffect, useMemo } from 'react';
import { View } from 'react-native';

import { AnnotatedCurve } from '../../../src/charts/AnnotatedCurve';
import { Lanes, type Lane } from '../../../src/charts/Lanes';
import { fillsOf } from '../../../src/home/data';
import { cadenceOf, displayName, nextRebalance, lastFillDay, type Point } from '../../../src/home/model';
import { PaperAmount } from '../../../src/home/PaperAmount';
import { dayLabel } from '../../../src/home/when';
import { estimateOrders, ordersSentence } from '../../../src/portfolio/model';
import { makeStyles, radius, useTheme } from '../../../src/theme';
import { Card, Loading, Notice, PanelError, Screen, StatusMark, Text } from '../../../src/ui';
import { runStateOfExecution } from '../../../src/ui/status';

const LABEL_W = 40;
const DAY = 86_400_000;

/** One sleeve (sleeve2 A): its curve against SPY, a lane per holding and the next rebalance estimated. */
export default function SleeveScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { sleeve, sleeveLoading, sleeveError, fetchSleeve } = usePortfolioStore();
  const { orders, sessions, curves, loadCurves, loadBlotter } = useTradingStore();

  useEffect(() => {
    if (id) fetchSleeve(id);
    loadBlotter().then(loadCurves, () => undefined);
  }, [id, fetchSleeve, loadBlotter, loadCurves]);

  const mine = sleeve?.sleeveId === id ? sleeve : null;
  const session = sessions.find((x) => x.sleeveId === id) ?? null;
  const fills = useMemo(
    () => fillsOf(orders).filter((f) => (session ? f.sessionId === session.id : mine ? f.strategyId === mine.strategyId : false)),
    [orders, session, mine],
  );
  const curve = mine ? curves[mine.executionId] : undefined;
  const series: Point[] = (curve?.points ?? []).map((p) => ({ t: Number(p.timestamp?.seconds ?? 0) * 1000, v: Number(p.equity?.value ?? 0) }));
  const bench = rebase(
    (curve?.benchmark ?? []).map((p) => ({ t: Number(p.timestamp?.seconds ?? 0) * 1000, v: Number(p.equity?.value ?? 0) })),
    series[0]?.v ?? 0,
  );
  const now = Date.now();
  const from = series[0]?.t ?? now - 30 * DAY;

  const symbols = useMemo(() => {
    const set = new Set<string>([...(mine?.holdings.map((h) => h.symbol) ?? []), ...Object.keys(mine?.targets ?? {})]);
    return [...set].sort();
  }, [mine]);
  const lanes: Lane[] = symbols.map((sym) => {
    const days = new Map<number, number>();
    for (const f of fills) {
      if (f.symbol !== sym) continue;
      const d = new Date(f.t);
      d.setHours(0, 0, 0, 0);
      days.set(d.getTime(), (days.get(d.getTime()) ?? 0) + 1);
    }
    return {
      key: sym,
      label: sym,
      start: from,
      tone: mine?.frozen ? 'risk' : mine?.live ? 'ink' : 'accent',
      dashed: !mine?.live,
      markers: [...days.entries()].map(([day, count]) => ({ t: day + DAY / 2, kind: 'fill' as const, count, id: String(day) })),
    };
  });

  const cadence = cadenceOf(mine?.rebalance ?? '');
  const running = mine ? runStateOfExecution(mine.executionStatus) === 'running' && !mine.frozen : false;
  const next =
    cadence && running ? nextRebalance(cadence, lastFillDay(fills, { strategyId: mine?.strategyId ?? '', sessionId: session?.id ?? null }) ?? mine?.startedAt?.getTime() ?? null, now) : null;
  const estimate = mine ? estimateOrders(mine.holdings, mine.targets, mine.cash ?? 0) : [];
  const value = mine ? mine.holdings.reduce((sum, h) => sum + h.marketValue, 0) + (mine.cash ?? 0) : 0;
  const title = mine ? displayName(mine.name) : 'Sleeve';
  const paper = !mine?.live;

  return (
    <Screen
      title={title}
      artSeed={`sleeve-${id ?? ''}`}
      art="bold"
      back={{ label: 'Portfolio', onPress: () => (router.canGoBack() ? router.back() : router.replace('/portfolio')) }}
      eyebrow={mine ? `${mine.live ? 'LIVE' : 'PAPER'} SESSION` : undefined}
      refreshing={sleeveLoading && mine !== null}
      onRefresh={() => id && fetchSleeve(id)}
    >
      {sleeveLoading && !mine ? (
        <Loading label="Loading this sleeve" />
      ) : sleeveError && !mine ? (
        <PanelError title="Couldn't load this sleeve" detail={sleeveError} onRetry={() => id && fetchSleeve(id)} />
      ) : mine ? (
        <>
          <View style={s.hero}>
            <PaperAmount paper={paper} variant="hero">
              {money(value, 2)}
            </PaperAmount>
            <StatusMark state={mine.frozen ? 'frozen' : runStateOfExecution(mine.executionStatus)} />
          </View>
          {mine.frozen ? (
            <Notice
              title="This sleeve is frozen."
              detail="Alpaca and the ledger disagree about its holdings, so it won't trade until that's resolved."
              onPress={session ? () => router.push({ pathname: '/sessions/[id]', params: { id: session.id } }) : undefined}
            />
          ) : null}

          {series.length > 1 ? (
            <View style={s.chart}>
              <AnnotatedCurve series={series} benchmark={bench} from={from} until={now} inset={LABEL_W} height={140} accessibilityLabel={`${title} against SPY`} />
              {lanes.length ? <Lanes lanes={lanes} from={from} until={now} labelWidth={LABEL_W} /> : null}
              <Text variant="caption" tone="fg3" style={s.center}>
                SPY dashed, on the same dates. Dots are fills.
              </Text>
            </View>
          ) : null}

          {next !== null ? (
            <View style={s.next}>
              <Clock color={c.fg3} size={15} strokeWidth={1.8} style={s.nextIcon} />
              <Text variant="small" tone="fg2" style={s.flex}>
                <Text variant="smallStrong">Rebalances {dayLabel(next, now).toLowerCase() === 'today' ? 'today' : dayLabel(next, now)}.</Text>
                {estimate.length
                  ? ` At the latest prices that's ${ordersSentence(estimate)}. This is an estimate; the session prices its orders when it runs.`
                  : Object.keys(mine.targets).length
                    ? ' At the latest prices it is already on target.'
                    : ' Its weights depend on its rules, so the orders are known only when it runs.'}
              </Text>
            </View>
          ) : null}

          <Card style={s.list}>
            {mine.holdings.length === 0 ? (
              <Text variant="small" tone="fg2" style={s.empty}>
                No holdings. The sleeve is in cash.
              </Text>
            ) : null}
            {mine.holdings.map((h, i) => {
              const weight = value > 0 ? (h.marketValue / value) * 100 : 0;
              const target = mine.targets[h.symbol];
              return (
                <View key={h.symbol} style={[s.row, i < mine.holdings.length - 1 || mine.cash ? s.divider : null]}>
                  <Text variant="numStrong" style={s.sym}>
                    {h.symbol}
                  </Text>
                  <Text variant="numSmall" tone="fg3" style={s.flex}>
                    {qty(h.qty)} sh · {weight.toFixed(1)}%{target !== undefined ? ` of ${(target * 100).toFixed(0)}%` : ''}
                  </Text>
                  <PaperAmount paper={paper} variant="num">
                    {money(h.marketValue, 2)}
                  </PaperAmount>
                </View>
              );
            })}
            {mine.cash ? (
              <View style={s.row}>
                <Text variant="numStrong" tone="fg2" style={s.sym}>
                  Cash
                </Text>
                <View style={s.flex} />
                <PaperAmount paper={paper} variant="num" tone="fg2">
                  {money(mine.cash, 2)}
                </PaperAmount>
              </View>
            ) : null}
          </Card>
        </>
      ) : null}
    </Screen>
  );
}

/** A series scaled so its first value equals `start`. */
function rebase(points: Point[], start: number): Point[] {
  const first = points.find((p) => p.v > 0);
  if (!first || !(start > 0)) return [];
  return points.map((p) => ({ t: p.t, v: (p.v * start) / first.v }));
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  center: { textAlign: 'center' },
  hero: { gap: 6 },
  chart: { gap: 8, padding: 8, marginHorizontal: -8, borderRadius: 12, backgroundColor: t.c.canvas + "b3" },
  next: {
    flexDirection: 'row',
    gap: 10,
    padding: 12,
    borderRadius: radius.md,
    backgroundColor: t.c.sunk,
    borderWidth: 1,
    borderColor: t.c.line,
  },
  nextIcon: { marginTop: 2 },
  list: { paddingVertical: 2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  sym: { width: 52 },
  empty: { paddingVertical: 12 },
}));
