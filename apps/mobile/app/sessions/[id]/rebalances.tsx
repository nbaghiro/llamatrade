import { marketDataClient } from '@llamatrade/core/net';
import { num, toDate } from '@llamatrade/core/format';
import { Timeframe } from '@llamatrade/core/proto/market_data_pb';
import { barsToCandles } from '@llamatrade/core/stores/markets';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';

import { clock, dayOrToday, fillsOf } from '../../../src/sessions/data';
import { MixChart } from '../../../src/sessions/MixChart';
import { displayName, formatQty, laneX, mixOverTime, rebalanceDays, weightChange, weightPct, type DailyClose } from '../../../src/sessions/model';
import { makeStyles, radius, useTheme } from '../../../src/theme';
import { Card, Loading, PanelError, Screen, Text } from '../../../src/ui';

/** One session's rebalances (sessions/rebalance2 A): the mix over time, one day opened. */
export default function RebalancesScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const detail = useTradingStore((st) => (st.detail?.session.id === id ? st.detail : null));
  const detailError = useTradingStore((st) => st.detailError);
  const [closes, setCloses] = useState<Record<string, DailyClose[]> | null>(null);
  const [picked, setPicked] = useState<number | null>(null);

  useEffect(() => {
    if (!id || detail) return;
    useTradingStore.getState().loadSession(id, new Date(Date.now() - 400 * 86_400_000)).catch(() => undefined);
  }, [id, detail]);

  const fills = useMemo(() => (detail ? fillsOf(detail.orders.filter((o) => o.sessionId === detail.session.id)) : []), [detail]);
  const days = useMemo(() => rebalanceDays(fills), [fills]);
  const start = toDate(detail?.session.startedAt)?.getTime() ?? fills[0]?.at ?? Date.now();
  const symbols = useMemo(() => [...new Set(fills.map((f) => f.symbol))], [fills]);

  useEffect(() => {
    if (!detail || symbols.length === 0) return;
    let live = true;
    marketDataClient
      .getMultiBars({
        symbols,
        timeframe: Timeframe.TIMEFRAME_1DAY,
        start: { seconds: BigInt(Math.floor(start / 1000) - 86_400), nanos: 0 },
        end: { seconds: BigInt(Math.floor(Date.now() / 1000)), nanos: 0 },
      })
      .then((r) => {
        if (!live) return;
        const out: Record<string, DailyClose[]> = {};
        for (const sym of symbols) out[sym] = barsToCandles(r.bars[sym]?.bars ?? []).map((k) => ({ t: k.time * 1000, close: k.close }));
        setCloses(out);
      })
      .catch(() => live && setCloses({}));
    return () => {
      live = false;
    };
  }, [detail, symbols, start]);

  const allocated = detail?.execution ? num(detail.execution.allocatedCapital) : 0;
  const mix = useMemo(() => (closes ? mixOverTime(allocated, fills, closes) : null), [closes, allocated, fills]);
  const openDay = picked ?? days[days.length - 1]?.day ?? null;
  const opened = days.find((d) => d.day === openDay) ?? null;
  const change = mix && opened ? weightChange(mix, opened.day) : [];
  const title = detail ? displayName(detail.session.name) : 'Session';
  const back = { label: title, onPress: () => (router.canGoBack() ? router.back() : router.replace({ pathname: '/sessions/[id]', params: { id: id ?? '' } })) };
  const orderCount = fills.length;

  return (
    <Screen title="Rebalances" back={back} art="bold" artSeed={`rebalances-${id}`}>
      {!detail ? (
        detailError ? <PanelError title="This session could not be loaded" detail={detailError} /> : <Loading label="Loading rebalances" />
      ) : days.length === 0 ? (
        <Card>
          <Text variant="small" tone="fg2">No orders have filled for this session yet, so there's no rebalance to show.</Text>
        </Card>
      ) : (
        <>
          <Text variant="small" tone="fg2" style={s.subtitle}>
            {days.length === 1 ? '1 day with orders' : `${days.length} days with orders`} · {orderCount === 1 ? '1 filled order' : `${orderCount} filled orders`}
          </Text>

          <Card style={s.chartCard}>
            {mix === null ? (
              <View style={s.chartBox}>
                <Loading label="Rebuilding the mix" />
              </View>
            ) : mix.days.length > 1 ? (
              <MixChart mix={mix} selected={opened?.day} />
            ) : (
              <View style={[s.chartBox, s.center]}>
                <Text variant="small" tone="fg3">Daily prices for these symbols aren't available, so the mix can't be drawn.</Text>
              </View>
            )}
            <View style={s.markers}>
              <View style={[s.track, { backgroundColor: c.accent }]} />
              {days.map((d) => {
                const on = d.day === openDay;
                return (
                  <Pressable
                    key={d.day}
                    accessibilityRole="button"
                    accessibilityLabel={`Open ${dayOrToday(d.at)}`}
                    hitSlop={6}
                    onPress={() => setPicked(d.day)}
                    style={[
                      s.marker,
                      { left: `${laneX(d.at, start, Date.now()) * 100}%`, backgroundColor: c.accentFill, borderColor: on ? c.fg : c.accentFill },
                      on ? s.markerOn : null,
                    ]}
                  >
                    {on ? <Text variant="caption" color={c.accentInk} style={s.markerText}>{d.fills.length}</Text> : null}
                  </Pressable>
                );
              })}
            </View>
            <View style={s.axis}>
              <Text variant="numSmall" tone="fg3">{dayOrToday(start)}</Text>
              <Text variant="numSmall" tone="fg3">Today</Text>
            </View>
            {mix && mix.days.length > 1 ? (
              <Text variant="caption" tone="fg3">
                Bands from the bottom: {mix.symbols.join(', ')}, then cash in grey. Rebuilt from fills and daily closes.
              </Text>
            ) : null}
          </Card>

          {opened ? (
            <Card style={s.detail}>
              <View style={s.detailHead}>
                <Text variant="subhead">{`${dayOrToday(opened.at)}, ${clock(opened.at)}`}</Text>
                <Text variant="small" tone="fg2">{opened.fills.length === 1 ? '1 filled' : `${opened.fills.length} filled`}</Text>
              </View>
              <Text variant="small" tone="fg3">The reason the rule chose this mix isn't recorded yet, so only the orders are shown.</Text>
              {change
                .filter((w) => opened.fills.some((f) => f.symbol === w.symbol) || w.before > 0 || w.after > 0)
                .map((w) => (
                  <View key={w.symbol} style={[s.kv, { borderColor: c.line }]}>
                    <Text variant="small" tone="fg2">{w.symbol}</Text>
                    <Text variant="num">{`${weightPct(w.before)} → ${weightPct(w.after)}`}</Text>
                  </View>
                ))}
              <View style={[s.kv, { borderColor: c.line }]}>
                <Text variant="small" tone="fg2">Orders</Text>
                <Text variant="num" style={s.orders}>
                  {opened.fills.map((f) => `${f.side === 'buy' ? 'Buy' : 'Sell'} ${formatQty(f.quantity)} ${f.symbol}`).join(' · ')}
                </Text>
              </View>
            </Card>
          ) : null}
        </>
      )}
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  subtitle: { marginTop: -8 },
  chartBox: { height: 200 },
  chartCard: { borderRadius: radius.lg, paddingHorizontal: 12, gap: 2 },
  center: { alignItems: 'center', justifyContent: 'center', paddingHorizontal: 20 },
  markers: { height: 26, justifyContent: 'center', marginTop: 8, marginHorizontal: 8 },
  track: { height: 1.5, opacity: 0.5 },
  marker: { position: 'absolute', width: 12, height: 12, borderRadius: 6, marginLeft: -6, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  markerOn: { width: 22, height: 22, borderRadius: 11, marginLeft: -11 },
  markerText: { fontSize: 10, lineHeight: 12 },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 2, marginBottom: 4 },
  detail: { gap: 8, borderRadius: radius.lg },
  detailHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  kv: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, borderTopWidth: 1, paddingTop: 9 },
  orders: { flexShrink: 1, textAlign: 'right' },
}));
