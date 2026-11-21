import { money, num } from '@llamatrade/core/format';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import type { Candle } from '@llamatrade/core/stores/markets';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { View } from 'react-native';

import { loadSeries, useBoard } from '../../src/markets/board';
import { CandleChart } from '../../src/markets/charts';
import { holdersBySymbol, moveTone, price, signedPct, type Range } from '../../src/markets/model';
import { clock, day, fillsOf, useSessionRows } from '../../src/sessions/data';
import { formatQty, weightPct } from '../../src/sessions/model';
import { ModeTag } from '../../src/sessions/parts';
import { makeStyles, radius } from '../../src/theme';
import { Card, ListRow, Loading, PanelError, Screen, Segmented, Text } from '../../src/ui';

const RANGES = [
  { key: '1D', label: '1D' },
  { key: '1M', label: '1M' },
  { key: '6M', label: '6M' },
  { key: '1Y', label: '1Y' },
] as const;

const back = { label: 'Markets', onPress: () => (router.canGoBack() ? router.back() : router.replace('/markets')) };

/** One symbol (phone-nav2 A pushed, markets2 A): price, candles with fills and costs, its holders. */
export default function SymbolScreen() {
  const s = useStyles();
  const { symbol: raw } = useLocalSearchParams<{ symbol: string }>();
  const symbol = (raw ?? '').toUpperCase();
  const [range, setRange] = useState<Range>('6M');
  const [attempt, setAttempt] = useState(0);
  const [series, setSeries] = useState<{ candles: Candle[]; error: string | null } | null>(null);
  const move = useBoard((st) => st.moves[symbol]);
  const name = useBoard((st) => st.names[symbol]);
  const rows = useSessionRows();
  const positions = useTradingStore((st) => st.positions);
  const orders = useTradingStore((st) => st.orders);

  useEffect(() => {
    if (!symbol) return;
    useBoard.getState().load([symbol]).catch(() => undefined);
    if (!useTradingStore.getState().loaded) useTradingStore.getState().loadBlotter().catch(() => undefined);
  }, [symbol]);

  useEffect(() => {
    if (!symbol) return;
    let live = true;
    setSeries(null);
    loadSeries(symbol, range)
      .then((r) => live && setSeries(r))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [symbol, range, attempt]);

  const holders = useMemo(() => {
    const map = holdersBySymbol(
      positions.map((p) => ({ symbol: p.symbol, sessionId: p.sessionId, shares: num(p.quantity), avgPrice: num(p.averageEntryPrice), value: num(p.marketValue) })),
      rows.map((r) => ({ id: r.id, title: r.title, mode: r.mode, frozen: r.state === 'frozen', stopped: r.state === 'stopped' })),
    );
    return map.get(symbol) ?? [];
  }, [positions, rows, symbol]);

  const modeOf = useMemo(() => {
    const m = new Map(rows.map((r) => [r.id, r.mode]));
    return (id: string) => m.get(id) ?? 'paper';
  }, [rows]);

  const symbolOrders = useMemo(() => orders.filter((o) => o.symbol === symbol), [orders, symbol]);
  const fills = useMemo(() => fillsOf(symbolOrders), [symbolOrders]);
  const sessionOf = useMemo(() => new Map(symbolOrders.map((o) => [o.id, o.sessionId])), [symbolOrders]);
  const marks = fills.map((f) => ({ side: f.side, price: f.price, at: f.at, sessionId: sessionOf.get(f.id) ?? '' }));
  const latest = [...fills].sort((a, b) => b.at - a.at)[0];
  const titleOf = new Map(rows.map((r) => [r.id, r.title]));

  return (
    <Screen title={symbol} back={back} eyebrow={name || undefined} art="bold" artSeed={`symbol-${symbol}`}>
      <View style={s.priceRow}>
        <Text variant="hero" style={s.price}>{move ? price(move.price) : '–'}</Text>
        {move ? (
          <Text variant="num" tone={moveTone(move.changePct)} style={s.change}>
            {signedPct(move.changePct)} today
          </Text>
        ) : null}
      </View>

      <View>
        {series === null ? (
          <View style={s.chartBox}>
            <Loading label="Loading prices" />
          </View>
        ) : series.error ? (
          <PanelError title="Prices could not be loaded" detail={series.error} onRetry={() => setAttempt((n) => n + 1)} />
        ) : series.candles.length === 0 ? (
          <View style={[s.chartBox, s.center]}>
            <Text variant="small" tone="fg2" style={s.centerText}>
              {range === '1D' ? 'Intraday bars aren’t available from the market data service yet. Pick a longer range.' : 'No prices for this range.'}
            </Text>
          </View>
        ) : (
          <Card style={s.chartCard}>
            <CandleChart
              candles={series.candles}
              fills={marks}
              fillMode={modeOf}
              costs={holders.map((h) => ({ price: h.avgPrice, mode: h.mode, label: h.title }))}
            />
          </Card>
        )}
      </View>
      <Segmented options={RANGES} value={range} onChange={setRange} style={s.ranges} />
      {marks.length || holders.length ? (
        <Text variant="caption" tone="fg3">
          B and S mark your fills. Lines show each session’s average cost; dashed is paper. Held share is of the session’s holdings.
        </Text>
      ) : null}

      <Text variant="subhead" style={s.section}>
        {holders.length === 0 ? 'In your sessions' : holders.length === 1 ? 'Held in 1 session' : `Held in ${holders.length} sessions`}
      </Text>
      {holders.length === 0 ? (
        <Card>
          <Text variant="small" tone="fg2">No running session holds {symbol}.</Text>
        </Card>
      ) : (
        <Card style={s.list}>
          {holders.map((h, i) => (
            <ListRow
              key={h.sessionId}
              onPress={() => router.push({ pathname: '/sessions/[id]', params: { id: h.sessionId } })}
              last={i === holders.length - 1 && !latest}
              label={
                <View style={s.holderTitle}>
                  <Text variant="body" numberOfLines={1} style={s.flexShrink}>{h.title}</Text>
                  {h.frozen ? <Text variant="small" tone="risk">frozen</Text> : null}
                </View>
              }
              sub={
                <View style={s.holderSub}>
                  <ModeTag mode={h.mode} />
                  <Text variant="small" tone="fg3" numberOfLines={1} style={s.flexShrink}>
                    {formatQty(h.shares)} sh · avg {price(h.avgPrice)}
                    {h.weight !== null ? ` · ${weightPct(h.weight)}` : ''}
                  </Text>
                </View>
              }
              value={<Text variant="num">{money(h.value, 2)}</Text>}
            />
          ))}
          {latest ? (
            <ListRow
              last
              label={`${latest.side === 'buy' ? 'Bought' : 'Sold'} ${formatQty(latest.quantity)} on ${day(latest.at)}`}
              sub={`${clock(latest.at)} at $${price(latest.price)} · ${money(latest.quantity * latest.price, 2)}${titleOf.get(sessionOf.get(latest.id) ?? '') ? ` · ${titleOf.get(sessionOf.get(latest.id) ?? '')}` : ''}`}
            />
          ) : null}
        </Card>
      )}
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginTop: -4 },
  price: { fontSize: 40, lineHeight: 46 },
  change: { fontSize: 15 },
  chartBox: { height: 230 },
  chartCard: { borderRadius: radius.lg, paddingHorizontal: 10, paddingVertical: 8 },
  center: { alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  centerText: { textAlign: 'center' },
  ranges: { alignSelf: 'center' },
  section: { marginTop: 8, marginBottom: -4 },
  list: { paddingVertical: 2, borderRadius: radius.lg },
  holderTitle: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  holderSub: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 },
  flexShrink: { flexShrink: 1 },
}));
