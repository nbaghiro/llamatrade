import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { OrderSide, OrderType, TimeInForce } from '@llamatrade/core/proto/trading_pb';
import { toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { Copy } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Panel } from '../../components/backtest/parts';
import { buildSessionRow, CheckLadder, outcomeOf, placedAt } from '../../components/sessions';
import {
  etHm,
  largestThatFits,
  niceTicks,
  orderTime,
  parseLimitBreach,
  type LimitBreach,
} from '../../components/sessions/timeline';
import { ModeBadge, PageHead, StatList, StatusMark } from '../../components/ui';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonFigure, SkeletonRows } from '../../components/ui/Skeleton';
import { formatMoney, formatNumber } from '../../lib/format';
import { ORDER_OUTCOME_LABEL, stoppingChecks, type OrderOutcome } from '../../lib/sessionState';

const TYPE_LABEL: Partial<Record<OrderType, string>> = {
  [OrderType.MARKET]: 'Market',
  [OrderType.LIMIT]: 'Limit',
  [OrderType.STOP]: 'Stop',
  [OrderType.STOP_LIMIT]: 'Stop limit',
  [OrderType.TRAILING_STOP]: 'Trailing stop',
};

const TIF_LABEL: Partial<Record<TimeInForce, string>> = {
  [TimeInForce.DAY]: 'day',
  [TimeInForce.GTC]: 'good till cancelled',
  [TimeInForce.IOC]: 'immediate or cancel',
  [TimeInForce.FOK]: 'fill or kill',
  [TimeInForce.OPG]: 'at the open',
  [TimeInForce.CLS]: 'at the close',
};

const STATE_WORD: Record<OrderOutcome, string> = {
  stopped: 'Not sent',
  rejected: 'Rejected by Alpaca',
  filled: 'Filled',
  partial: 'Partly filled',
  open: 'Open',
  closed: 'Closed',
};

const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/** /trading/orders/:orderId: the order against its limit, every check, and the ways forward (order2 A). */
export default function OrderCheckPage() {
  const { orderId = '' } = useParams();
  const navigate = useNavigate();
  const order = useTradingStore((s) => (s.order?.id === orderId ? s.order : null));
  const orderLoading = useTradingStore((s) => s.orderLoading);
  const orderError = useTradingStore((s) => s.orderError);
  const loadOrder = useTradingStore((s) => s.loadOrder);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const placeOrder = useTradingStore((s) => s.placeOrder);
  const placing = useTradingStore((s) => s.placing);
  const placeError = useTradingStore((s) => s.placeError);
  const sessions = useTradingStore((s) => s.sessions);
  const orders = useTradingStore((s) => s.orders);
  const executions = useTradingStore((s) => s.executions);
  const sleeves = useTradingStore((s) => s.sleeves);
  const performance = useTradingStore((s) => s.performance);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const [choice, setChoice] = useState<'fit' | 'leave'>('fit');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    loadOrder(orderId).catch(() => undefined);
    loadBlotter().catch(() => undefined);
    fetchStrategies().catch(() => undefined);
  }, [orderId, loadOrder, loadBlotter, fetchStrategies]);

  const session = sessions.find((s) => s.id === order?.sessionId);
  const row = useMemo(
    () =>
      session
        ? buildSessionRow(session, { executions, sleeves, performance, strategies, orders })
        : null,
    [session, executions, sleeves, performance, strategies, orders]
  );

  const crumbs = [{ label: 'Sessions', to: '/trading' }];

  if (orderError && !order) {
    return (
      <div className="page">
        <PageHead crumbs={crumbs} title="Order" />
        <Panel>
          <PanelError
            title="This order couldn't be loaded"
            cause={orderError}
            onRetry={() => loadOrder(orderId)}
            retrying={orderLoading}
          />
        </Panel>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="page grid gap-3.5" aria-busy="true">
        <SkeletonFigure />
        <Panel>
          <SkeletonRows rows={7} cols={3} />
        </Panel>
      </div>
    );
  }

  const outcome = outcomeOf(order);
  const stopped = outcome === 'stopped';
  const failed = stopped || outcome === 'rejected';
  const checks = stopped ? stoppingChecks(order.statusMessage) : [];
  const quantity = toNumber(order.quantity);
  const breach = stopped ? parseLimitBreach(order.statusMessage) : null;
  const fill = toNumber(order.averageFillPrice);
  const price =
    fill || (breach && quantity > 0 ? breach.value / quantity : toNumber(order.limitPrice));
  const at = orderTime(order);
  const name = row?.name ?? 'Session';
  const mode = session?.mode === ExecutionMode.LIVE ? 'live' : 'paper';
  const side = order.side === OrderSide.SELL ? 'Sell' : 'Buy';
  const fits = breach && price > 0 ? largestThatFits(breach.limit, price) : 0;
  const canPlace = Boolean(breach && fits > 0 && row?.state === 'running');
  const picked = canPlace ? choice : 'leave';

  const onPlace = async () => {
    if (!order || !canPlace) return;
    const placed = await placeOrder({
      sessionId: order.sessionId,
      symbol: order.symbol,
      side: order.side === OrderSide.SELL ? 'sell' : 'buy',
      quantity: fits,
      strategyId: order.strategyId,
      sleeveId: order.sleeveId,
    });
    if (placed) navigate(`/trading/orders/${placed.id}`);
  };

  const copyId = () => {
    navigator.clipboard
      ?.writeText(order.id)
      .then(() => setCopied(true))
      .catch(() => undefined);
  };

  return (
    <div className="page">
      <PageHead
        crumbs={[
          ...crumbs,
          ...(order.sessionId ? [{ label: name, to: `/trading/${order.sessionId}` }] : []),
          { label: 'Orders' },
        ]}
        title={`${side} ${qty(quantity)} ${order.symbol}`}
        badges={
          <>
            <ModeBadge mode={mode} />
            <StatusMark
              state={failed ? 'frozen' : outcome === 'open' ? 'waiting' : 'running'}
              label={`${STATE_WORD[outcome]}${at ? ` at ${etHm(at)}` : ''}`}
            />
          </>
        }
        sub={`${name}${row?.version ? ` · version ${row.version}` : ''} · ${placedAt(order)} ET${
          stopped ? ' · nothing was sent to Alpaca' : ''
        }`}
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={copyId}>
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              {copied ? 'Copied' : 'Copy order ID'}
            </button>
            {order.sessionId && (
              <Link to={`/trading/${order.sessionId}`} className="btn btn-secondary">
                Open the session
              </Link>
            )}
          </>
        }
      />
      <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="grid min-w-0 gap-3.5">
          {breach && (
            <Panel title="Order value against the limit" aside="limit recorded with the order">
              <LimitBar
                breach={breach}
                fits={fits}
                price={price}
                symbol={order.symbol}
                quantity={quantity}
              />
            </Panel>
          )}
          <Panel title="What the checks found" aside="market hours first, then every other check">
            <CheckLadder
              stopped={checks}
              found={
                breach
                  ? { 1: `${formatMoney(breach.value)} is over ${formatMoney(breach.limit)}` }
                  : {}
              }
              others={stopped ? 'clear' : outcome === 'closed' ? 'unknown' : 'passed'}
            />
            {order.statusMessage && (
              <div className="border-t border-line px-3.5 py-3">
                <div className="mb-1.5 text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
                  Recorded with the order
                </div>
                <code className="block rounded-[6px] border border-line bg-sunk px-3 py-2 font-mono text-[12px] text-fg-2">
                  {order.statusMessage}
                </code>
              </div>
            )}
            {stopped && (
              <p className="m-0 border-t border-line px-3.5 py-2.5 text-[11.5px] text-fg-3">
                Only failures are stored with an order, so a check that was skipped reads the same
                as one that found nothing.
              </p>
            )}
          </Panel>
        </div>
        <div className="grid min-w-0 gap-3.5">
          {breach && (
            <Panel title="What you can do">
              <div className="grid gap-2 p-3.5" role="radiogroup" aria-label="What to do">
                <Option
                  on={picked === 'fit'}
                  disabled={!canPlace}
                  onSelect={() => setChoice('fit')}
                  title={`Place ${qty(fits)} ${order.symbol} now`}
                >
                  {formatMoney(fits * price)} at the price used for this order. It runs through the
                  same checks, and the next rebalance sizes around what the sleeve then holds.
                  {!canPlace && ' Only a running session can place it.'}
                </Option>
                <Option
                  on={picked === 'leave'}
                  onSelect={() => setChoice('leave')}
                  title="Leave it"
                >
                  The next rebalance tries again with the same limit and may be stopped for the same
                  reason.
                </Option>
                <p className="m-0 px-1 text-[11.5px] text-fg-3">
                  The order value limit can&apos;t be changed in the app yet.
                </p>
                {placeError && (
                  <p role="alert" className="m-0 text-[12px] text-risk">
                    {placeError}
                  </p>
                )}
                <div className="mt-1 flex justify-end gap-2">
                  <Link to={`/trading/${order.sessionId}`} className="btn btn-ghost">
                    Not now
                  </Link>
                  {picked === 'fit' ? (
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={!canPlace || placing}
                      onClick={onPlace}
                    >
                      {placing ? 'Placing…' : `Place ${qty(fits)} ${order.symbol}`}
                    </button>
                  ) : (
                    <Link to={`/trading/${order.sessionId}`} className="btn btn-primary">
                      Leave it
                    </Link>
                  )}
                </div>
              </div>
            </Panel>
          )}
          <Panel title="Order">
            <div className="px-3.5 py-1">
              <StatList
                items={[
                  {
                    label: 'Type',
                    value:
                      [TYPE_LABEL[order.type], TIF_LABEL[order.timeInForce]]
                        .filter(Boolean)
                        .join(', ') || '·',
                  },
                  ...(price > 0
                    ? [{ label: fill ? 'Average fill' : 'Price used', value: formatMoney(price) }]
                    : []),
                  ...(outcome === 'filled' || outcome === 'partial'
                    ? [
                        {
                          label: 'Filled',
                          value: `${qty(toNumber(order.filledQuantity))} of ${qty(quantity)}`,
                        },
                      ]
                    : []),
                  { label: 'Created', value: `${placedAt(order)} ET` },
                  { label: 'State', value: ORDER_OUTCOME_LABEL[outcome] },
                  {
                    label: 'Order ID',
                    value: <span className="text-fg-3">{order.id.slice(0, 8)}</span>,
                  },
                ]}
              />
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function LimitBar({
  breach,
  fits,
  price,
  symbol,
  quantity,
}: {
  breach: LimitBreach;
  fits: number;
  price: number;
  symbol: string;
  quantity: number;
}) {
  const ticks = niceTicks(Math.max(breach.value, breach.limit) * 1.05);
  const max = ticks[ticks.length - 1] || 1;
  const pct = (v: number) => `${Math.min(100, (v / max) * 100).toFixed(2)}%`;
  const over = breach.value - breach.limit;
  return (
    <div className="px-4 pb-4 pt-7">
      <div className="relative h-3 rounded-full bg-sunk">
        <i
          className="absolute inset-y-0 left-0 rounded-l-full bg-accent"
          style={{ width: pct(Math.min(breach.value, breach.limit)) }}
        />
        {over > 0 && (
          <i
            className="absolute inset-y-0 rounded-r-full bg-risk"
            style={{ left: pct(breach.limit), width: pct(over) }}
          />
        )}
        {fits > 0 && (
          <i
            className="absolute -inset-y-1 border-l border-dashed border-fg-2"
            style={{ left: pct(fits * price) }}
          />
        )}
        <i
          className="absolute -inset-y-2 border-l-2 border-fg"
          style={{ left: pct(breach.limit) }}
        />
        <span
          className="absolute -top-6 -translate-x-1/2 whitespace-nowrap font-mono text-[11px] font-semibold"
          style={{ left: pct(breach.limit) }}
        >
          Limit {formatMoney(breach.limit)}
        </span>
      </div>
      <div className="relative mt-2 h-4 font-mono text-[10.5px] text-fg-3">
        {ticks.map((t) => (
          <span key={t} className="absolute -translate-x-1/2" style={{ left: pct(t) }}>
            {formatMoney(t, { dp: 0 })}
          </span>
        ))}
      </div>
      <dl className="m-0 mt-5 flex flex-wrap gap-x-10 gap-y-3">
        <Big
          label="This order"
          value={formatMoney(breach.value)}
          sub={`${qty(quantity)} × ${formatMoney(price)}`}
        />
        <Big label="Limit" value={formatMoney(breach.limit)} sub="per order" />
        {over > 0 && (
          <Big label="Over by" value={formatMoney(over)} tone="risk" sub="the amber part" />
        )}
        {fits > 0 && (
          <Big
            label="Largest that fits"
            value={`${qty(fits)} ${symbol}`}
            sub={`${formatMoney(fits * price)}, dashed line`}
          />
        )}
      </dl>
    </div>
  );
}

function Big({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: 'risk';
}) {
  return (
    <div>
      <dt className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">{label}</dt>
      <dd
        className={`m-0 mt-1 font-mono text-[19px] font-semibold ${tone === 'risk' ? 'text-risk' : ''}`}
      >
        {value}
      </dd>
      <dd className="m-0 font-mono text-[11px] text-fg-3">{sub}</dd>
    </div>
  );
}

function Option({
  on,
  disabled = false,
  onSelect,
  title,
  children,
}: {
  on: boolean;
  disabled?: boolean;
  onSelect: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      disabled={disabled}
      onClick={onSelect}
      className={`grid grid-cols-[18px_minmax(0,1fr)] gap-3 rounded-[10px] border px-3.5 py-3 text-left disabled:opacity-60 ${
        on ? 'border-fg border-2' : 'border-line'
      }`}
    >
      <span
        aria-hidden="true"
        className={`mt-0.5 h-4 w-4 rounded-full border ${on ? 'border-[5px] border-fg' : 'border-line-strong'}`}
      />
      <span>
        <b className="block text-[13px] font-semibold">{title}</b>
        <span className="text-[12.5px] text-fg-2">{children}</span>
      </span>
    </button>
  );
}
