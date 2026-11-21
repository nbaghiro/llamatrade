import { BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, type ReactNode } from 'react';
import { View } from 'react-native';

import {
  heldPeriods,
  MAX_PINS,
  maxDrawdown,
  monthLabel,
  resultLanes,
  resultSentence,
  switchesOf,
  type HoldingLane,
} from '../../../src/account/firstResult';
import { useBacktestResult } from '../../../src/account/useBacktestResult';
import { LineChart } from '../../../src/charts/LineChart';
import { makeStyles, useTheme } from '../../../src/theme';
import { Button, Card, Loading, PanelError, Screen, Text, pnlTone } from '../../../src/ui';

const back = { label: 'Back', onPress: () => (router.canGoBack() ? router.back() : router.replace('/onboarding')) };

const pct = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)}%`;
const money = (v: number) => `$${Math.round(v).toLocaleString('en-US')}`;

/** Thin a long daily series for a phone-width chart, keeping the last point. */
function thin<T>(xs: readonly T[], max = 160): T[] {
  if (xs.length <= max) return [...xs];
  const step = Math.ceil(xs.length / max);
  return xs.filter((_, i) => i % step === 0 || i === xs.length - 1);
}

function Lane({ lane, accent, last }: { lane: HoldingLane; accent: boolean; last: boolean }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={[s.lane, last ? null : s.divider]}>
      <Text variant="caption" tone="fg2" style={s.laneLabel} numberOfLines={1}>
        {lane.symbols.join(' · ')}
      </Text>
      <View style={s.track}>
        {lane.spans.map((sp, i) => (
          <View
            key={i}
            style={[s.bar, { left: `${sp.from * 100}%`, width: `${Math.max(0.6, (sp.to - sp.from) * 100)}%`, backgroundColor: accent ? c.accent : c.fg3 }]}
          />
        ))}
      </View>
    </View>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <Screen title="Backtest" back={back} art="bold" artSeed="onboarding-result">
      {children}
    </Screen>
  );
}

export default function FirstResultScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { run, name, series, trades, loading, error, reload } = useBacktestResult(id);

  const view = useMemo(() => {
    if (!series || series.values.length < 2) return null;
    const { dates, values, benchmark } = series;
    const start = dates[0];
    const end = dates[dates.length - 1];
    const periods = trades ? heldPeriods(trades, end) : [];
    const span = Math.max(1, end.getTime() - start.getTime());
    const switches = switchesOf(periods);
    const { lanes, bySymbol } = resultLanes(periods, start, end);
    return {
      start,
      end,
      first: values[0],
      last: values[values.length - 1],
      total: values[values.length - 1] / values[0] - 1,
      benchTotal: benchmark.length > 1 ? benchmark[benchmark.length - 1] / benchmark[0] - 1 : null,
      drop: maxDrawdown(values),
      benchDrop: benchmark.length > 1 ? maxDrawdown(benchmark) : null,
      lanes,
      bySymbol,
      pins: switches.length <= MAX_PINS ? switches.map((p) => (p.from.getTime() - start.getTime()) / span) : [],
      sentence: resultSentence(periods),
      chart: thin(values),
      chartBench: benchmark.length ? thin(benchmark) : undefined,
    };
  }, [series, trades]);

  if (loading && !run) {
    return (
      <Shell>
        <Loading label="Loading the backtest" />
      </Shell>
    );
  }
  if (error || !run) {
    return (
      <Shell>
        <PanelError title="The backtest couldn't be loaded" detail={error ?? undefined} onRetry={reload} />
      </Shell>
    );
  }
  if (run.status !== BacktestStatus.COMPLETED || !view) {
    return (
      <Shell>
        <Card style={s.gap}>
          <Text variant="subhead">This backtest has no result yet</Text>
          <Text variant="small" tone="fg2">{run.statusMessage || 'It is still running, or it stopped before it finished.'}</Text>
        </Card>
      </Shell>
    );
  }

  const bench = series?.benchmarkSymbol || 'SPY';
  const title = name || 'Your backtest';
  const facts = [
    view.benchTotal !== null ? `${bench} ${pct(view.benchTotal)}` : null,
    `worst drop ${Math.abs(view.drop * 100).toFixed(1)}%`,
  ].filter(Boolean);

  return (
    <Shell>
      <View style={s.head}>
        <Text variant="label" tone="fg3">
          {title} · {monthLabel(view.start)} to {monthLabel(view.end)}
        </Text>
        <Text variant="hero">{money(view.last)}</Text>
        <Text variant="small" tone="fg3">
          <Text variant="numSmall" tone={pnlTone(view.total)}>{pct(view.total)}</Text>
          {` from ${money(view.first)} · ${facts.join(' · ')}`}
        </Text>
      </View>

      <View>
        <LineChart values={view.chart} benchmark={view.chartBench} height={160} xLabels={[monthLabel(view.start), monthLabel(view.end)]} />
        {view.pins.map((x, i) => (
          <View key={i} pointerEvents="none" style={[s.pin, { left: `${x * 100}%`, borderColor: c.accent }]} />
        ))}
      </View>
      <View style={s.legend}>
        <View style={s.legendItem}><View style={[s.key, { backgroundColor: c.accent }]} /><Text variant="caption" tone="fg2">{title}</Text></View>
        {view.chartBench ? <View style={s.legendItem}><View style={[s.key, s.keyDash]} /><Text variant="caption" tone="fg2">{bench}</Text></View> : null}
        {view.pins.length ? <View style={s.legendItem}><View style={[s.pinKey, { borderColor: c.accent }]} /><Text variant="caption" tone="fg2">Switch</Text></View> : null}
      </View>

      {view.lanes.length ? (
        <Card style={s.lanes}>
          <Text variant="label" tone="fg3" style={s.lanesHead}>{view.bySymbol ? 'When it held each symbol' : 'What it held'}</Text>
          {view.lanes.map((lane, i) => (
            <Lane key={lane.key} lane={lane} accent={view.bySymbol || i > 0 || view.lanes.length === 1} last={i === view.lanes.length - 1} />
          ))}
        </Card>
      ) : trades === null ? (
        <Loading label="Reading the trades" />
      ) : null}

      {view.sentence ? <Text variant="small" tone="fg2">{view.sentence}</Text> : null}
      {view.benchDrop !== null && view.benchDrop < 0 && view.drop < 0 ? (
        <Text variant="small" tone="fg2">
          {bench}&apos;s worst drop over the same dates was {Math.abs(view.benchDrop * 100).toFixed(1)}%, against {Math.abs(view.drop * 100).toFixed(1)}% here.
        </Text>
      ) : null}

      <Button
        label="Start on paper"
        onPress={() => router.push(run.strategyId ? { pathname: '/sessions/start', params: { strategy: run.strategyId } } : '/sessions/start')}
      />
      <Text variant="caption" tone="fg3" style={s.center}>
        Backtests use past prices and assume fills at the close. Real results will differ.
      </Text>
    </Shell>
  );
}

const useStyles = makeStyles((t) => ({
  gap: { gap: 6 },
  head: { gap: 4 },
  pin: { position: 'absolute', top: 0, bottom: 22, width: 0, borderLeftWidth: 1, borderStyle: 'dashed' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginTop: -4 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  key: { width: 14, height: 2, borderRadius: 1 },
  keyDash: { borderTopWidth: 1.5, borderStyle: 'dashed', borderColor: t.c.fg3, height: 0 },
  pinKey: { width: 0, height: 12, borderLeftWidth: 1, borderStyle: 'dashed' },
  lanes: { paddingVertical: 4 },
  lanesHead: { paddingTop: 8, paddingBottom: 4 },
  lane: { flexDirection: 'row', alignItems: 'center', gap: 10, height: 34 },
  laneLabel: { width: 96 },
  track: { flex: 1, height: 2, backgroundColor: t.c.line },
  bar: { position: 'absolute', top: -1, height: 4, borderRadius: 2 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  center: { textAlign: 'center' },
}));
