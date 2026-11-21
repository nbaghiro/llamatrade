import { money, num, toDate } from '@llamatrade/core/format';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { OrderSide, OrderStatus } from '@llamatrade/core/proto/trading_pb';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router, useLocalSearchParams } from 'expo-router';
import { Check, TriangleAlert } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { useBoard } from '../../../src/markets/board';
import { clock, day } from '../../../src/sessions/data';
import { displayName, formatQty } from '../../../src/sessions/model';
import { againstLimit } from '../../../src/sessions/order';
import { ModeTag } from '../../../src/sessions/parts';
import { InkButton, QuietButton } from '../../../src/sessions/Sheet';
import { makeStyles, radius, useTheme } from '../../../src/theme';
import { Card, Loading, Notice, PanelError, Screen, Text } from '../../../src/ui';

const STATUS_LABEL: Partial<Record<OrderStatus, string>> = {
  [OrderStatus.REJECTED]: 'Rejected',
  [OrderStatus.FILLED]: 'Filled',
  [OrderStatus.CANCELLED]: 'Cancelled',
  [OrderStatus.EXPIRED]: 'Expired',
  [OrderStatus.PARTIAL]: 'Partly filled',
  [OrderStatus.PENDING]: 'Pending',
  [OrderStatus.SUBMITTED]: 'Submitted',
  [OrderStatus.ACCEPTED]: 'Accepted',
};

/** A rejected order (sessions/order2 A): its value against the limit it broke, and ways forward. */
export default function OrderScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { order, orderLoading, orderError, loadOrder, sessions, placeOrder, placing, placeError } = useTradingStore(
    useShallow((st) => ({
      order: st.order,
      orderLoading: st.orderLoading,
      orderError: st.orderError,
      loadOrder: st.loadOrder,
      sessions: st.sessions,
      placeOrder: st.placeOrder,
      placing: st.placing,
      placeError: st.placeError,
    })),
  );
  const [placed, setPlaced] = useState<string | null>(null);
  const symbol = order?.symbol ?? '';
  const last = useBoard((st) => (symbol ? st.moves[symbol]?.price : undefined));

  useEffect(() => {
    if (id) loadOrder(id).catch(() => undefined);
  }, [id, loadOrder]);
  useEffect(() => {
    if (symbol) useBoard.getState().load([symbol]).catch(() => undefined);
  }, [symbol]);

  const back = { label: 'Sessions', onPress: () => (router.canGoBack() ? router.back() : router.replace('/sessions')) };

  if (!order || order.id !== id) {
    return (
      <Screen title="Order" back={back} art="bold" artSeed={`order-${id}`}>
        {orderError ? <PanelError title="This order could not be loaded" detail={orderError} onRetry={() => id && loadOrder(id)} /> : orderLoading ? <Loading label="Loading order" /> : null}
      </Screen>
    );
  }

  const session = sessions.find((x) => x.id === order.sessionId);
  const mode = session?.mode === ExecutionMode.LIVE ? 'live' : 'paper';
  const side = order.side === OrderSide.SELL ? 'Sell' : 'Buy';
  const qty = num(order.quantity);
  const at = toDate(order.submittedAt) ?? toDate(order.createdAt);
  const priceUsed = num(order.limitPrice) || last || 0;
  const rejected = order.status === OrderStatus.REJECTED;
  const read = priceUsed > 0 ? againstLimit(qty, priceUsed, order.statusMessage) : null;
  const fraction = read && read.limit ? Math.min(1, read.limit / Math.max(read.value, read.limit)) : 1;
  const smaller = read?.fits && read.fits > 0 && read.fits < qty ? read.fits : null;

  const place = async (quantity: number) => {
    const o = await placeOrder({
      sessionId: order.sessionId,
      symbol: order.symbol,
      side: order.side === OrderSide.SELL ? 'sell' : 'buy',
      quantity,
      strategyId: order.strategyId || undefined,
      sleeveId: order.sleeveId || undefined,
    });
    if (o) setPlaced(`${side} ${formatQty(quantity)} ${order.symbol} placed. It goes through the session's checks again.`);
  };

  return (
    <Screen
      title={`${side} ${formatQty(qty)} ${order.symbol}`}
      back={back}
      art="bold"
      artSeed={`order-${order.id}`}
      eyebrow={
        <View style={s.eyebrow}>
          <ModeTag mode={mode} />
          <Text variant="small" tone={rejected ? 'risk' : 'fg2'}>
            {STATUS_LABEL[order.status] ?? 'Order'}
            {at ? ` ${day(at.getTime())}, ${clock(at.getTime())}` : ''}
          </Text>
        </View>
      }
    >
      {session ? <Text variant="small" tone="fg2" style={s.subtitle}>{displayName(session.name)}</Text> : null}

      {read ? (
        <Card style={s.valueCard}>
          <View style={s.valueRow}>
            <Text variant="numLarge">{money(read.value, 2)}</Text>
            {read.over > 0 ? <Text variant="num" tone="risk">{money(read.over, 2)} over</Text> : null}
          </View>
          {read.limit ? (
            <>
              <View style={[s.bar, { backgroundColor: c.sunk }]}>
                <View style={{ flex: fraction, backgroundColor: c.accentFill, borderTopLeftRadius: 4, borderBottomLeftRadius: 4 }} />
                {read.over > 0 ? <View style={{ flex: 1 - fraction, backgroundColor: c.risk, borderTopRightRadius: 4, borderBottomRightRadius: 4 }} /> : null}
              </View>
              <Text variant="numSmall" tone="fg2">{money(read.limit, 0)} limit</Text>
            </>
          ) : null}
          <Text variant="caption" tone="fg3">
            {num(order.limitPrice) ? 'At the order’s limit price.' : `At the latest price, $${priceUsed.toFixed(2)}; the price at the time isn’t stored.`}
          </Text>
        </Card>
      ) : null}

      {rejected ? (
        <Card style={s.checks}>
          <View style={[s.check, { borderLeftColor: c.risk }]}>
            <TriangleAlert color={c.risk} size={16} strokeWidth={1.8} />
            <Text variant="small" style={s.flex}>{order.statusMessage || 'The order was rejected without a reason.'}</Text>
          </View>
          <View style={[s.check, s.checkQuiet, { borderTopColor: c.line }]}>
            <Check color={c.fg3} size={16} strokeWidth={1.8} />
            <Text variant="small" tone="fg2" style={s.flex}>Only the check that failed is recorded, so the others aren't listed.</Text>
          </View>
        </Card>
      ) : null}

      {placed ? <Notice tone="neutral" title="Placed." detail={placed} /> : null}
      {placeError ? <Notice title="The order wasn't placed." detail={placeError} /> : null}

      {rejected && !placed && session?.isActive ? (
        <>
          <Text variant="subhead" style={s.section}>What you can do</Text>
          {smaller ? (
            <>
              <Text variant="small" tone="fg2">
                {`${side} ${smaller} ${order.symbol} now, about ${money(smaller * priceUsed, 2)}. It goes through the same checks.`}
              </Text>
              <InkButton label={`${side} ${smaller} ${order.symbol}`} onPress={() => place(smaller)} loading={placing} />
            </>
          ) : (
            <Text variant="small" tone="fg2">The session keeps running. Open it to see its holdings, or to pause or stop it.</Text>
          )}
          <QuietButton label="Open the session" onPress={() => router.push({ pathname: '/sessions/[id]', params: { id: order.sessionId } })} />
        </>
      ) : null}
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  flex: { flex: 1 },
  eyebrow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  subtitle: { marginTop: -8 },
  valueCard: { gap: 8, borderRadius: radius.lg },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  bar: { height: 8, borderRadius: 4, flexDirection: 'row', overflow: 'hidden' },
  checks: { paddingVertical: 0, paddingHorizontal: 0, borderRadius: radius.lg, overflow: 'hidden' },
  check: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderLeftWidth: 2 },
  checkQuiet: { borderLeftWidth: 0, borderTopWidth: 1, paddingLeft: 16 },
  section: { marginTop: 8, marginBottom: -4 },
}));
