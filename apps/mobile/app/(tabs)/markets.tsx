import { num } from '@llamatrade/core/format';
import { MarketStatus } from '@llamatrade/core/proto/market_data_pb';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';

import { useBoard, clockLine } from '../../src/markets/board';
import { Sparkline } from '../../src/markets/charts';
import { holderLine, holdersBySymbol, moveTone, price, signedPct, sortByMove, symbolsFor, type Holder, type Segment } from '../../src/markets/model';
import { clock, useSessionRows } from '../../src/sessions/data';
import { makeStyles, radius, useTheme } from '../../src/theme';
import { Card, EmptyState, Loading, Screen, Segmented, Text } from '../../src/ui';

const SEGMENTS = [
  { key: 'held', label: 'Held' },
  { key: 'indexes', label: 'Indexes' },
  { key: 'watch', label: 'Watch' },
] as const;

/** Markets tab (phone-nav2 A, attention2 A): held, index and watch symbols with today's move. */
export default function MarketsScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const [segment, setSegment] = useState<Segment>('held');
  const rows = useSessionRows();
  const positions = useTradingStore((st) => st.positions);
  const blotterLoaded = useTradingStore((st) => st.loaded);
  const { moves, sparks, clock: market, loading, error, load, loadClock } = useBoard();

  const holders = useMemo(
    () =>
      holdersBySymbol(
        positions.map((p) => ({
          symbol: p.symbol,
          sessionId: p.sessionId,
          shares: num(p.quantity),
          avgPrice: num(p.averageEntryPrice),
          value: num(p.marketValue),
        })),
        rows.map((r) => ({ id: r.id, title: r.title, mode: r.mode, frozen: r.state === 'frozen', stopped: r.state === 'stopped' })),
      ),
    [positions, rows],
  );
  const held = useMemo(() => [...holders.keys()], [holders]);
  const symbols = useMemo(() => sortByMove(symbolsFor(segment, held), moves), [segment, held, moves]);

  useEffect(() => {
    loadClock().catch(() => undefined);
  }, [loadClock]);
  useEffect(() => {
    load(symbolsFor(segment, held)).catch(() => undefined);
  }, [segment, held, load]);

  const refresh = () => {
    loadClock().catch(() => undefined);
    useTradingStore.getState().loadBlotter().catch(() => undefined);
    load(symbolsFor(segment, held)).catch(() => undefined);
  };

  const status = clockLine(market, clock);
  const waitingForHeld = segment === 'held' && !blotterLoaded;

  return (
    <Screen title="Markets" tab art="bold" artSeed="markets-tab" refreshing={loading} onRefresh={refresh}>
      <View style={s.bar}>
        {status ? (
          <View style={s.status}>
            <View style={[s.dot, { backgroundColor: market?.status === MarketStatus.OPEN ? c.accent : c.fg3 }]} />
            <Text variant="small" tone="fg2" numberOfLines={1}>{status}</Text>
          </View>
        ) : (
          <View />
        )}
        <Segmented options={SEGMENTS} value={segment} onChange={setSegment} />
      </View>

      {waitingForHeld ? (
        <Loading label="Loading what your sessions hold" />
      ) : symbols.length === 0 ? (
        <EmptyState
          title={segment === 'held' ? 'No session holds anything yet' : 'Nothing to show'}
          detail={segment === 'held' ? 'Symbols appear here once a running session buys them.' : undefined}
        />
      ) : (
        <Card style={s.card}>
          {symbols.map((sym, i) => (
            <SymbolRow
              key={sym}
              symbol={sym}
              holders={holders.get(sym) ?? []}
              move={moves[sym]}
              spark={sparks[sym]}
              last={i === symbols.length - 1}
            />
          ))}
        </Card>
      )}

      {error ? <Text variant="small" tone="risk">{error} Pull down to try again.</Text> : null}
      <Text variant="small" tone="fg3">Sorted by today's move. Prices from Alpaca, IEX feed.</Text>
    </Screen>
  );
}

function SymbolRow({
  symbol,
  holders,
  move,
  spark,
  last,
}: {
  symbol: string;
  holders: readonly Holder[];
  move?: { price: number; changePct: number };
  spark?: readonly number[];
  last: boolean;
}) {
  const s = useStyles();
  const { c } = useTheme();
  const frozen = holders.some((h) => h.frozen);
  const line = holderLine(holders);
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push({ pathname: '/markets/[symbol]', params: { symbol } })}
      style={({ pressed }) => [s.row, last ? null : { borderBottomWidth: 1, borderColor: c.line }, pressed ? { opacity: 0.7 } : null]}
    >
      <View style={s.rowMain}>
        <Text variant="numStrong" style={s.sym}>{symbol}</Text>
        {line ? (
          <Text variant="small" tone="fg2" numberOfLines={1}>
            {line}
            {frozen ? <Text variant="small" tone="risk"> · frozen</Text> : null}
          </Text>
        ) : null}
      </View>
      <Sparkline values={spark ?? []} />
      <View style={s.figures}>
        <Text variant="num">{move ? price(move.price) : '–'}</Text>
        {move ? <Text variant="numSmall" tone={moveTone(move.changePct)}>{signedPct(move.changePct)}</Text> : null}
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  bar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  status: { flexDirection: 'row', alignItems: 'center', gap: 7, flexShrink: 1 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  card: { paddingVertical: 0, borderRadius: radius.lg },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 13 },
  rowMain: { flex: 1, minWidth: 0, gap: 2 },
  sym: { fontSize: 15, lineHeight: 20 },
  figures: { alignItems: 'flex-end', minWidth: 64 },
}));
